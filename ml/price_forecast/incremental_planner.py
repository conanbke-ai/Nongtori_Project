"""Pure pricing work planner. No network, persistence, or model execution."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9), name="KST")


def _identifier(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("Expected a nonempty exact identifier string")


def _instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Expected a timezone-aware datetime")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class Acquisition:
    provider: str
    endpoint: str
    market: str
    settlement_day: date
    fields: frozenset[str]
    corporation_filter: str | None = None
    product_filter: str | None = None

    def __post_init__(self) -> None:
        for identifier in (self.provider, self.endpoint, self.market):
            _identifier(identifier)
        for identifier in (self.corporation_filter, self.product_filter):
            if identifier is not None:
                _identifier(identifier)
        if type(self.settlement_day) is not date:
            raise ValueError("Expected an exact settlement date")
        if not isinstance(self.fields, frozenset) or "origin" not in self.fields:
            raise ValueError("Expected a frozen field selection including origin")
        for field in self.fields:
            _identifier(field)


@dataclass(frozen=True)
class Series:
    provider: str
    market: str
    corporation: str
    product: str
    origin: str
    cultivar: str
    grade: str
    unit: str

    def __post_init__(self) -> None:
        for identifier in vars(self).values():
            _identifier(identifier)


@dataclass(frozen=True)
class Target:
    requests: tuple[Acquisition, ...]
    series: Series
    source_and_units_confirmed: bool
    previous_cutoff: datetime
    minimum_new_days: int

    def __post_init__(self) -> None:
        _instant(self.previous_cutoff)
        if type(self.source_and_units_confirmed) is not bool:
            raise ValueError("Expected an explicit verification flag")
        if type(self.minimum_new_days) is not int or self.minimum_new_days < 1:
            raise ValueError("Expected a positive minimum")
        s = self.series
        if not self.requests or len(set(self.requests)) != len(self.requests):
            raise ValueError("Expected a nonempty set of distinct requests")
        for r in self.requests:
            if (r.provider, r.market) != (s.provider, s.market):
                raise ValueError("Request and series refer to different sources")
            if r.corporation_filter not in (None, s.corporation) or r.product_filter not in (None, s.product):
                raise ValueError("Request filters do not cover the series")


@dataclass(frozen=True)
class Receipt:
    request: Acquisition
    sha256: str
    complete: bool
    # Local verification time, not provider publication.
    verified_at: datetime | None
    # None is unverified; () is verified empty.
    eligible_rows: tuple["Observation", ...] | None = None


@dataclass(frozen=True)
class Observation:
    series: Series
    trade_day: date
    # Independent availability evidence; never inferred from verified_at.
    available_at: datetime | None
    source_sha256: str


@dataclass(frozen=True)
class Decision:
    series: Series
    state: str
    new_days: int = 0


@dataclass(frozen=True)
class Plan:
    fetch: tuple[Acquisition, ...]
    decisions: tuple[Decision, ...]


def _has_digest(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _verified_rows(receipt: Receipt, verified: datetime) -> bool:
    if not isinstance(receipt.eligible_rows, tuple):
        return False
    request = receipt.request
    for row in receipt.eligible_rows:
        if (
            not isinstance(row, Observation)
            or not isinstance(row.series, Series)
            or row.source_sha256 != receipt.sha256
            or type(row.trade_day) is not date
            or row.trade_day > request.settlement_day
        ):
            return False
        series = row.series
        if (
            (series.provider, series.market) != (request.provider, request.market)
            or request.corporation_filter not in (None, series.corporation)
            or request.product_filter not in (None, series.product)
        ):
            return False
        if row.available_at is not None:
            try:
                available = _instant(row.available_at)
            except ValueError:
                return False
            if available > verified or row.trade_day > available.astimezone(KST).date():
                return False
    return True


def plan_updates(
    targets: tuple[Target, ...],
    receipts: tuple[Receipt, ...],
    approved_series: frozenset[Series],
    *,
    as_of: datetime,
) -> Plan:
    """Plan from trusted parse receipts for exact requests.

    KST guards calendar dates, not publication times. Only the adapter can
    establish independent row availability and complete pagination.
    """
    now = _instant(as_of)
    today = now.astimezone(KST).date()
    unverified: set[Acquisition] = set()
    pending: dict[Acquisition, None] = {}
    decisions: list[Decision] = []
    requests = {r for target in targets if target.source_and_units_confirmed for r in target.requests}
    by_request: dict[Acquisition, dict[str, Receipt]] = {}
    for receipt in receipts:
        if receipt.request not in requests or receipt.complete is not True or not _has_digest(receipt.sha256):
            continue
        if receipt.verified_at is None:
            continue
        try:
            verified = _instant(receipt.verified_at)
        except ValueError:
            unverified.add(receipt.request)
            continue
        if verified > now:
            continue
        if receipt.request.settlement_day > verified.astimezone(KST).date() or not _verified_rows(receipt, verified):
            unverified.add(receipt.request)
            continue
        versions = by_request.setdefault(receipt.request, {})
        existing = versions.get(receipt.sha256)
        if existing is not None and existing != receipt:
            raise ValueError("Conflicting receipt metadata for one source edition")
        versions[receipt.sha256] = receipt
    seen: set[Series] = set()
    for target in targets:
        s = target.series
        if s in seen:
            raise ValueError("Duplicate series target")
        seen.add(s)
        cutoff = _instant(target.previous_cutoff)
        if cutoff > now:
            raise ValueError("Previous cutoff is later than the planning time")
        if not target.source_and_units_confirmed:
            decisions.append(Decision(s, "UNVERIFIED_SOURCE"))
            continue
        if any(r.settlement_day > today for r in target.requests):
            decisions.append(Decision(s, "AWAITING_SETTLEMENT_DAY"))
            continue
        if any(r in unverified for r in target.requests):
            decisions.append(Decision(s, "UNVERIFIED_ACQUISITION"))
            continue
        missing = tuple(r for r in target.requests if not by_request.get(r))
        for r in missing:
            pending[r] = None
        if any(len(by_request.get(r, {})) > 1 for r in target.requests):
            decisions.append(Decision(s, "AMBIGUOUS_ACQUISITION"))
            continue
        if missing:
            decisions.append(Decision(s, "AWAITING_ACQUISITION"))
            continue
        days: set[date] = set()
        for r in target.requests:
            receipt = next(iter(by_request[r].values()))
            for row in receipt.eligible_rows or ():
                if row.series != s or row.available_at is None:
                    continue
                instant = _instant(row.available_at)
                if cutoff < instant <= now:
                    days.add(row.trade_day)
        state = (
            "RETRAIN_CANDIDATE" if len(days) >= target.minimum_new_days
            else "REUSE_APPROVED_MODEL" if s in approved_series else "NO_APPROVED_MODEL"
        )
        decisions.append(Decision(s, state, len(days)))
    return Plan(tuple(pending), tuple(decisions))
