from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, ImageDraw

REVIEW_BUCKETS = [
    "REVIEW_REQUIRED",
    "LABEL_AMBIGUITY",
    "CROP_QUALITY",
    "DOMAIN_VARIATION",
    "LIKELY_MODEL_LIMIT",
    "MODEL_DISAGREEMENT",
]


def _safe_name(index: int, source: Path) -> str:
    return f"{index:03d}_{source.name}"


def _make_preview(source: Path, dest: Path, label: str) -> None:
    image = Image.open(source).convert("RGB")
    image.thumbnail((360, 300))
    canvas = Image.new("RGB", (380, 340), "white")
    x = (380 - image.width) // 2
    y = 10 + (300 - image.height) // 2
    canvas.paste(image, (x, y))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 315), label[:55], fill="black")
    canvas.save(dest, quality=90)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--audit-dir", type=Path, default=Path("artifacts/ripeness-v008-error-audit"))
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/ripeness-v008-review-gallery"))
    args = p.parse_args()

    candidates_path = args.audit_dir / "review_candidates.json"
    if not candidates_path.exists():
        raise FileNotFoundError(f"missing V008 candidates: {candidates_path}")
    candidates: list[dict[str, Any]] = json.loads(candidates_path.read_text(encoding="utf-8"))
    if not candidates:
        raise RuntimeError("V008 review candidate list is empty")

    images_dir = args.output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    cards: list[str] = []

    for n, item in enumerate(candidates, start=1):
        source = Path(item["path"])
        if not source.exists():
            raise FileNotFoundError(f"candidate crop missing: {source}")
        filename = _safe_name(n, source)
        preview = images_dir / filename
        label = f'#{n} true={item["true_label"]} R={item["resnet_pred"]} E={item["efficientnet_pred"]}'
        _make_preview(source, preview, label)
        row = {
            "review_id": n,
            "sample_index": item["sample_index"],
            "bucket": item["bucket"],
            "true_label": item["true_label"],
            "resnet_pred": item["resnet_pred"],
            "resnet_confidence": round(float(item["resnet_confidence"]), 6),
            "efficientnet_pred": item["efficientnet_pred"],
            "efficientnet_confidence": round(float(item["efficientnet_confidence"]), 6),
            "source_asset": item.get("source_asset", ""),
            "crop_path": str(source),
            "preview_path": str(preview),
            "review_category": "REVIEW_REQUIRED",
            "review_note": "",
            "label_action": "KEEP",
        }
        rows.append(row)
        options = "".join(f'<option value="{html.escape(v)}">{html.escape(v)}</option>' for v in REVIEW_BUCKETS)
        cards.append(f'''<article class="card">
<img src="images/{html.escape(filename)}" loading="lazy">
<div class="meta"><b>#{n}</b> · {html.escape(str(item["bucket"]))}</div>
<div>GT <b>{item["true_label"]}</b> · ResNet {item["resnet_pred"]} ({float(item["resnet_confidence"]):.3f}) · EfficientNet {item["efficientnet_pred"]} ({float(item["efficientnet_confidence"]):.3f})</div>
<div class="path">{html.escape(str(item.get("source_asset", "")))}</div>
<label>Review category <select data-review="{n}">{options}</select></label>
<textarea data-note="{n}" placeholder="육안 판정 근거 / 조명 / 가림 / crop / label 경계 메모"></textarea>
</article>''')

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "review_sheet.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)

    instructions = {
        "candidate_count": len(rows),
        "review_categories": REVIEW_BUCKETS,
        "rule": "Do not change frozen labels from this gallery. Record review evidence first; any label correction requires a separate adjudication/revision workflow.",
        "priority": ["SHARED_SAME_ERROR", "RESNET_ONLY_CORRECT", "EFFICIENTNET_ONLY_CORRECT"],
    }
    (args.output_dir / "review_manifest.json").write_text(json.dumps(instructions, ensure_ascii=False, indent=2), encoding="utf-8")

    page = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>Nongtori V008 Hard Example Review</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;background:#f6f7f8;color:#222}}h1{{margin-bottom:4px}}.summary{{margin-bottom:20px;color:#555}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(390px,1fr));gap:16px}}.card{{background:white;border:1px solid #ddd;border-radius:12px;padding:12px;box-shadow:0 1px 4px #0001}}img{{display:block;max-width:100%;margin:auto}}.meta{{margin-top:8px}}.path{{font-size:12px;color:#666;overflow-wrap:anywhere;margin:6px 0}}select,textarea{{width:100%;box-sizing:border-box;margin-top:6px}}textarea{{height:70px}}.warn{{padding:10px;background:#fff4ce;border-radius:8px;margin:12px 0 20px}}</style></head><body>
<h1>🌱 Nongtori · V008 M0/M1 Hard-example Review</h1>
<div class="summary">{len(rows)} validation candidates · frozen validation evidence · test set not used</div>
<div class="warn"><b>주의:</b> 이 화면에서 원본 label을 직접 수정하지 않는다. 육안 review evidence만 기록하고 label 변경은 별도 adjudication/revision 절차로 처리한다.</div>
<div class="grid">{''.join(cards)}</div>
<script>document.querySelectorAll('select,textarea').forEach(el=>el.addEventListener('change',()=>{{localStorage.setItem('v008-'+el.dataset.review+'-'+(el.tagName==='SELECT'?'category':'note'),el.value)}}));document.querySelectorAll('select,textarea').forEach(el=>{{const k='v008-'+el.dataset.review+'-'+(el.tagName==='SELECT'?'category':'note');const v=localStorage.getItem(k);if(v!==null)el.value=v}});</script>
</body></html>'''
    (args.output_dir / "review_gallery.html").write_text(page, encoding="utf-8")
    print(f"Review candidates : {len(rows)}")
    print(f"Gallery           : {args.output_dir / 'review_gallery.html'}")
    print(f"Review sheet      : {csv_path}")
    print(f"Manifest          : {args.output_dir / 'review_manifest.json'}")


if __name__ == "__main__":
    main()
