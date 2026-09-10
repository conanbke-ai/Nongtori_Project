from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .hf_metadata_audit import _fetch_page


def _fetch_page_resilient(*, offset: int, length: int, attempts: int = 8) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return _fetch_page(offset=offset, length=length)
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"failed to fetch metadata page offset={offset} after {attempts} attempts: {last}")


def _image_src(row: dict[str, Any]) -> str:
    image = row.get("image") or {}
    if isinstance(image, dict) and image.get("src"):
        return str(image["src"])
    raise ValueError("Dataset Viewer row has no image.src")


def hash_remote_asset(url: str, *, timeout: int = 120, attempts: int = 5) -> tuple[str, int]:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Nongtori-KGCV-AssetHash/1.0"})
            digest = hashlib.sha256(); size = 0
            with urllib.request.urlopen(request, timeout=timeout) as response:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk: break
                    digest.update(chunk); size += len(chunk)
            return digest.hexdigest(), size
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts: time.sleep(min(20, 2 ** attempt))
    raise RuntimeError(f"asset download failed after {attempts} attempts: {last}")


def hash_shard(*, shard_index: int, shard_count: int, output: Path, page_size: int = 100) -> dict[str, Any]:
    if not 0 <= shard_index < shard_count: raise ValueError("invalid shard index")
    first = _fetch_page_resilient(offset=0, length=1); total = int(first.get("num_rows_total", 0))
    rows=[]; errors=[]
    for offset in range(shard_index * page_size, total, shard_count * page_size):
        length=min(page_size,total-offset); page=_fetch_page_resilient(offset=offset,length=length)
        for wrapped in page.get("rows",[]):
            row_idx=int(wrapped["row_idx"]); row=wrapped.get("row",{}) or {}
            try:
                sha256,size=hash_remote_asset(_image_src(row)); rows.append({"row_idx":row_idx,"content_sha256":sha256,"size_bytes":size,"source":str(row.get("source","UNKNOWN"))})
            except Exception as exc: errors.append({"row_idx":row_idx,"error":str(exc)})
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps({"shard_index":shard_index,"shard_count":shard_count,"total_rows":total,"rows":rows,"errors":errors},ensure_ascii=False,indent=2),encoding="utf-8")
    return {"hashed":len(rows),"errors":len(errors),"total_rows":total}


def _assign_split(groups:list[str],*,seed:int=20260910,train_ratio:float=.70,valid_ratio:float=.15)->dict[str,str]:
    ordered=sorted(groups); random.Random(seed).shuffle(ordered); n=len(ordered); train_end=round(n*train_ratio); valid_end=train_end+round(n*valid_ratio)
    return {group:("train" if i<train_end else "valid" if i<valid_end else "test") for i,group in enumerate(ordered)}


def aggregate(*,shard_dir:Path,normalized_manifest:Path,output_manifest:Path,summary_path:Path)->dict[str,Any]:
    asset_rows={}; errors=[]
    for path in sorted(Path(shard_dir).glob("*.json")):
        data=json.loads(path.read_text(encoding="utf-8")); errors.extend(data.get("errors",[]))
        for row in data.get("rows",[]): asset_rows[int(row["row_idx"])]=row
    with Path(normalized_manifest).open(encoding="utf-8",newline="") as f: samples=list(csv.DictReader(f))
    hash_to_rows=defaultdict(list)
    for row_idx,asset in asset_rows.items(): hash_to_rows[str(asset["content_sha256"])].append(row_idx)
    group_for_row={}
    for sha,row_indices in hash_to_rows.items():
        for row_idx in row_indices: group_for_row[row_idx]=f"sha256:{sha}"
    split_by_hash=_assign_split(list(hash_to_rows))
    out_fields=(list(samples[0].keys())+["asset_size_bytes","split_group","split"]) if samples else []
    output_manifest.parent.mkdir(parents=True,exist_ok=True); counts=Counter(); snapshot_eligible=0
    with output_manifest.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=out_fields); writer.writeheader()
        for sample in samples:
            row_idx=int(sample["source_row_idx"]); asset=asset_rows.get(row_idx)
            if asset:
                sha=str(asset["content_sha256"]); sample["content_sha256"]=sha; sample["asset_status"]="HASH_VERIFIED_REMOTE"; sample["asset_size_bytes"]=str(asset["size_bytes"]); sample["split_group"]=group_for_row[row_idx]; sample["split"]=split_by_hash[sha]
                if sample.get("task_eligible")=="true": sample["snapshot_eligible"]="true"; snapshot_eligible+=1
                counts[sample["split"]]+=1
            else: sample["asset_size_bytes"]=""; sample["split_group"]=""; sample["split"]=""
            writer.writerow(sample)
    duplicate_hashes={sha:rows for sha,rows in hash_to_rows.items() if len(rows)>1}
    summary={"physical_rows_expected":1477,"physical_rows_hashed":len(asset_rows),"hash_errors":errors,"unique_content_hashes":len(hash_to_rows),"duplicate_content_hash_groups":len(duplicate_hashes),"duplicate_content_rows":sum(len(v) for v in duplicate_hashes.values()),"sample_rows":len(samples),"snapshot_eligible_sample_rows":snapshot_eligible,"sample_split_counts":dict(sorted(counts.items())),"split_policy":"CONTENT_SHA256_ATOMIC; all objects from one image and byte-identical images stay in one split","status":"READY_FOR_SNAPSHOT" if len(asset_rows)==1477 and not errors else "REVIEW_REQUIRED"}
    summary_path.parent.mkdir(parents=True,exist_ok=True); summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8"); return summary


def main()->int:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True)
    shard=sub.add_parser("hash-shard"); shard.add_argument("--shard-index",type=int,required=True); shard.add_argument("--shard-count",type=int,required=True); shard.add_argument("--output",type=Path,required=True)
    agg=sub.add_parser("aggregate"); agg.add_argument("--shard-dir",type=Path,required=True); agg.add_argument("--normalized-manifest",type=Path,required=True); agg.add_argument("--output-manifest",type=Path,required=True); agg.add_argument("--summary",type=Path,required=True)
    args=parser.parse_args()
    if args.command=="hash-shard":
        result=hash_shard(shard_index=args.shard_index,shard_count=args.shard_count,output=args.output); print(json.dumps(result,ensure_ascii=False)); return 0 if result["errors"]==0 else 2
    summary=aggregate(shard_dir=args.shard_dir,normalized_manifest=args.normalized_manifest,output_manifest=args.output_manifest,summary_path=args.summary); print(json.dumps(summary,ensure_ascii=False,indent=2)); return 0 if summary["status"]=="READY_FOR_SNAPSHOT" else 2

if __name__=="__main__": raise SystemExit(main())
