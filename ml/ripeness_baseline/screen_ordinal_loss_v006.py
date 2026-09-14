from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from ml.observability import RunLogger
from ml.ripeness_baseline.cache_v001 import get_or_build_snapshot_cache
from ml.ripeness_baseline.screen_lr_v002 import _num_workers, train_validation_only
from ml.ripeness_baseline.train_v001 import CLASS_TO_INDEX, CLASS_VALUES, SEED, metrics, seed_all

BASE_LR = 5e-5
ORDINAL_LAMBDA = 0.20
MAX_EPOCHS = 15
MAX_CLASS_DISTANCE = float(max(CLASS_VALUES) - min(CLASS_VALUES))


def train_ordinal_loss(cache: dict[str, Any], out: Path, logger: RunLogger, *, seed: int = SEED, max_epochs: int = MAX_EPOCHS, ordinal_lambda: float = ORDINAL_LAMBDA) -> dict[str, Any]:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Dataset
    from torchvision import models, transforms
    seed_all(seed)
    class DS(Dataset):
        def __init__(self, records, train_mode):
            self.records=records
            self.transform=transforms.Compose([transforms.RandomResizedCrop(224,scale=(0.8,1.0)),transforms.RandomHorizontalFlip(),transforms.ColorJitter(0.15,0.15,0.15,0.05),transforms.ToTensor(),transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])]) if train_mode else transforms.Compose([transforms.Resize(256),transforms.CenterCrop(224),transforms.ToTensor(),transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])])
        def __len__(self): return len(self.records)
        def __getitem__(self,i):
            r=self.records[i]; return self.transform(Image.open(r['path']).convert('RGB')),CLASS_TO_INDEX[r['label']]
    records=cache['records']; train_records=[r for r in records if r['split']=='train']; valid_records=[r for r in records if r['split']=='valid']
    counts=Counter(r['label'] for r in train_records); weights=torch.tensor([len(train_records)/(len(CLASS_VALUES)*counts[c]) for c in CLASS_VALUES],dtype=torch.float32)
    workers=_num_workers(); device=torch.device('cuda' if torch.cuda.is_available() else 'cpu'); class_values=torch.tensor(CLASS_VALUES,dtype=torch.float32,device=device)
    def loader(rs,train_mode):
        g=torch.Generator().manual_seed(seed); return DataLoader(DS(rs,train_mode),batch_size=32,shuffle=train_mode,generator=g if train_mode else None,num_workers=workers,pin_memory=torch.cuda.is_available())
    model=models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1); model.fc=nn.Linear(model.fc.in_features,len(CLASS_VALUES)); model.to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=BASE_LR,weight_decay=1e-4); ce_criterion=nn.CrossEntropyLoss(weight=weights.to(device))
    def loss_parts(logits,labels):
        ce=ce_criterion(logits,labels); probs=torch.softmax(logits,dim=1); targets=class_values[labels].unsqueeze(1); distances=torch.abs(class_values.unsqueeze(0)-targets)/MAX_CLASS_DISTANCE; ordinal=(probs*distances).sum(dim=1).mean(); return ce+ordinal_lambda*ordinal,ce,ordinal
    exp=f'ORDINAL-DISTANCE-LAMBDA-{ordinal_lambda:.2f}-seed-{seed}'; checkpoint=out/exp/'checkpoints'/'best.pt'; checkpoint.parent.mkdir(parents=True,exist_ok=True)
    best_f1=-1.0; best_epoch=0; best_metrics=None; best_loss=0.0; patience=0; history=[]
    def evaluate():
        model.eval(); yt=[]; yp=[]; total_sum=ce_sum=ordinal_sum=0.0; n=0
        with torch.no_grad():
            for x,y in loader(valid_records,False):
                x=x.to(device,non_blocking=True); y=y.to(device,non_blocking=True); z=model(x); total,ce,ordinal=loss_parts(z,y); b=len(y); total_sum+=total.item()*b; ce_sum+=ce.item()*b; ordinal_sum+=ordinal.item()*b; n+=b; p=z.argmax(1).cpu().tolist(); yt.extend(CLASS_VALUES[i] for i in y.cpu().tolist()); yp.extend(CLASS_VALUES[i] for i in p)
        return total_sum/n,ce_sum/n,ordinal_sum/n,metrics(yt,yp)
    logger.emit('INFO','SCREENING_STARTED','ordinal-aware loss screening started',phase='SCREENING',experiment=exp,change_category='LOSS',loss='weighted_ce_plus_expected_ordinal_distance',ordinal_lambda=ordinal_lambda,class_values=CLASS_VALUES,seed=seed,test_evaluated=False)
    for epoch in range(1,max_epochs+1):
        started=time.monotonic(); model.train(); total_sum=ce_sum=ordinal_sum=0.0; n=0
        for x,y in loader(train_records,True):
            x=x.to(device,non_blocking=True); y=y.to(device,non_blocking=True); optimizer.zero_grad(); z=model(x); total,ce,ordinal=loss_parts(z,y)
            if not torch.isfinite(total): raise RuntimeError(f'non-finite loss epoch={epoch}')
            total.backward(); optimizer.step(); b=len(y); total_sum+=total.item()*b; ce_sum+=ce.item()*b; ordinal_sum+=ordinal.item()*b; n+=b
        vl,vce,vord,vm=evaluate(); improved=vm['macro_f1']>best_f1+1e-8
        if improved:
            best_f1=vm['macro_f1']; best_epoch=epoch; best_metrics=vm; best_loss=vl; patience=0; torch.save(model.state_dict(),checkpoint); logger.emit('INFO','CHECKPOINT_SAVED','ordinal-aware checkpoint improved',phase='SCREENING',epoch=epoch,metric_name='valid_macro_f1',metric_value=best_f1,checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest())
        else: patience+=1
        row={'epoch':epoch,'learning_rate':BASE_LR,'ordinal_lambda':ordinal_lambda,'train_loss':total_sum/n,'train_ce_loss':ce_sum/n,'train_ordinal_penalty':ordinal_sum/n,'valid_loss':vl,'valid_ce_loss':vce,'valid_ordinal_penalty':vord,'best_epoch':best_epoch,'early_stopping_counter':patience,'epoch_elapsed_sec':round(time.monotonic()-started,3),**vm}; history.append(row); logger.emit('INFO','EPOCH_COMPLETED',f'{exp} epoch {epoch} completed',phase='SCREENING',**row)
        if patience>=5: break
    if best_metrics is None: raise RuntimeError('no ordinal-aware checkpoint')
    result={'experiment':exp,'ordinal_lambda':ordinal_lambda,'seed':seed,'test_evaluated':False,'controlled_change':'loss_expected_ordinal_distance_only','best_epoch':best_epoch,'best_valid_loss':best_loss,'best_valid_metrics':best_metrics,'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),'history':history}; (out/exp/'validation_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); return result

