"""Replay complete auction captures into point-in-time daily price versions."""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from fractions import Fraction
from typing import TYPE_CHECKING, Iterable, TextIO

from .at_auction import PROVIDER
from .baseline import SERIES_FIELDS, DailyPrice
from .incremental_planner import KST, Series

if TYPE_CHECKING:
    from .at_auction import AuctionEdition, AuctionQuery, AuctionTrade


@dataclass(frozen=True)
class WithdrawalEvidence:
    query: AuctionQuery
    edition_sha256: str
    trade_id: tuple[str, ...]
    observed_at: datetime
    source_sha256: str
    edition_available_at: datetime | None = None


@dataclass(frozen=True)
class AuctionHistory:
    prices: tuple[DailyPrice, ...]
    manifest: dict[str, dict]
    counts: dict[str, int]


@dataclass(frozen=True)
class _SourcedTrade:
    trade: AuctionTrade
    source_sha256: str
    available_at: datetime


@dataclass(frozen=True)
class _ReplayEdition:
    edition: AuctionEdition
    available_at: datetime
    trades: dict[tuple[str, ...], AuctionTrade]
    withdrawals: dict[tuple[str, ...], WithdrawalEvidence]


def _instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Capture and confirmation times must have a UTC offset")
    return value.astimezone(timezone.utc)


