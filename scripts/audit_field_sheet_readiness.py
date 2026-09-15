from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.data_pipeline.field_readiness import audit_csv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit Nongtori field Sheet CSV readiness without modifying source data."
    )
    parser.add_argument("csv", type=Path, help="CSV export of 농가_딸기데이터")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/field-data-readiness"),
    )
    args = parser.parse_args()
    summary = audit_csv(args.csv, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
