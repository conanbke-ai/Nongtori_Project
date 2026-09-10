from __future__ import annotations

import argparse
import json
from pathlib import Path

from .archive import extract_archive
from .audit import audit_directory
from .dedup import deduplicate_manifest
from .downloader import DatasetDownloader
from .normalize import normalize_external_csv, normalize_field_csv
from .registry import DatasetRegistry
from .snapshot import create_snapshot
from .split import create_split_manifest
from .training_snapshot import create_training_snapshot

DEFAULT_SOURCES = Path(__file__).with_name("sources")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nongtori-data", description="Nongtori reproducible dataset pipeline")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p = sub.add_parser("download"); p.add_argument("source_id"); p.add_argument("--raw-root", type=Path, required=True)
    p = sub.add_parser("extract"); p.add_argument("--archive", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("audit"); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("snapshot"); p.add_argument("source_id"); p.add_argument("--audit-dir", type=Path, required=True); p.add_argument("--snapshot-root", type=Path, required=True); p.add_argument("--snapshot-id", required=True)
    p = sub.add_parser("normalize-field"); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--source-id", default="DATA-FIELD-001")
    p = sub.add_parser("normalize-external"); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--mapping", type=Path, required=True); p.add_argument("--label-column", default="label"); p.add_argument("--sample-id-column", default="sample_id"); p.add_argument("--asset-column", default="asset_path"); p.add_argument("--hash-column", default="content_sha256"); p.add_argument("--group-column", default="group_id")
    p = sub.add_parser("dedup"); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("split"); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--seed", default="nongtori-v1"); p.add_argument("--train-ratio", type=float, default=0.70); p.add_argument("--val-ratio", type=float, default=0.15); p.add_argument("--test-ratio", type=float, default=0.15)
    p = sub.add_parser("training-snapshot"); p.add_argument("--snapshot-id", required=True); p.add_argument("--normalized", type=Path, required=True); p.add_argument("--dedup", type=Path, required=True); p.add_argument("--split", type=Path, required=True); p.add_argument("--snapshot-root", type=Path, required=True); p.add_argument("--label-mapping-version", required=True); p.add_argument("--schema-version", default="v1"); p.add_argument("--source-id", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = DatasetRegistry(args.sources)
    if args.command == "list":
        for source in registry.list(): print(f"{source.source_id}\t{source.provider}\t{source.status}\t{source.title}")
        return 0
    if args.command == "download":
        result = DatasetDownloader().download(registry.get(args.source_id), args.raw_root); print(json.dumps({"source_id": result.source_id, "output_dir": str(result.output_dir), "files": len(result.files), "metadata": result.metadata}, ensure_ascii=False, indent=2)); return 0
    if args.command == "extract":
        files = extract_archive(args.archive, args.output); print(json.dumps({"output_dir": str(args.output), "files": len(files)}, ensure_ascii=False, indent=2)); return 0
    if args.command == "audit": print(json.dumps(audit_directory(args.input, args.output), ensure_ascii=False, indent=2)); return 0
    if args.command == "snapshot":
        source = registry.get(args.source_id); print(create_snapshot(args.snapshot_id, source.source_id, source.version_or_revision or "unversioned", args.audit_dir, args.snapshot_root)); return 0
    if args.command == "normalize-field": print(normalize_field_csv(args.input, args.output, source_id=args.source_id)); return 0
    if args.command == "normalize-external": print(normalize_external_csv(args.input, args.output, args.mapping, label_column=args.label_column, sample_id_column=args.sample_id_column, asset_column=args.asset_column, hash_column=args.hash_column, group_column=args.group_column)); return 0
    if args.command == "dedup": print(json.dumps(deduplicate_manifest(args.input, args.output), ensure_ascii=False, indent=2)); return 0
    if args.command == "split": print(json.dumps(create_split_manifest(args.input, args.output, seed=args.seed, train_ratio=args.train_ratio, val_ratio=args.val_ratio, test_ratio=args.test_ratio), ensure_ascii=False, indent=2)); return 0
    print(create_training_snapshot(args.snapshot_id, normalized_manifest=args.normalized, dedup_manifest=args.dedup, split_manifest=args.split, snapshot_root=args.snapshot_root, label_mapping_version=args.label_mapping_version, schema_version=args.schema_version, source_ids=args.source_id)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