def _digest(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Expected a lowercase SHA-256 digest")
    return value


def _query_key(query: AuctionQuery) -> tuple[str, ...]:
    return (
        query.settlement_day.isoformat(), query.market, query.corporation or "",
        query.category or "", query.product or "", query.cultivar or "",
    )


def _validate_scopes(editions: Iterable[AuctionEdition]) -> None:
    queries: dict[tuple[date, str], set[AuctionQuery]] = defaultdict(set)
    for edition in editions:
        query = edition.query
        queries[query.settlement_day, query.market].add(query)
    for market_day, scopes in queries.items():
        for left, right in itertools.combinations(scopes, 2):
            filters = ("corporation", "category", "product", "cultivar")
            differing = any(
                a is not None and b is not None and a != b
                for a, b in ((getattr(left, name), getattr(right, name)) for name in filters)
            )
            if not differing:
                raise ValueError(f"Overlapping acquisition scopes for {market_day[1]} on {market_day[0]}")


def _aggregate(active: dict[tuple[str, ...], _SourcedTrade]) -> tuple[float | None, float | None]:
    if not active:
        return None, None
    total_krw = sum(Fraction(row.trade.total_krw) for row in active.values())
    volume_kg = sum(Fraction(row.trade.volume_kg) for row in active.values())
    return float(total_krw / volume_kg), float(volume_kg)


def _validated_edition_rows(edition: AuctionEdition) -> dict[tuple[str, ...], AuctionTrade]:
    query = edition.query
    unexpected = Counter(
        row.reason for row in edition.rejections if row.reason != "NON_AUCTION_TRADE_TYPE"
    )
    if unexpected:
        detail = ", ".join(f"{reason}={count}" for reason, count in sorted(unexpected.items()))
        raise ValueError(f"Unsafe aT normalization for {query.market} on {query.settlement_day}: {detail}")
    rows = {}
    if (
        edition.duplicate_rows < 0
        or edition.duplicate_rows + len(edition.trades) + len(edition.rejections) != edition.input_rows
    ):
        raise ValueError("Edition counts do not match its deduplicated trades")
    for row in edition.trades:
        category, _, product = row.series.product.partition(":")
        if (
            not row.trade_id
            or row.trade_id in rows
            or row.series.provider != PROVIDER
            or row.series.market != query.market
            or query.corporation not in (None, row.series.corporation)
            or query.category not in (None, category)
            or query.product not in (None, product)
            or query.cultivar not in (None, row.series.cultivar)
            or type(row.trade_day) is not date
            or row.trade_day > query.settlement_day
            or row.trade_day > edition.available_at.astimezone(KST).date()
            or not row.total_krw.is_finite()
            or row.total_krw < 0
            or not row.volume_kg.is_finite()
            or row.volume_kg <= 0
        ):
            raise ValueError("Edition contains a duplicate or invalid trade for its request")
        rows[row.trade_id] = row
    return rows


def _prepare_replay(
    editions: tuple[AuctionEdition, ...], withdrawals: Iterable[WithdrawalEvidence],
) -> list[_ReplayEdition]:
    """Validate captured snapshots and place held versions at their proof time."""
    confirmations = {}
    for evidence in withdrawals:
        _digest(evidence.edition_sha256)
        _digest(evidence.source_sha256)
        capture_at = _instant(evidence.edition_available_at) if evidence.edition_available_at else None
        key = (evidence.query, evidence.edition_sha256, evidence.trade_id, capture_at)
        if key in confirmations:
            raise ValueError("Multiple withdrawal confirmations for one trade and edition")
        confirmations[key] = evidence

    ordered = sorted(editions, key=lambda item: (_instant(item.available_at), _query_key(item.query)))
    last: dict[AuctionQuery, _ReplayEdition] = {}
    sources: dict[AuctionQuery, dict[tuple[str, ...], _SourcedTrade]] = {}
    prepared = []
    for edition in ordered:
        query = edition.query
        capture_at = _instant(edition.available_at)
        if query.settlement_day > capture_at.astimezone(KST).date():
            raise ValueError("Capture precedes the settlement day")
        previous = last.get(query)
        if previous and capture_at == _instant(previous.edition.available_at):
            if previous.edition != edition:
                raise ValueError("Conflicting editions for one acquisition at the same time")
            continue
        digest = _digest(edition.source_sha256)
        fresh = _validated_edition_rows(edition)
        previous_rows = sources.setdefault(query, {})
        proofs = {}
        available_at = max(capture_at, previous.available_at) if previous else capture_at
        for trade_id in previous_rows.keys() - fresh.keys():
            key = (query, digest, trade_id)
            evidence = confirmations.pop((*key, capture_at), None)
            if evidence is None:
                evidence = confirmations.pop((*key, None), None)
            old = previous_rows.pop(trade_id)
            if evidence is None or _instant(evidence.observed_at) < old.available_at:
                raise ValueError("Unconfirmed disappearance from a complete auction edition")
            if evidence.source_sha256 in (digest, old.source_sha256):
                raise ValueError("Withdrawal needs evidence independent of the missing row")
            available_at = max(available_at, _instant(evidence.observed_at))
            proofs[trade_id] = evidence
        for trade_id, trade in fresh.items():
            old = previous_rows.get(trade_id)
            if old is None or old.trade != trade:
                previous_rows[trade_id] = _SourcedTrade(trade, digest, capture_at)
        replay_edition = _ReplayEdition(edition, available_at, fresh, proofs)
        last[query] = replay_edition
        prepared.append(replay_edition)
    if confirmations:
        raise ValueError("Withdrawal confirmation does not match a disappeared trade in the supplied editions")
    return sorted(prepared, key=lambda item: item.available_at)


def reconcile_auction_editions(
    editions: Iterable[AuctionEdition],
    *,
    withdrawals: Iterable[WithdrawalEvidence] = (),
) -> AuctionHistory:
    """Replay validated editions. Ambiguous disappearance blocks the whole export."""
    editions = tuple(editions)
    _validate_scopes(editions)
    ordered = _prepare_replay(editions, withdrawals)
    source_by_query: dict[AuctionQuery, dict[tuple[str, ...], _SourcedTrade]] = {}
    owner_by_trade: dict[tuple[str, ...], AuctionQuery] = {}
    active: dict[tuple[Series, date], dict[tuple[str, ...], _SourcedTrade]] = defaultdict(dict)
    published = set()
    prices = []
    manifest = {}
    input_rows = duplicate_rows = excluded_non_auction_rows = corrections = withdrawn_trades = 0
    for available_at, batch in itertools.groupby(ordered, key=lambda item: item.available_at):
        changes: dict[tuple[Series, date], set[tuple[str, str]]] = defaultdict(set)
        previous_sources: dict[tuple[Series, date], set[str]] = defaultdict(set)
        removal_proofs: dict[tuple[Series, date], set[str]] = defaultdict(set)
        for replay in batch:
            edition = replay.edition
            digest = edition.source_sha256
            raw_source = (digest, _instant(edition.available_at).isoformat())
            previous = source_by_query.setdefault(edition.query, {})
            input_rows += edition.input_rows
            duplicate_rows += edition.duplicate_rows
            excluded_non_auction_rows += len(edition.rejections)
            for trade_id, evidence in replay.withdrawals.items():
                old = previous.pop(trade_id)
                key = (old.trade.series, old.trade.trade_day)
                del active[key][trade_id]
                changes[key].add(raw_source)
                previous_sources[key].add(old.source_sha256)
                removal_proofs[key].add(evidence.source_sha256)
                withdrawn_trades += 1

            for trade_id, trade in replay.trades.items():
                owner = owner_by_trade.setdefault(trade_id, edition.query)
                if owner != edition.query:
                    raise ValueError("Auction trade identity appears in multiple acquisition scopes")
                old = previous.get(trade_id)
                if old is not None:
                    if old.trade == trade:
                        continue
                    old_key = (old.trade.series, old.trade.trade_day)
                    del active[old_key][trade_id]
                    changes[old_key].add(raw_source)
                    previous_sources[old_key].add(old.source_sha256)
                    corrections += 1
                key = (trade.series, trade.trade_day)
                version = _SourcedTrade(trade, digest, available_at)
                previous[trade_id] = version
                active[key][trade_id] = version
                changes[key].add(raw_source)

        for series, trade_day in sorted(changes, key=lambda key: (tuple(vars(key[0]).values()), key[1])):
            key = (series, trade_day)
            members = active[key]
            if not members and key not in published:
                del active[key]
                continue
            price, volume = _aggregate(members)
            entry = {
                "format": "nongtori-auction-daily-v1",
                "series": asdict(series),
                "trade_day": trade_day.isoformat(),
                "available_at": available_at.isoformat(),
                "availability_basis": "COMPLETE_RESPONSE_CAPTURE_AND_REQUIRED_WITHDRAWAL_EVIDENCE",
                "price_krw_per_kg": price,
                "trade_volume_kg": volume,
                "active_trade_count": len(members),
                "active_source_sha256": sorted({row.source_sha256 for row in members.values()}),
                "change_source_sha256": sorted({digest for digest, _ in changes[key]}),
                "change_source_captures": [
                    {"source_sha256": digest, "captured_at": timestamp} for digest, timestamp in sorted(changes[key])
                ],
                "previous_source_sha256": sorted(previous_sources[key]),
                "withdrawal_evidence_sha256": sorted(removal_proofs[key]),
            }
            serialized = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            version_sha = hashlib.sha256(serialized).hexdigest()
            manifest[version_sha] = entry
            prices.append(DailyPrice(series, trade_day, available_at, price, volume, version_sha))
            if members:
                published.add(key)
            else:
                published.remove(key)
                del active[key]
    return AuctionHistory(tuple(prices), manifest, {
        "supplied_editions": len(editions),
        "validated_editions": len(ordered),
        "input_rows": input_rows,
        "duplicate_rows": duplicate_rows,
        "excluded_non_auction_rows": excluded_non_auction_rows,
        "corrected_trades": corrections,
        "withdrawn_trades": withdrawn_trades,
        "daily_versions": len(prices),
    })


def write_daily_prices(stream: TextIO, prices: Iterable[DailyPrice]) -> None:
    """Write the existing baseline CSV contract without coercing classification codes."""
    writer = csv.writer(stream)
    writer.writerow((*SERIES_FIELDS, "trade_day", "available_at", "status", "price_krw_per_kg",
                     "trade_volume_kg", "source_sha256"))
    for price in prices:
        writer.writerow((
            *(getattr(price.series, field) for field in SERIES_FIELDS),
            price.trade_day.isoformat(),
            _instant(price.available_at).isoformat(),
            "WITHDRAWN" if price.price_krw_per_kg is None else "TRADED",
            price.price_krw_per_kg,
            price.trade_volume_kg,
            price.source_sha256,
        ))


def summarize_population(history: AuctionHistory, *, cultivar: str, product: str | None = None) -> dict:
    """Audit observed exact-Series coverage for a separately verified cultivar code."""
    if not isinstance(cultivar, str) or not cultivar or cultivar != cultivar.strip():
        raise ValueError("Expected an exact cultivar code from the provider's classification")
    by_series: dict[Series, list[DailyPrice]] = defaultdict(list)
    excluded_cultivar = excluded_product = 0
    for row in history.prices:
        if row.series.cultivar != cultivar:
            excluded_cultivar += 1
        elif product is not None and row.series.product != product:
            excluded_product += 1
        else:
            by_series[row.series].append(row)
    products = {series.product for series in by_series}
    if len(products) > 1:
        raise ValueError("Cultivar code is ambiguous across products; specify the verified product code")
    coverage = []
    for series, versions in sorted(by_series.items(), key=lambda item: tuple(vars(item[0]).values())):
        latest = {row.trade_day: row for row in versions}
        trade_days = sorted(day for day, row in latest.items() if row.price_krw_per_kg is not None)
        coverage.append({
            "series": asdict(series),
            "admitted_versions": len(versions),
            "observed_trade_days": len(trade_days),
            "withdrawn_trade_days": len(latest) - len(trade_days),
            "first_trade_day": trade_days[0].isoformat() if trade_days else None,
            "last_trade_day": trade_days[-1].isoformat() if trade_days else None,
            "first_available_at": min(row.available_at for row in versions).isoformat(),
            "last_available_at": max(row.available_at for row in versions).isoformat(),
        })
    return {
        "cultivar": cultivar,
        "product": product or next(iter(products), None),
        "availability_basis": "COMPLETE_RESPONSE_CAPTURE_AND_REQUIRED_WITHDRAWAL_EVIDENCE",
        "excluded_other_cultivar_versions": excluded_cultivar,
        "excluded_other_product_versions": excluded_product,
        "series": coverage,
    }