def main():
    p=argparse.ArgumentParser(); p.add_argument('--workdir',type=Path,default=Path('artifacts/ripeness-v006-ordinal-loss-local-gpu')); p.add_argument('--epochs',type=int,default=15); p.add_argument('--seed',type=int,default=SEED); p.add_argument('--ordinal-lambda',type=float,default=ORDINAL_LAMBDA); args=p.parse_args(); logger=RunLogger(args.workdir,'ripeness_v006_ordinal_loss')
    try:
        logger.emit('INFO','RUN_STARTED','RIPENESS-V006 ordinal-aware loss screening started',phase='INIT',experiment_id='RIPENESS-V006-ORDINAL-LOSS',snapshot_id='KGCV-RIPENESS-V001',seed=args.seed,test_evaluated=False); cache=get_or_build_snapshot_cache(logger); baseline=train_validation_only(cache,args.workdir,logger,BASE_LR,args.epochs,args.seed); candidate=train_ordinal_loss(cache,args.workdir,logger,seed=args.seed,max_epochs=args.epochs,ordinal_lambda=args.ordinal_lambda); comparison={'status':'SCREENING_COMPLETE','test_evaluated':False,'change_category':'LOSS','controlled_change':'expected_ordinal_distance_regularizer_only','baseline':baseline,'candidate':candidate}; (args.workdir/'comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8'); logger.finish_summary(status='SUCCESS',summary_path=args.workdir/'summaries'/'run_summary.json',final_metrics={'baseline':baseline['best_valid_metrics'],'ordinal_loss':candidate['best_valid_metrics']})
    except Exception as exc:
        logger.exception('RUN_FAILED','V006 ordinal loss screening failed',exc,phase='FAILED'); logger.finish_summary(status='FAILED',summary_path=args.workdir/'summaries'/'run_summary.json'); raise
if __name__=='__main__': main()
