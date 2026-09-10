from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .annotation_audit import audit_kgcv_json, audit_strawberry_ds_yolo, write_audit_report
from .archive import extract_archive
from .audit import audit_directory
from .dedup import deduplicate_manifest
from .downloader import DatasetDownloader
from .field_audit import audit_field_csv
from .incremental import incremental_scan_csv
from .normalize import normalize_external_csv, normalize_field_csv
from .registry import DatasetRegistry
from .rename_manifest import preflight_rename, write_preflight_summary, write_rename_manifest
from .snapshot import create_snapshot
from .split import create_split_manifest
from .training_snapshot import create_training_snapshot
from .working_assets import materialize_working_assets, read_manifest, write_materialized_manifest, write_rollback_manifest

DEFAULT_SOURCES = Path(__file__).with_name("sources")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nongtori-data", description="Nongtori reproducible dataset pipeline")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p = sub.add_parser("download"); p.add_argument("source_id"); p.add_argument("--raw-root", type=Path, required=True)
    p = sub.add_parser("extract"); p.add_argument("--archive", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("audit"); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("audit-strawberry-ds"); p.add_argument("--labels-dir", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("audit-kgcv"); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("snapshot"); p.add_argument("source_id"); p.add_argument("--audit-dir", type=Path, required=True); p.add_argument("--snapshot-root", type=Path, required=True); p.add_argument("--snapshot-id", required=True)
    p = sub.add_parser("incremental-scan"); p.add_argument("--input", type=Path, required=True); p.add_argument("--ledger", type=Path, required=True); p.add_argument("--output-ledger", type=Path, required=True); p.add_argument("--key-field", action="append", default=[]); p.add_argument("--ignore-field", action="append", default=[])
    p = sub.add_parser("field-audit"); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path)
    p = sub.add_parser("rename-preflight"); p.add_argument("--metadata", type=Path, required=True); p.add_argument("--source-dir", type=Path, required=True); p.add_argument("--farm-id", required=True); p.add_argument("--capture-session-id", required=True); p.add_argument("--manifest", type=Path, required=True); p.add_argument("--summary", type=Path, required=True)
    p = sub.add_parser("materialize-working-assets"); p.add_argument("--manifest", type=Path, required=True); p.add_argument("--source-dir", type=Path, required=True); p.add_argument("--object-store-root", type=Path, required=True); p.add_argument("--session-root", type=Path, required=True); p.add_argument("--output-manifest", type=Path, required=True); p.add_argument("--rollback-manifest", type=Path, required=True)
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
    if args.command == "audit-strawberry-ds":
        report = audit_strawberry_ds_yolo(args.labels_dir); write_audit_report(report, args.output); print(json.dumps(report, ensure_ascii=False, indent=2)); return 0
    if args.command == "audit-kgcv":
        report = audit_kgcv_json(args.input); write_audit_report(report, args.output); print(json.dumps(report, ensure_ascii=False, indent=2)); return 0
    if args.command == "snapshot":
        source = registry.get(args.source_id); print(create_snapshot(args.snapshot_id, source.source_id, source.version_or_revision or "unversioned", args.audit_dir, args.snapshot_root)); return 0
    if args.command == "incremental-scan":
        key_fields = tuple(args.key_field) if args.key_field else ("Farm", "ID")
        print(json.dumps(incremental_scan_csv(args.input, args.ledger, args.output_ledger, key_fields=key_fields, ignored_fields=args.ignore_field), ensure_ascii=False, indent=2)); return 0
    if args.command == "field-audit": print(json.dumps(audit_field_csv(args.input, args.output), ensure_ascii=False, indent=2)); return 0
    if args.command == "rename-preflight":
        with args.metadata.open(encoding="utf-8-sig", newline="") as f: metadata_rows = list(csv.DictReader(f))
        manifest, summary = preflight_rename(metadata_rows, args.source_dir, farm_id=args.farm_id, capture_session_id=args.capture_session_id)
        write_rename_manifest(manifest, args.manifest); write_preflight_summary(summary, args.summary); print(json.dumps(summary, ensure_ascii=False, indent=2)); return 0
    if args.command == "materialize-working-assets":
        rows, counts = materialize_working_assets(read_manifest(args.manifest), args.source_dir, args.object_store_root, args.session_root)
        write_materialized_manifest(rows, args.output_manifest); write_rollback_manifest(rows, args.rollback_manifest); print(json.dumps(counts, ensure_ascii=False, indent=2)); return 0
    if args.command == "normalize-field": print(normalize_field_csv(args.input, args.output, source_id=args.source_id)); return 0
    if args.command == "normalize-external": print(normalize_external_csv(args.input, args.output, args.mapping, label_column=args.label_column, sample_id_column=args.sample_id_column, asset_column=args.asset_column, hash_column=args.hash_column, group_column=args.group_column)); return 0
    if args.command == "dedup": print(json.dumps(deduplicate_manifest(args.input, args.output), ensure_ascii=False, indent=2)); return 0
    if args.command == "split": print(json.dumps(create_split_manifest(args.input, args.output, seed=args.seed, train_ratio=args.train_ratio, val_ratio=args.val_ratio, test_ratio=args.test_ratio), ensure_ascii=False, indent=2)); return 0
    print(create_training_snapshot(args.snapshot_id, normalized_manifest=args.normalized, dedup_manifest=args.dedup, split_manifest=args.split, snapshot_root=args.snapshot_root, label_mapping_version=args.label_mapping_version, schema_version=args.schema_version, source_ids=args.source_id)); return 0


if __name__ == "__main__": raise SystemExit(main())
