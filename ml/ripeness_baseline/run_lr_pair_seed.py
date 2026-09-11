from __future__ import annotations
import argparse, json
from pathlib import Path
from ml.observability import RunLogger
from ml.ripeness_baseline.screen_lr_v002 import train_validation_only
from ml.ripeness_baseline.train_v001 import EXPECTED_ASSIGNMENT_SHA256, EXPECTED_PHYSICAL_IMAGES, EXPECTED_SAMPLES, EXPECTED_SPLIT_COUNTS, build_crop_cache


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--seed',type=int,required=True); ap.add_argument('--workdir',type=Path,required=True); ap.add_argument('--epochs',type=int,default=12); a=ap.parse_args()
    logger=RunLogger(a.workdir,f'ripeness_lr_pair_{a.seed}')
    try:
        logger.emit('INFO','RUN_STARTED','paired LR validation started',phase='INIT',experiment_id='RIPENESS-V002-LR-CONFIRMATION',snapshot_id='KGCV-RIPENESS-V001',seed=a.seed,test_evaluated=False)
        cache=build_crop_cache(a.workdir/'crops',logger)
        if cache['errors'] or cache['physical_images']!=EXPECTED_PHYSICAL_IMAGES or cache['samples']!=EXPECTED_SAMPLES: raise RuntimeError('snapshot count/error contract failed')
        if cache['split_counts']!=EXPECTED_SPLIT_COUNTS or cache['assignment_sha256']!=EXPECTED_ASSIGNMENT_SHA256: raise RuntimeError('frozen split contract failed')
        results=[train_validation_only(cache,a.workdir,logger,lr,a.epochs,a.seed) for lr in (3e-4,5e-5)]
        payload={'seed':a.seed,'test_evaluated':False,'results':results}
        (a.workdir/'pair-result.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        logger.finish_summary(status='SUCCESS',summary_path=a.workdir/'summaries'/'run_summary.json',final_metrics={r['experiment']:r['best_valid_metrics'] for r in results})
    except Exception as exc:
        logger.exception('RUN_FAILED','paired LR validation failed',exc,phase='FAILED'); logger.finish_summary(status='FAILED',summary_path=a.workdir/'summaries'/'run_summary.json'); raise
if __name__=='__main__': main()
