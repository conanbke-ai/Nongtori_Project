from __future__ import annotations

import argparse, hashlib, io, json, math, os, random, time, urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ml.data_pipeline.hf_metadata_audit import _fetch_page
from ml.data_pipeline.kgcv_manifest import STAGE_MAPPING

CLASS_VALUES=[0,1,4]
CLASS_TO_INDEX={v:i for i,v in enumerate(CLASS_VALUES)}
SEED=20260910


def seed_all(seed:int=SEED):
    random.seed(seed); np.random.seed(seed)
    import torch
    torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(False)


def fetch_bytes(url:str,retries:int=5)->bytes:
    last=None
    for i in range(retries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Nongtori-Baseline/1.0"})
            with urllib.request.urlopen(req,timeout=180) as r: return r.read()
        except Exception as e:
            last=e; time.sleep(min(16,2**i))
    raise RuntimeError(last)


def image_src(row:dict[str,Any])->str:
    image=row.get("image") or {}
    if isinstance(image,dict) and image.get("src"): return str(image["src"])
    raise ValueError("missing image.src")


def build_crop_cache(root:Path)->dict[str,Any]:
    root.mkdir(parents=True,exist_ok=True)
    first=_fetch_page(offset=0,length=100)
    total=int(first["num_rows_total"]); pages=[first]
    for off in range(100,total,100): pages.append(_fetch_page(offset=off,length=min(100,total-off)))
    records=[]; hash_to_rows={}; errors=[]
    for page in pages:
        for wrapped in page.get("rows",[]):
            row_idx=int(wrapped["row_idx"]); row=wrapped.get("row") or {}; objects=row.get("objects") or {}
            cats=objects.get("categories") or []
            eligible=[]
            for oi,cid in enumerate(cats):
                stage={0:"flower",1:"green",2:"overripe",3:"red",4:"small g",5:"turning red",6:"white"}.get(int(cid))
                spec=STAGE_MAPPING.get(stage or "",{})
                if spec.get("eligible") and spec.get("maturity") in CLASS_TO_INDEX: eligible.append((oi,stage,int(spec["maturity"])))
            if not eligible: continue
            try:
                data=fetch_bytes(image_src(row)); sha=hashlib.sha256(data).hexdigest(); hash_to_rows.setdefault(sha,[]).append(row_idx)
                img=Image.open(io.BytesIO(data)).convert("RGB"); w,h=img.size
                bboxes=objects.get("bbox") or []
                for oi,stage,maturity in eligible:
                    if oi>=len(bboxes): raise ValueError(f"missing bbox object={oi}")
                    x,y,bw,bh=[float(v) for v in bboxes[oi]]
                    x1=max(0,int(math.floor(x))); y1=max(0,int(math.floor(y))); x2=min(w,int(math.ceil(x+bw))); y2=min(h,int(math.ceil(y+bh)))
                    if x2<=x1 or y2<=y1: raise ValueError(f"invalid bbox {bboxes[oi]}")
                    path=root/f"{row_idx}_{oi}.jpg"; img.crop((x1,y1,x2,y2)).save(path,quality=92)
                    records.append({"row_idx":row_idx,"object_idx":oi,"sha256":sha,"path":str(path),"label":maturity,"stage":stage})
            except Exception as exc: errors.append({"row_idx":row_idx,"error":str(exc)})
    hashes=sorted(hash_to_rows); random.Random(SEED).shuffle(hashes); n=len(hashes); a=round(n*.70); b=a+round(n*.15)
    split_of={sha:("train" if i<a else "valid" if i<b else "test") for i,sha in enumerate(hashes)}
    for r in records:r["split"]=split_of[r["sha256"]]
    meta={"physical_images":len(hash_to_rows),"samples":len(records),"errors":errors,"records":records,"split_counts":dict(Counter(r["split"] for r in records))}
    (root/"cache_manifest.json").write_text(json.dumps(meta,ensure_ascii=False),encoding="utf-8")
    return meta


def metrics(y_true,y_pred):
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support, cohen_kappa_score
    p,r,f,_=precision_recall_fscore_support(y_true,y_pred,labels=CLASS_VALUES,zero_division=0)
    return {"accuracy":float(accuracy_score(y_true,y_pred)),"macro_f1":float(f1_score(y_true,y_pred,labels=CLASS_VALUES,average="macro",zero_division=0)),"ordinal_mae":float(np.mean(np.abs(np.array(y_true)-np.array(y_pred)))),"weighted_kappa":float(cohen_kappa_score(y_true,y_pred,labels=CLASS_VALUES,weights="quadratic")),"per_class":{str(c):{"precision":float(p[i]),"recall":float(r[i]),"f1":float(f[i])} for i,c in enumerate(CLASS_VALUES)},"confusion_matrix":confusion_matrix(y_true,y_pred,labels=CLASS_VALUES).tolist()}


def train(cache:dict[str,Any],out:Path,max_epochs:int=30):
    import torch
    from torch import nn
    from torch.utils.data import Dataset,DataLoader
    from torchvision import models,transforms
    class DS(Dataset):
        def __init__(self,recs,train=False):
            self.r=recs
            self.t=(transforms.Compose([transforms.RandomResizedCrop(224,scale=(.8,1.0)),transforms.RandomHorizontalFlip(),transforms.ColorJitter(.15,.15,.15,.05),transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])]) if train else transforms.Compose([transforms.Resize(256),transforms.CenterCrop(224),transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])]))
        def __len__(self): return len(self.r)
        def __getitem__(self,i): return self.t(Image.open(self.r[i]["path"]).convert("RGB")),CLASS_TO_INDEX[self.r[i]["label"]]
    recs=cache["records"]; tr=[r for r in recs if r["split"]=="train"]; va=[r for r in recs if r["split"]=="valid"]; te=[r for r in recs if r["split"]=="test"]
    counts=Counter(r["label"] for r in tr); weights=torch.tensor([len(tr)/(len(CLASS_VALUES)*counts[c]) for c in CLASS_VALUES],dtype=torch.float32)
    dl=lambda rs,t:DataLoader(DS(rs,t),batch_size=32,shuffle=t,num_workers=2,pin_memory=False)
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model=models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1); model.fc=nn.Linear(model.fc.in_features,len(CLASS_VALUES)); model.to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=3e-4,weight_decay=1e-4); crit=nn.CrossEntropyLoss(weight=weights.to(device))
    best=-1.; best_epoch=0; patience=0; history=[]; best_path=out/"best.pt"; out.mkdir(parents=True,exist_ok=True)
    def evaluate(loader):
        model.eval(); yt=[];yp=[]; loss=0.;n=0
        with torch.no_grad():
            for x,y in loader:
                x=x.to(device); y=y.to(device); z=model(x); loss+=crit(z,y).item()*len(y); n+=len(y); pred=z.argmax(1).cpu().tolist(); yt += [CLASS_VALUES[i] for i in y.cpu().tolist()]; yp += [CLASS_VALUES[i] for i in pred]
        return loss/max(1,n),metrics(yt,yp)
    for epoch in range(1,max_epochs+1):
        model.train(); tl=0.;n=0
        for x,y in dl(tr,True):
            x=x.to(device);y=y.to(device);opt.zero_grad();z=model(x);loss=crit(z,y);loss.backward();opt.step();tl+=loss.item()*len(y);n+=len(y)
        vl,vm=evaluate(dl(va,False)); history.append({"epoch":epoch,"train_loss":tl/n,"valid_loss":vl,**vm}); print(json.dumps(history[-1]))
        if vm["macro_f1"]>best+1e-8: best=vm["macro_f1"];best_epoch=epoch;patience=0;torch.save(model.state_dict(),best_path)
        else: patience+=1
        if patience>=5: break
    model.load_state_dict(torch.load(best_path,map_location=device,weights_only=True)); test_loss,test_metrics=evaluate(dl(te,False))
    result={"experiment_id":"RIPENESS-BASELINE-V001","snapshot_id":"KGCV-RIPENESS-V001","status":"REPRODUCED","device":str(device),"seed":SEED,"best_epoch":best_epoch,"best_valid_macro_f1":best,"test_loss":test_loss,"test_metrics":test_metrics,"history":history,"cache_summary":{k:v for k,v in cache.items() if k!="records"}}
    (out/"metrics.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--workdir",type=Path,default=Path("artifacts/ripeness-baseline-v001"));ap.add_argument("--epochs",type=int,default=30);a=ap.parse_args();seed_all(); cache=build_crop_cache(a.workdir/"crops")
    if cache["errors"] or cache["samples"]!=3162: raise SystemExit(f"cache contract failed: samples={cache['samples']} errors={len(cache['errors'])}")
    result=train(cache,a.workdir,a.epochs);print(json.dumps(result["test_metrics"],ensure_ascii=False,indent=2))
if __name__=="__main__": main()
