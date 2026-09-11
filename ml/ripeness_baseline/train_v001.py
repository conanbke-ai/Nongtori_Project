from __future__ import annotations

import argparse, hashlib, io, json, math, random, time, urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ml.data_pipeline.hf_metadata_audit import _fetch_page
from ml.data_pipeline.kgcv_manifest import STAGE_MAPPING
from ml.observability import RunLogger

CLASS_VALUES=[0,1,4]
CLASS_TO_INDEX={v:i for i,v in enumerate(CLASS_VALUES)}
SEED=20260910


def seed_all(seed:int=SEED):
    random.seed(seed); np.random.seed(seed)
    import torch
    torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(False)


def fetch_bytes(url:str, logger:RunLogger, row_idx:int, retries:int=5)->bytes:
    last=None
    for attempt in range(1,retries+1):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Nongtori-Baseline/1.0"})
            with urllib.request.urlopen(req,timeout=180) as r: return r.read()
        except Exception as e:
            last=e
            backoff=min(16,2**(attempt-1))
            logger.emit("WARNING","REMOTE_FETCH_RETRY","image fetch failed; retrying",phase="CACHE_BUILD",row_idx=row_idx,attempt=attempt,max_attempts=retries,error_type=type(e).__name__,error_message=str(e),backoff_sec=backoff)
            if attempt<retries: time.sleep(backoff)
    raise RuntimeError(last)


def image_src(row:dict[str,Any])->str:
    image=row.get("image") or {}
    if isinstance(image,dict) and image.get("src"): return str(image["src"])
    raise ValueError("missing image.src")


def build_crop_cache(root:Path, logger:RunLogger)->dict[str,Any]:
    root.mkdir(parents=True,exist_ok=True)
    logger.emit("INFO","PHASE_STARTED","building KGCV object crop cache",phase="CACHE_BUILD",expected_samples=3162)
    first=_fetch_page(offset=0,length=100); total=int(first["num_rows_total"]); pages=[first]
    for off in range(100,total,100): pages.append(_fetch_page(offset=off,length=min(100,total-off)))
    records=[]; hash_to_rows={}; errors=[]; processed=0; next_pct=5
    for page in pages:
        for wrapped in page.get("rows",[]):
            row_idx=int(wrapped["row_idx"]); row=wrapped.get("row") or {}; objects=row.get("objects") or {}; processed+=1
            cats=objects.get("categories") or []; eligible=[]
            for oi,cid in enumerate(cats):
                stage={0:"flower",1:"green",2:"overripe",3:"red",4:"small g",5:"turning red",6:"white"}.get(int(cid)); spec=STAGE_MAPPING.get(stage or "",{})
                if spec.get("eligible") and spec.get("maturity") in CLASS_TO_INDEX: eligible.append((oi,stage,int(spec["maturity"])))
            if eligible:
                try:
                    data=fetch_bytes(image_src(row),logger,row_idx); sha=hashlib.sha256(data).hexdigest(); hash_to_rows.setdefault(sha,[]).append(row_idx)
                    img=Image.open(io.BytesIO(data)).convert("RGB"); w,h=img.size; bboxes=objects.get("bbox") or []
                    for oi,stage,maturity in eligible:
                        if oi>=len(bboxes): raise ValueError(f"missing bbox object={oi}")
                        x,y,bw,bh=[float(v) for v in bboxes[oi]]; x1=max(0,int(math.floor(x))); y1=max(0,int(math.floor(y))); x2=min(w,int(math.ceil(x+bw))); y2=min(h,int(math.ceil(y+bh)))
                        if x2<=x1 or y2<=y1: raise ValueError(f"invalid bbox {bboxes[oi]}")
                        path=root/f"{row_idx}_{oi}.jpg"; img.crop((x1,y1,x2,y2)).save(path,quality=92); records.append({"row_idx":row_idx,"object_idx":oi,"sha256":sha,"path":str(path),"label":maturity,"stage":stage})
                except Exception as exc:
                    errors.append({"row_idx":row_idx,"error":str(exc)}); logger.exception("CACHE_ROW_FAILED","failed to materialize source row",exc,phase="CACHE_BUILD",row_idx=row_idx)
            pct=processed*100/total
            if pct>=next_pct or processed==total:
                logger.progress(phase="CACHE_BUILD",current=processed,total=total,message="source rows scanned",crop_samples=len(records),failed_rows=len(errors)); next_pct+=5
    hashes=sorted(hash_to_rows); random.Random(SEED).shuffle(hashes); n=len(hashes); a=round(n*.70); b=a+round(n*.15); split_of={sha:("train" if i<a else "valid" if i<b else "test") for i,sha in enumerate(hashes)}
    for r in records:r["split"]=split_of[r["sha256"]]
    meta={"physical_images":len(hash_to_rows),"samples":len(records),"errors":errors,"records":records,"split_counts":dict(Counter(r["split"] for r in records)),"class_counts":dict(Counter(str(r["label"]) for r in records))}
    (root/"cache_manifest.json").write_text(json.dumps(meta,ensure_ascii=False),encoding="utf-8")
    logger.emit("INFO","PHASE_COMPLETED","crop cache built",phase="CACHE_BUILD",physical_images=meta["physical_images"],samples=meta["samples"],split_counts=meta["split_counts"],class_counts=meta["class_counts"],failed_rows=len(errors))
    return meta


