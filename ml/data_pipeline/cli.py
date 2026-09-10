from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import audit_directory
from .downloader import DatasetDownloader
from .registry import DatasetRegistry
from .snapshot import create_snapshot

DEFAULT_SOURCES = Path(__file__).with_name("sources")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nongtori-data", description="Nongtori reproducible dataset pipeline")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p = sub.add_parser("download"); p.add_argument("source_id"); p.add_argument("--raw-root", type=Path, required=True)
    p = sub.add_parser("audit"); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("snapshot"); p.add_argument("source_id"); p.add_argument("--audit-dir", type=Path, required=True); p.add_argument("--snapshot-root", type=Path, required=True); p.add_argument("--snapshot-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = DatasetRegistry(args.sources)
    if args.command == "list":
        for source in registry.list():
            print(f"{source.source_id}\t{source.provider}\t{source.status}\t{source.title}")
        return 0
    if args.command == "download":
        result = DatasetDownloader().download(registry.get(args.source_id), args.raw_root)
        print(json.dumps({"source_id": result.source_id, "output_dir": str(result.output_dir), "files": len(result.files), "metadata": result.metadata}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "audit":
        print(json.dumps(audit_directory(args.input, args.output), ensure_ascii=False, indent=2))
        return 0
    source = registry.get(args.source_id)
    path = create_snapshot(args.snapshot_id, source.source_id, source.version_or_revision or "unversioned", args.audit_dir, args.snapshot_root)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
