"""Immutable local aT captures and one explicitly bounded collection command."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from .at_auction import (
    ADAPTER_VERSION, AuctionCodebook, AuctionEdition, AuctionError, AuctionQuery, PageCapture,
    fetch_edition, https_transport, load_codebook, parse_edition, validate_query,
)
from .auction_history import (
    WithdrawalEvidence, reconcile_auction_editions, summarize_population, write_daily_prices,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS auction_editions (
    query TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    codebook_sha256 TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    pages TEXT NOT NULL,
    PRIMARY KEY (query, captured_at)
)
"""


def _query_key(query: AuctionQuery) -> str:
    return json.dumps(query.filters(), sort_keys=True)


def _codebook_key(codebook: AuctionCodebook) -> str:
    snapshot = {
        field: sorted(values) if isinstance(values, frozenset) else values
        for field, values in asdict(codebook).items()
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def _parse_query(values: dict) -> AuctionQuery:
    return AuctionQuery(
        date.fromisoformat(values["trd_clcln_ymd"]), values["whsl_mrkt_cd"],
        values.get("corp_cd"), values.get("gds_mclsf_cd"),
        values.get("gds_lclsf_cd"), values.get("gds_sclsf_cd"),
    )


def _encode_pages(edition: AuctionEdition) -> str:
    return json.dumps([
        {
            "number": page.number,
            "size": page.size,
            "received_at": page.received_at.isoformat(),
            "payload": base64.b64encode(page.payload).decode("ascii"),
            "sha256": page.sha256,
        }
        for page in edition.captures
    ], separators=(",", ":"))


def _decode_edition(record: tuple[str, ...], codebook: AuctionCodebook) -> AuctionEdition:
    stored_query, captured_at, source_sha256, codebook_sha256, adapter_version, pages = record
    if codebook_sha256 != _codebook_key(codebook):
        raise AuctionError("Archived capture requires its original standard-code reference")
    if adapter_version != ADAPTER_VERSION:
        raise AuctionError("Archived capture requires a compatible adapter version")
    try:
        query = _parse_query(json.loads(stored_query))
        captures = []
        for page in json.loads(pages):
            capture = PageCapture(
                page["number"], page["size"], datetime.fromisoformat(page["received_at"]),
                base64.b64decode(page["payload"], validate=True),
            )
            if capture.sha256 != page["sha256"]:
                raise AuctionError("Archived page hash mismatch")
            captures.append(capture)
    except (TypeError, KeyError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, AuctionError):
            raise
        raise AuctionError("Malformed aT archive") from error
    edition = parse_edition(query, tuple(captures), codebook)
    if _query_key(query) != stored_query or edition.source_sha256 != source_sha256 or edition.available_at.isoformat() != captured_at:
        raise AuctionError("Archived request, hash or capture timestamp mismatch")
    return edition


def collect(
    path: Path,
    query: AuctionQuery,
    codebook: AuctionCodebook,
    fetch: Callable[[], AuctionEdition],
    *,
    refresh: bool = False,
) -> tuple[str, AuctionEdition]:
    """Reuse the latest complete exact request unless an explicit refresh is requested."""
    validate_query(query, codebook)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(descriptor)
    with closing(sqlite3.connect(path, timeout=10)) as connection, connection:
        connection.execute(SCHEMA)
        # A second process waits or fails instead of also spending calls on this archive.
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute(
            "SELECT query, captured_at, source_sha256, codebook_sha256, adapter_version, pages FROM auction_editions "
            "WHERE query = ? ORDER BY captured_at DESC LIMIT 1",
            (_query_key(query),),
        ).fetchone()
        existing = _decode_edition(previous, codebook) if previous is not None else None
        if existing is not None and not refresh:
            return "REUSED", existing
        candidate = fetch()
        verified = parse_edition(query, candidate.captures, codebook)
        if candidate != verified:
            raise AuctionError("Fetched edition does not match its captured pages")
        if existing is not None:
            if candidate.source_sha256 == existing.source_sha256:
                return "UNCHANGED", existing
            if candidate.available_at <= existing.available_at:
                raise AuctionError("A new capture must follow the previous capture")
        connection.execute(
            "INSERT INTO auction_editions VALUES (?, ?, ?, ?, ?, ?)",
            (_query_key(query), candidate.available_at.isoformat(), candidate.source_sha256,
             _codebook_key(codebook), ADAPTER_VERSION, _encode_pages(candidate)),
        )
        return "CAPTURED", candidate


def load_editions(path: Path, codebook: AuctionCodebook) -> tuple[AuctionEdition, ...]:
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        rows = connection.execute(
            "SELECT query, captured_at, source_sha256, codebook_sha256, adapter_version, pages FROM auction_editions "
            "ORDER BY captured_at, query"
        )
        return tuple(_decode_edition(row, codebook) for row in rows)


def _describe(edition: AuctionEdition) -> dict:
    return {
        "request": edition.query.filters(),
        "first_confirmed_available_at": edition.available_at.isoformat(),
        "source_sha256": edition.source_sha256,
        "standard_code_source_sha256": edition.code_evidence_sha256,
        "adapter_version": ADAPTER_VERSION,
        "page_hashes": [page.sha256 for page in edition.captures],
        "input_rows": edition.input_rows,
        "duplicate_rows": edition.duplicate_rows,
        "admitted_trades": len(edition.trades),
        "rejections": dict(Counter(row.reason for row in edition.rejections)),
    }


def _collect(args: argparse.Namespace, codebook: AuctionCodebook) -> dict:
    query = AuctionQuery(args.settlement_day, args.market, args.corporation, args.product,
                         args.category, args.cultivar)

    def fetch() -> AuctionEdition:
        transport = https_transport(os.environ.get("NONGTORI_AT_SERVICE_KEY"), args.interval_seconds)
        return fetch_edition(query, codebook, transport, size=args.page_size, max_pages=args.max_pages)

    status, edition = collect(args.archive, query, codebook, fetch, refresh=args.refresh)
    return {"status": status, **_describe(edition)}


def _read_withdrawals(manifest: Path) -> tuple[WithdrawalEvidence, ...]:
    try:
        entries = json.loads(manifest.read_bytes())
        if not isinstance(entries, list):
            raise ValueError
        confirmations = []
        for item in entries:
            query = _parse_query(item["query"])
            source = manifest.parent / item["evidence_file"]
            with source.open("rb") as evidence:
                digest = hashlib.file_digest(evidence, "sha256").hexdigest()
            if digest != item["source_sha256"]:
                raise AuctionError("Withdrawal evidence file hash mismatch")
            confirmations.append(WithdrawalEvidence(
                query, item["edition_sha256"], tuple(item["trade_id"]),
                datetime.fromisoformat(item["observed_at"]), digest,
                datetime.fromisoformat(item["edition_available_at"]) if "edition_available_at" in item else None,
            ))
        return tuple(confirmations)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, AuctionError):
            raise
        raise AuctionError("Malformed withdrawal manifest") from error


