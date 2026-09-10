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
    try: parsed = float(value)
    except (TypeError, ValueError): return None
    return parsed if math.isfinite(parsed) else None


def _percentile(values: list[float], q: float) -> float | None:
    if not values: return None
    ordered = sorted(values)
    if len(ordered) == 1: return ordered[0]
    pos = (len(ordered) - 1) * q; lo = math.floor(pos); hi = math.ceil(pos)
    if lo == hi: return ordered[lo]
    weight = pos - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def _fetch_page(*, offset: int, length: int, timeout: int = 60, retries: int = 3) -> dict[str, Any]:
    params = urllib.parse.urlencode({"dataset": KGCV_DATASET, "config": KGCV_CONFIG, "split": KGCV_SPLIT, "offset": offset, "length": length})
    url = f"{HF_ROWS_ENDPOINT}?{params}"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Nongtori-KGCV-Audit/1.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response: return json.load(response)
        except Exception as exc:
            last_error = exc
            if attempt + 1 < retries: time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch Hugging Face rows offset={offset}: {last_error}")


def audit_kgcv_hf_metadata(*, page_size: int = 100) -> dict[str, Any]:
    if not 1 <= page_size <= 100: raise ValueError("page_size must be between 1 and 100")
    first = _fetch_page(offset=0, length=page_size)
    total_rows = int(first.get("num_rows_total", 0)); pages = [first]
    for offset in range(page_size, total_rows, page_size): pages.append(_fetch_page(offset=offset, length=min(page_size, total_rows-offset)))
    class_counts: Counter[str] = Counter(); source_counts: Counter[str] = Counter(); decimal_values: dict[str,list[float]] = defaultdict(list)
    errors=[]; annotation_count=0; rows_seen=0
    for page in pages:
        for wrapped in page.get("rows", []):
            rows_seen += 1; row=wrapped.get("row",{}) or {}; source_counts[str(row.get("source","UNKNOWN"))]+=1; objects=row.get("objects",{}) or {}
            categories=objects.get("categories",[]) or []; decimals=objects.get("decimal_stage",[]) or []
            if len(categories)!=len(decimals): errors.append({"row_idx":wrapped.get("row_idx"),"error":"OBJECT_ARRAY_LENGTH_MISMATCH"}); continue
            for class_id, decimal_raw in zip(categories,decimals):
                try: class_id=int(class_id)
                except (TypeError,ValueError): errors.append({"row_idx":wrapped.get("row_idx"),"error":f"INVALID_CLASS_ID:{class_id}"}); continue
                stage=KGCV_CLASS_NAMES.get(class_id)
                if stage is None: errors.append({"row_idx":wrapped.get("row_idx"),"error":f"UNKNOWN_CLASS_ID:{class_id}"}); continue
                class_counts[stage]+=1; annotation_count+=1; decimal=_to_float(decimal_raw)
                if decimal is not None:
                    if 0<=decimal<=1: decimal_values[stage].append(decimal)
                    else: errors.append({"row_idx":wrapped.get("row_idx"),"error":f"DECIMAL_STAGE_OUT_OF_RANGE:{decimal}"})
    def summarize(values:list[float])->dict[str,Any]:
        if not values:return {"count":0}
        o=sorted(values); return {"count":len(o),"min":o[0],"p10":_percentile(o,.1),"p25":_percentile(o,.25),"median":median(o),"mean":mean(o),"p75":_percentile(o,.75),"p90":_percentile(o,.9),"max":o[-1]}
    turning=sorted(decimal_values.get("turning red",[])); hist=Counter(f"{v:.1f}" for v in turning)
    candidates=[]
    for threshold in (.4,.5,.6,.7): candidates.append({"threshold":threshold,"maturity2_count_if_below":sum(v<threshold for v in turning),"maturity3_count_if_at_or_above":sum(v>=threshold for v in turning)})
    return {"source_id":"DATA-RIP-002","dataset":KGCV_DATASET,"transport":"HUGGINGFACE_DATASET_VIEWER_METADATA_ONLY","rows_expected":total_rows,"rows_seen":rows_seen,"annotation_count":annotation_count,"class_counts":dict(sorted(class_counts.items())),"source_counts":dict(sorted(source_counts.items())),"decimal_stage_summary":{s:summarize(v) for s,v in sorted(decimal_values.items())},"turning_red":{"count":len(turning),"decimal_histogram":dict(sorted(hist.items(),key=lambda x:float(x[0]))),"candidate_threshold_diagnostics":candidates,"mapping_status":"FIELD_CALIBRATION_REQUIRED","policy":"DO_NOT_PROMOTE_HEURISTIC_THRESHOLD"},"errors":errors,"status":"AUDITED" if rows_seen==total_rows and not errors else "REVIEW_REQUIRED"}


def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,required=True); parser.add_argument("--page-size",type=int,default=100); args=parser.parse_args()
    report=audit_kgcv_hf_metadata(page_size=args.page_size); args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps(report,ensure_ascii=False,indent=2)); return 0 if report["status"]=="AUDITED" else 2

if __name__=="__main__": raise SystemExit(main())
