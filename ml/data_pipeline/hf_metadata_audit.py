from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

HF_ROWS_ENDPOINT = "https://datasets-server.huggingface.co/rows"
KGCV_DATASET = "Project-AgML/strawberry_growth_detection"
KGCV_CONFIG = "default"
KGCV_SPLIT = "train"
KGCV_CLASS_NAMES = {0: "flower", 1: "green", 2: "overripe", 3: "red", 4: "small g", 5: "turning red", 6: "white"}

def _to_float(value: Any) -> float | None:
    if value in (None, "", "-1", -1): return None
    try: parsed=float(value)
    except (TypeError,ValueError): return None
    return parsed if math.isfinite(parsed) else None

def _percentile(values:list[float],q:float)->float|None:
    if not values:return None
    o=sorted(values)
    if len(o)==1:return o[0]
    pos=(len(o)-1)*q; lo=math.floor(pos); hi=math.ceil(pos)
    if lo==hi:return o[lo]
    w=pos-lo; return o[lo]*(1-w)+o[hi]*w

def _fetch_page(*,offset:int,length:int,timeout:int=12,retries:int=2)->dict[str,Any]:
    params=urllib.parse.urlencode({"dataset":KGCV_DATASET,"config":KGCV_CONFIG,"split":KGCV_SPLIT,"offset":offset,"length":length}); url=f"{HF_ROWS_ENDPOINT}?{params}"; last=None
    for attempt in range(retries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Nongtori-KGCV-Audit/1.0"})
            with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
        except Exception as exc:
            last=exc
            if attempt+1<retries:time.sleep(1)
    raise RuntimeError(f"failed to fetch Hugging Face rows offset={offset}: {last}")

def audit_kgcv_hf_metadata(*,page_size:int=100)->dict[str,Any]:
    if not 1<=page_size<=100:raise ValueError("page_size must be between 1 and 100")
    first=_fetch_page(offset=0,length=page_size); total=int(first.get("num_rows_total",0)); pages=[first]
    for offset in range(page_size,total,page_size):pages.append(_fetch_page(offset=offset,length=min(page_size,total-offset)))
    classes:Counter[str]=Counter(); sources:Counter[str]=Counter(); decimals:dict[str,list[float]]=defaultdict(list); errors=[]; anns=0; seen=0
    for page in pages:
        for wrapped in page.get("rows",[]):
            seen+=1; row=wrapped.get("row",{}) or {}; sources[str(row.get("source","UNKNOWN"))]+=1; objects=row.get("objects",{}) or {}; cats=objects.get("categories",[]) or []; ds=objects.get("decimal_stage",[]) or []
            if len(cats)!=len(ds):errors.append({"row_idx":wrapped.get("row_idx"),"error":"OBJECT_ARRAY_LENGTH_MISMATCH"});continue
            for cid,raw in zip(cats,ds):
                try:cid=int(cid)
                except (TypeError,ValueError):errors.append({"row_idx":wrapped.get("row_idx"),"error":f"INVALID_CLASS_ID:{cid}"});continue
                stage=KGCV_CLASS_NAMES.get(cid)
                if stage is None:errors.append({"row_idx":wrapped.get("row_idx"),"error":f"UNKNOWN_CLASS_ID:{cid}"});continue
                classes[stage]+=1;anns+=1;d=_to_float(raw)
                if d is not None:
                    if 0<=d<=1:decimals[stage].append(d)
                    else:errors.append({"row_idx":wrapped.get("row_idx"),"error":f"DECIMAL_STAGE_OUT_OF_RANGE:{d}"})
    def summary(v:list[float])->dict[str,Any]:
        if not v:return {"count":0}
        o=sorted(v);return {"count":len(o),"min":o[0],"p10":_percentile(o,.1),"p25":_percentile(o,.25),"median":median(o),"mean":mean(o),"p75":_percentile(o,.75),"p90":_percentile(o,.9),"max":o[-1]}
    turning=sorted(decimals.get("turning red",[]));hist=Counter(f"{v:.1f}" for v in turning);candidates=[]
    for t in (.4,.5,.6,.7):candidates.append({"threshold":t,"maturity2_count_if_below":sum(v<t for v in turning),"maturity3_count_if_at_or_above":sum(v>=t for v in turning)})
    return {"source_id":"DATA-RIP-002","dataset":KGCV_DATASET,"transport":"HUGGINGFACE_DATASET_VIEWER_METADATA_ONLY","rows_expected":total,"rows_seen":seen,"annotation_count":anns,"class_counts":dict(sorted(classes.items())),"source_counts":dict(sorted(sources.items())),"decimal_stage_summary":{s:summary(v) for s,v in sorted(decimals.items())},"turning_red":{"count":len(turning),"decimal_histogram":dict(sorted(hist.items(),key=lambda x:float(x[0]))),"candidate_threshold_diagnostics":candidates,"mapping_status":"FIELD_CALIBRATION_REQUIRED","policy":"DO_NOT_PROMOTE_HEURISTIC_THRESHOLD"},"errors":errors,"status":"AUDITED" if seen==total and not errors else "REVIEW_REQUIRED"}

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);p.add_argument("--page-size",type=int,default=100);a=p.parse_args()
    try:report=audit_kgcv_hf_metadata(page_size=a.page_size)
    except Exception as exc:
        report={"source_id":"DATA-RIP-002","dataset":KGCV_DATASET,"status":"SOURCE_UNAVAILABLE","error":str(exc),"policy":"DO_NOT_FABRICATE_AUDIT_RESULT"}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report["status"]=="AUDITED" else 2
if __name__=="__main__":raise SystemExit(main())