def _export(args: argparse.Namespace, codebook: AuctionCodebook) -> dict:
    target = (args.category, args.product, args.cultivar)
    if target not in codebook.products:
        raise AuctionError("Target cultivar is absent from the standard-code reference")
    editions = load_editions(args.archive, codebook)
    withdrawals = _read_withdrawals(args.withdrawals) if args.withdrawals else ()
    history = reconcile_auction_editions(editions, withdrawals=withdrawals)
    product = f"{args.category}:{args.product}"
    prices = tuple(row for row in history.prices if (row.series.product, row.series.cultivar) == (product, args.cultivar))
    if not any(row.price_krw_per_kg is not None for row in prices):
        raise AuctionError("No eligible trade history for the requested cultivar")
    population = summarize_population(history, cultivar=args.cultivar, product=product)
    output = io.StringIO(newline="")
    write_daily_prices(output, prices)
    payload = output.getvalue().encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as temporary:
        staged = Path(temporary.name)
        try:
            temporary.write(payload)
            temporary.close()
            os.link(staged, args.output)  # Publish the completed file without replacing an existing export.
        finally:
            staged.unlink(missing_ok=True)
    return {
        "standard_code_source_sha256": codebook.evidence_sha256,
        "normalized_csv_sha256": hashlib.sha256(payload).hexdigest(),
        "normalized_rows": len(prices),
        "population": population,
        "counts": history.counts,
        "captures": [_describe(edition) for edition in editions],
        "source_manifest": history.manifest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True, help="Private local SQLite path")
    parser.add_argument("--codebook", type=Path, required=True, help="Normalized, code-exact reference JSON")
    parser.add_argument("--code-evidence", type=Path, required=True, help="Immutable standard-code source or source manifest")
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("collect", help="Collect one market and settlement date with an approved account budget")
    capture.add_argument("--settlement-day", required=True, type=date.fromisoformat)
    capture.add_argument("--market", required=True)
    capture.add_argument("--corporation")
    capture.add_argument("--category", help="aT large classification code")
    capture.add_argument("--product", help="aT middle classification code")
    capture.add_argument("--cultivar", help="aT small classification code")
    capture.add_argument("--page-size", type=int, default=100)
    capture.add_argument("--max-pages", required=True, type=int)
    capture.add_argument("--interval-seconds", required=True, type=float)
    capture.add_argument("--refresh", action="store_true", help="Explicit new capture for an existing exact request")
    commands.add_parser("inspect", help="Validate stored captures and report source coverage without calling aT")
    export = commands.add_parser("export", help="Export a verified, versioned cultivar history without calling aT")
    export.add_argument("--category", required=True)
    export.add_argument("--product", required=True)
    export.add_argument("--cultivar", required=True)
    export.add_argument("--withdrawals", type=Path)
    export.add_argument("--output", required=True, type=Path, help="New normalized CSV path")
    try:
        args = parser.parse_args()
        codebook = load_codebook(args.codebook.read_bytes())
        with args.code_evidence.open("rb") as evidence:
            if hashlib.file_digest(evidence, "sha256").hexdigest() != codebook.evidence_sha256:
                raise AuctionError("Standard-code source hash does not match its reference JSON")
        if args.command == "collect":
            report = _collect(args, codebook)
        elif args.command == "export":
            report = _export(args, codebook)
        else:
            report = {"editions": [_describe(edition) for edition in load_editions(args.archive, codebook)]}
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