def metrics(y_true,y_pred):
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support, cohen_kappa_score
    p,r,f,_=precision_recall_fscore_support(y_true,y_pred,labels=CLASS_VALUES,zero_division=0)
    return {"accuracy":float(accuracy_score(y_true,y_pred)),"macro_f1":float(f1_score(y_true,y_pred,labels=CLASS_VALUES,average="macro",zero_division=0)),"ordinal_mae":float(np.mean(np.abs(np.array(y_true)-np.array(y_pred)))),"weighted_kappa":float(cohen_kappa_score(y_true,y_pred,labels=CLASS_VALUES,weights="quadratic")),"per_class":{str(c):{"precision":float(p[i]),"recall":float(r[i]),"f1":float(f[i])} for i,c in enumerate(CLASS_VALUES)},"confusion_matrix":confusion_matrix(y_true,y_pred,labels=CLASS_VALUES).tolist()}


def train(cache:dict[str,Any],out:Path,logger:RunLogger,max_epochs:int=30):
    import torch
    from torch import nn
    from torch.utils.data import Dataset,DataLoader
    from torchvision import models,transforms
    class DS(Dataset):
        def __init__(self,recs,train=False):
            self.r=recs; self.t=(transforms.Compose([transforms.RandomResizedCrop(224,scale=(.8,1.0)),transforms.RandomHorizontalFlip(),transforms.ColorJitter(.15,.15,.15,.05),transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])]) if train else transforms.Compose([transforms.Resize(256),transforms.CenterCrop(224),transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])]))
        def __len__(self): return len(self.r)
        def __getitem__(self,i): return self.t(Image.open(self.r[i]["path"]).convert("RGB")),CLASS_TO_INDEX[self.r[i]["label"]]
    recs=cache["records"]; tr=[r for r in recs if r["split"]=="train"]; va=[r for r in recs if r["split"]=="valid"]; te=[r for r in recs if r["split"]=="test"]
    counts=Counter(r["label"] for r in tr); weights=torch.tensor([len(tr)/(len(CLASS_VALUES)*counts[c]) for c in CLASS_VALUES],dtype=torch.float32)
    dl=lambda rs,t:DataLoader(DS(rs,t),batch_size=32,shuffle=t,num_workers=2,pin_memory=False)
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu"); logger.emit("INFO","TRAINING_STARTED","baseline training started",phase="TRAIN",device=str(device),max_epochs=max_epochs,train_samples=len(tr),valid_samples=len(va),test_samples=len(te),class_weights=weights.tolist())
    model=models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1); model.fc=nn.Linear(model.fc.in_features,len(CLASS_VALUES)); model.to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=3e-4,weight_decay=1e-4); crit=nn.CrossEntropyLoss(weight=weights.to(device)); best=-1.; best_epoch=0; patience=0; history=[]; best_path=out/"checkpoints"/"best.pt"; best_path.parent.mkdir(parents=True,exist_ok=True); out.mkdir(parents=True,exist_ok=True)
    def evaluate(loader):
        model.eval(); yt=[];yp=[]; loss=0.;n=0
        with torch.no_grad():
            for x,y in loader:
                x=x.to(device); y=y.to(device); z=model(x); loss+=crit(z,y).item()*len(y); n+=len(y); pred=z.argmax(1).cpu().tolist(); yt += [CLASS_VALUES[i] for i in y.cpu().tolist()]; yp += [CLASS_VALUES[i] for i in pred]
        return loss/max(1,n),metrics(yt,yp)
    for epoch in range(1,max_epochs+1):
        epoch_start=time.monotonic(); model.train(); tl=0.;n=0; train_loader=dl(tr,True); batches=len(train_loader); next_batch_pct=10
        logger.emit("INFO","EPOCH_STARTED",f"epoch {epoch}/{max_epochs} started",phase="TRAIN",epoch=epoch,max_epochs=max_epochs,learning_rate=opt.param_groups[0]["lr"])
        for bi,(x,y) in enumerate(train_loader,1):
            x=x.to(device);y=y.to(device);opt.zero_grad();z=model(x);loss=crit(z,y)
            if not torch.isfinite(loss): raise RuntimeError(f"non-finite loss at epoch={epoch} batch={bi}: {loss.item()}")
            loss.backward();opt.step();tl+=loss.item()*len(y);n+=len(y); pct=bi*100/batches
            if pct>=next_batch_pct or bi==batches:
                logger.progress(phase="TRAIN_BATCH",current=bi,total=batches,message=f"epoch {epoch} batch progress",epoch=epoch,running_train_loss=tl/max(1,n),learning_rate=opt.param_groups[0]["lr"]); next_batch_pct+=10
        vl,vm=evaluate(dl(va,False)); improved=vm["macro_f1"]>best+1e-8; checkpoint_saved=False; checkpoint_sha=""
        if improved:
            best=vm["macro_f1"];best_epoch=epoch;patience=0;torch.save(model.state_dict(),best_path);checkpoint_sha=hashlib.sha256(best_path.read_bytes()).hexdigest();checkpoint_saved=True;logger.emit("INFO","CHECKPOINT_SAVED","new best checkpoint saved",phase="CHECKPOINT",epoch=epoch,checkpoint_path=str(best_path),checkpoint_sha256=checkpoint_sha,metric_name="valid_macro_f1",metric_value=best)
        else:
            patience+=1;logger.emit("WARNING","EARLY_STOPPING_WAIT","validation metric did not improve",phase="VALIDATE",epoch=epoch,early_stopping_counter=patience,patience_limit=5,best_metric=best,best_epoch=best_epoch)
        row={"epoch":epoch,"train_loss":tl/n,"valid_loss":vl,"learning_rate":opt.param_groups[0]["lr"],"best_metric":best,"best_epoch":best_epoch,"early_stopping_counter":patience,"checkpoint_saved":checkpoint_saved,"epoch_elapsed_sec":round(time.monotonic()-epoch_start,3),**vm};history.append(row)
        logger.emit("INFO","EPOCH_COMPLETED",f"epoch {epoch}/{max_epochs} completed",phase="VALIDATE",**row)
        if patience>=5:
            logger.emit("INFO","EARLY_STOPPING_TRIGGERED","early stopping triggered",phase="TRAIN",epoch=epoch,best_epoch=best_epoch,best_valid_macro_f1=best);break
    if not best_path.exists(): raise RuntimeError("required best checkpoint was not created")
    final_checkpoint_sha=hashlib.sha256(best_path.read_bytes()).hexdigest(); model.load_state_dict(torch.load(best_path,map_location=device,weights_only=True));logger.emit("INFO","TEST_STARTED","running final frozen test evaluation",phase="TEST",test_samples=len(te),best_epoch=best_epoch,checkpoint_sha256=final_checkpoint_sha)
    test_loss,test_metrics=evaluate(dl(te,False)); logger.emit("INFO","TEST_COMPLETED","final test evaluation completed",phase="TEST",test_loss=test_loss,**test_metrics)
    result={"experiment_id":"RIPENESS-BASELINE-V001","snapshot_id":"KGCV-RIPENESS-V001","status":"REPRODUCED","device":str(device),"seed":SEED,"best_epoch":best_epoch,"best_valid_macro_f1":best,"best_checkpoint":str(best_path),"best_checkpoint_sha256":final_checkpoint_sha,"test_loss":test_loss,"test_metrics":test_metrics,"history":history,"cache_summary":{k:v for k,v in cache.items() if k!="records"}}
    (out/"metrics.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--workdir",type=Path,default=Path("artifacts/ripeness-baseline-v001"));ap.add_argument("--epochs",type=int,default=30);a=ap.parse_args();logger=RunLogger(a.workdir,"ripeness_baseline_v001")
    try:
        logger.emit("INFO","RUN_STARTED","RIPENESS-BASELINE-V001 run started",phase="INIT",experiment_id="RIPENESS-BASELINE-V001",snapshot_id="KGCV-RIPENESS-V001",seed=SEED,max_epochs=a.epochs);seed_all();cache=build_crop_cache(a.workdir/"crops",logger)
        if cache["errors"] or cache["samples"]!=3162: raise RuntimeError(f"cache contract failed: samples={cache['samples']} errors={len(cache['errors'])}")
        result=train(cache,a.workdir,logger,a.epochs);logger.finish_summary(status="SUCCESS",summary_path=a.workdir/"summaries"/"run_summary.json",input_count=cache["physical_images"],processed_count=cache["physical_images"],success_count=cache["samples"],failed_count=len(cache["errors"]),best_checkpoint=result["best_checkpoint"],best_checkpoint_sha256=result["best_checkpoint_sha256"],best_metric={"valid_macro_f1":result["best_valid_macro_f1"]},final_metrics=result["test_metrics"]);print(json.dumps(result["test_metrics"],ensure_ascii=False,indent=2))
    except Exception as exc:
        logger.exception("RUN_FAILED","baseline run failed",exc,phase="FAILED");logger.finish_summary(status="FAILED",summary_path=a.workdir/"summaries"/"run_summary.json");raise
if __name__=="__main__": main()
