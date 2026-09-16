from __future__ import annotations

import argparse, hashlib, json, time
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from ml.observability import RunLogger
from ml.ripeness_baseline.cache_io import CANONICAL_CACHE_ROOT, load_or_build_crop_cache
from ml.ripeness_baseline.screen_lr_v002 import _num_workers
from ml.ripeness_baseline.train_v001 import CLASS_TO_INDEX, CLASS_VALUES, metrics, seed_all

LR = 5e-5
PATIENCE = 12
MAX_EPOCHS = 25


def run(cache: dict[str, Any], out: Path, logger: RunLogger, seed: int) -> dict[str, Any]:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Dataset
    from torchvision import models, transforms

    seed_all(seed)

    class DS(Dataset):
        def __init__(self, records, train_mode):
            self.records = records
            self.transform = transforms.Compose([
                transforms.RandomResizedCrop(224, scale=(0.8, 1.0)),
                transforms.RandomHorizontalFlip(),
                transforms.ColorJitter(0.15, 0.15, 0.15, 0.05),
                transforms.ToTensor(),
                transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225]),
            ]) if train_mode else transforms.Compose([
                transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(),
                transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225]),
            ])
        def __len__(self): return len(self.records)
        def __getitem__(self, i):
            r=self.records[i]
            return self.transform(Image.open(r['path']).convert('RGB')), CLASS_TO_INDEX[r['label']]

    train_records=[r for r in cache['records'] if r['split']=='train']
    valid_records=[r for r in cache['records'] if r['split']=='valid']
    counts=Counter(r['label'] for r in train_records)
    weights=torch.tensor([len(train_records)/(len(CLASS_VALUES)*counts[c]) for c in CLASS_VALUES],dtype=torch.float32)
    workers=_num_workers()
    def loader(records, train_mode):
        g=torch.Generator().manual_seed(seed)
        return DataLoader(DS(records,train_mode),batch_size=32,shuffle=train_mode,generator=g if train_mode else None,num_workers=workers,pin_memory=torch.cuda.is_available())

    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model=models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    model.fc=nn.Linear(model.fc.in_features,len(CLASS_VALUES)); model.to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=LR,weight_decay=1e-4)
    criterion=nn.CrossEntropyLoss(weight=weights.to(device))
    checkpoint=out/'checkpoints'/'best.pt'; checkpoint.parent.mkdir(parents=True,exist_ok=True)
    best=-1.0; best_epoch=0; best_metrics=None; wait=0; history=[]

    def evaluate():
        model.eval(); yt=[]; yp=[]; loss_sum=0.; n=0
        with torch.no_grad():
            for x,y in loader(valid_records,False):
                x=x.to(device); y=y.to(device); z=model(x); loss_sum += criterion(z,y).item()*len(y); n+=len(y)
                yt.extend(CLASS_VALUES[i] for i in y.cpu().tolist()); yp.extend(CLASS_VALUES[i] for i in z.argmax(1).cpu().tolist())
        return loss_sum/n, metrics(yt,yp)

    logger.emit('INFO','TRAINING_STARTED','patience diagnostic training started',phase='PATIENCE_DIAGNOSTIC',learning_rate=LR,patience=PATIENCE,max_epochs=MAX_EPOCHS,train_samples=len(train_records),valid_samples=len(valid_records),device=str(device))

    for epoch in range(1,MAX_EPOCHS+1):
        started=time.monotonic(); model.train(); loss_sum=0.; n=0
        for x,y in loader(train_records,True):
            x=x.to(device); y=y.to(device); optimizer.zero_grad(); z=model(x); loss=criterion(z,y)
            if not torch.isfinite(loss): raise RuntimeError(f'non-finite loss epoch={epoch}')
            loss.backward(); optimizer.step(); loss_sum += loss.item()*len(y); n+=len(y)
        vl, vm=evaluate(); improved=vm['macro_f1'] > best + 1e-8
        if improved:
            best=vm['macro_f1']; best_epoch=epoch; best_metrics=vm; wait=0; torch.save(model.state_dict(),checkpoint)
            logger.emit('INFO','CHECKPOINT_SAVED','patience diagnostic checkpoint improved',phase='PATIENCE_DIAGNOSTIC',epoch=epoch,metric_value=best,checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest())
        else: wait += 1
        row={'epoch':epoch,'train_loss':loss_sum/n,'valid_loss':vl,'macro_f1':vm['macro_f1'],'ordinal_mae':vm['ordinal_mae'],'weighted_kappa':vm['weighted_kappa'],'m1_f1':vm['per_class']['1']['f1'],'best_epoch':best_epoch,'no_improve_count':wait,'epoch_elapsed_sec':round(time.monotonic()-started,3)}
        history.append(row); logger.emit('INFO','EPOCH_COMPLETED','patience diagnostic epoch completed',phase='PATIENCE_DIAGNOSTIC',learning_rate=LR,early_stopping_counter=wait,**row)
        if wait>=PATIENCE:
            logger.emit('INFO','EARLY_STOPPING_TRIGGERED','extended patience exhausted',phase='PATIENCE_DIAGNOSTIC',epoch=epoch,best_epoch=best_epoch,best_valid_macro_f1=best,patience_limit=PATIENCE)
            break

    result={'experiment':'RIPENESS-V003-PATIENCE-DIAGNOSTIC','seed':seed,'learning_rate':LR,'patience':PATIENCE,'max_epochs':MAX_EPOCHS,'test_evaluated':False,'best_epoch':best_epoch,'best_valid_metrics':best_metrics,'history':history,'stopped_epoch':history[-1]['epoch']}
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--seed',type=int,default=20260910)
    ap.add_argument('--workdir',type=Path,default=Path('artifacts/ripeness-v003-patience'))
    ap.add_argument('--cache-root',type=Path,default=CANONICAL_CACHE_ROOT)
    ap.add_argument('--allow-download',action='store_true',help='build canonical snapshot cache only when unavailable')
    a=ap.parse_args()
    logger=RunLogger(a.workdir,'ripeness_v003_patience')
    try:
        logger.emit('INFO','RUN_STARTED','patience diagnostic started',phase='INIT',experiment_id='RIPENESS-V003-PATIENCE-DIAGNOSTIC',snapshot_id='KGCV-RIPENESS-V001',seed=a.seed,test_evaluated=False,cache_root=str(a.cache_root),allow_download=a.allow_download)
        cache=load_or_build_crop_cache(a.cache_root,logger,allow_download=a.allow_download)
        result=run(cache,a.workdir,logger,a.seed)
        logger.finish_summary(status='SUCCESS',summary_path=a.workdir/'summaries'/'run_summary.json',final_metrics={'best_epoch':result['best_epoch'],**result['best_valid_metrics']})
    except Exception as exc:
        logger.exception('RUN_FAILED','patience diagnostic failed',exc,phase='FAILED'); logger.finish_summary(status='FAILED',summary_path=a.workdir/'summaries'/'run_summary.json'); raise

if __name__=='__main__': main()
