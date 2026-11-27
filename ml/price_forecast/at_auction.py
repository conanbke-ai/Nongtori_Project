"""aT national wholesale auction transport, pagination and trade admission."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, DecimalException
from time import monotonic, sleep
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .incremental_planner import KST, Series

ENDPOINT = "https://apis.data.go.kr/B552845/katOrigin/trades"
PROVIDER = "at/15141810"
ADAPTER_VERSION = "at-auction-v1"
MAX_PAGE_BYTES = 8 * 1024 * 1024
FIELDS = (
    "trd_clcln_ymd", "whsl_mrkt_cd", "corp_cd", "gds_lclsf_cd", "gds_mclsf_cd",
    "gds_sclsf_cd", "plor_cd", "grd_cd", "unit_cd", "pkg_cd", "sz_cd",
    "unit_qty", "qty", "scsbd_prc", "totprc", "unit_tot_qty",
    "spm_no", "auctn_seq", "auctn_seq2", "trd_se", "scsbd_dt",
)


class AuctionError(ValueError):
    pass


def _code(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or not value.isascii() or not value.isalnum():
        raise AuctionError("Invalid or missing exact source code")
    return value


def _instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise AuctionError("Expected timestamp with a UTC offset")
    return value.astimezone(timezone.utc)


def _digest(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise AuctionError("Expected lowercase SHA-256")
    return value


@dataclass(frozen=True)
class AuctionQuery:
    settlement_day: date
    market: str
    corporation: str | None = None
    product: str | None = None  # aT middle classification
    category: str | None = None
    cultivar: str | None = None

    def __post_init__(self) -> None:
        if type(self.settlement_day) is not date:
            raise AuctionError("Expected settlement date")
        for code in (self.corporation, self.product, self.category, self.cultivar):
            if code is not None:
                _code(code)
        _code(self.market)

    def filters(self) -> dict[str, str]:
        result = {"trd_clcln_ymd": self.settlement_day.isoformat(), "whsl_mrkt_cd": self.market}
        for name, value in (
            ("corp_cd", self.corporation), ("gds_lclsf_cd", self.category),
            ("gds_mclsf_cd", self.product), ("gds_sclsf_cd", self.cultivar),
        ):
            if value is not None:
                result[name] = value
        return result


@dataclass(frozen=True)
class AuctionCodebook:
    """Selected standard codes, with the immutable source snapshot digest."""

    evidence_sha256: str
    markets: frozenset[str]
    corporations: frozenset[tuple[str, str]]
    products: frozenset[tuple[str, str, str]]
    origins: frozenset[str]
    grades: frozenset[str]
    packages: frozenset[str]
    sizes: frozenset[str]
    units: frozenset[str]


def load_codebook(payload: bytes) -> AuctionCodebook:
    try:
        data = json.loads(payload)
        if not isinstance(data, dict) or set(data) != {
            "evidence_sha256", "markets", "corporations", "products", "origins", "grades",
            "packages", "sizes", "units",
        }:
            raise AuctionError("Unexpected standard-code reference columns")
        for field in ("markets", "origins", "grades", "packages", "sizes", "units"):
            if not isinstance(data[field], list):
                raise AuctionError("Expected lists in the standard-code reference")
            data[field] = frozenset(_code(code) for code in data[field])
        for field, size in (("corporations", 2), ("products", 3)):
            values = data[field]
            if not isinstance(values, list) or any(not isinstance(item, list) or len(item) != size for item in values):
                raise AuctionError("Expected complete standard-code tuples")
            data[field] = frozenset(tuple(_code(code) for code in item) for item in values)
        _digest(data["evidence_sha256"])
        return AuctionCodebook(**data)
    except (ValueError, TypeError) as error:
        raise AuctionError("Invalid aT standard-code reference") from error


@dataclass(frozen=True)
class PageCapture:
    number: int
    size: int
    received_at: datetime
    payload: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()


@dataclass(frozen=True)
class AuctionTrade:
    trade_id: tuple[str, ...]
    series: Series
    trade_day: date
    total_krw: Decimal
    volume_kg: Decimal


@dataclass(frozen=True)
class AuctionRejection:
    page: int
    row: int
    reason: str


@dataclass(frozen=True)
class AuctionEdition:
    query: AuctionQuery
    available_at: datetime
    source_sha256: str
    captures: tuple[PageCapture, ...]
    trades: tuple[AuctionTrade, ...]
    input_rows: int
    duplicate_rows: int
    rejections: tuple[AuctionRejection, ...] = ()
    code_evidence_sha256: str | None = None


@dataclass(frozen=True)
class _Page:
    total: int
    rows: list[dict]


def _nonnegative_int(value: object) -> int:
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    raise AuctionError("Invalid pagination metadata")


def _parse_page(capture: PageCapture) -> _Page:
    def unique_keys(pairs: list[tuple[str, object]]) -> dict:
        result = dict(pairs)
        if len(result) != len(pairs):
            raise AuctionError("Duplicate key in aT JSON response")
        return result

    if not capture.payload or len(capture.payload) > MAX_PAGE_BYTES:
        raise AuctionError("Invalid aT page body size")
    try:
        data = json.loads(capture.payload, parse_float=Decimal, object_pairs_hook=unique_keys)
        response = data["response"]
        if response["header"]["resultCode"] != "00":
            raise AuctionError("aT returned an unsuccessful result")
        body = response["body"]
        number, size = body["pageNo"], body["numOfRows"]
        total = _nonnegative_int(body["totalCount"])
        items = body["items"]
        rows = [] if total == 0 and items == "" else items["item"]
        if (_nonnegative_int(number), _nonnegative_int(size)) != (capture.number, capture.size):
            raise AuctionError("aT page coordinate does not match the request")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise AuctionError("aT page rows must be an array of objects")
        expected = min(capture.size, max(0, total - (capture.number - 1) * capture.size))
        if len(rows) != expected:
            raise AuctionError("aT page does not contain the expected number of rows")
        return _Page(total, rows)
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError, DecimalException) as error:
        raise AuctionError("Unsupported or malformed aT response envelope") from error


def _trade_id(row: dict) -> tuple[str, ...]:
    # Settlement coordinates are retained in the provisional publisher record identity.
    coordinates = [_code(row.get("whsl_mrkt_cd")), _code(row.get("corp_cd"))]
    for field in ("spm_no", "auctn_seq", "auctn_seq2"):
        value = row.get(field)
        coordinates.append(str(value) if type(value) is int and value >= 0 else _code(value))
    return (*coordinates, row["trd_clcln_ymd"])


def _quantity(value: object) -> Decimal:
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise AuctionError("INVALID_AMOUNT")
    try:
        amount = Decimal(value)
    except DecimalException as error:
        raise AuctionError("INVALID_AMOUNT") from error
    if not amount.is_finite() or amount <= 0 or abs(amount.adjusted()) > 12 or len(amount.as_tuple().digits) > 12:
        raise AuctionError("INVALID_AMOUNT")
    return amount


def _normalize_trade(
    row: dict, codebook: AuctionCodebook, available_at: datetime, trade_id: tuple[str, ...],
) -> AuctionTrade:
    try:
        market, corporation, primary, product, cultivar, origin, grade, unit, package, size = (
            _code(row.get(field)) for field in (
                "whsl_mrkt_cd", "corp_cd", "gds_lclsf_cd", "gds_mclsf_cd", "gds_sclsf_cd",
                "plor_cd", "grd_cd", "unit_cd", "pkg_cd", "sz_cd",
            )
        )
    except AuctionError:
        raise AuctionError("MISSING_OR_INVALID_STANDARD_CODE") from None
    if (
        market not in codebook.markets or (market, corporation) not in codebook.corporations
        or (primary, product, cultivar) not in codebook.products or origin not in codebook.origins
        or grade not in codebook.grades or unit not in codebook.units or package not in codebook.packages
        or size not in codebook.sizes
    ):
        raise AuctionError("CODE_OUTSIDE_REFERENCE")
    try:
        moment = datetime.fromisoformat(row["scsbd_dt"])
        if "T" not in row["scsbd_dt"] and " " not in row["scsbd_dt"]:
            raise ValueError
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=KST)
        trade_day = moment.astimezone(KST).date()
        if _instant(moment) > available_at or trade_day > date.fromisoformat(row["trd_clcln_ymd"]):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise AuctionError("MISSING_OR_INVALID_TRADE_TIME") from None

    # The aT cross-field total convention has not been validated for grams or tonnes.
    if unit != "12":
        raise AuctionError("UNVERIFIED_MASS_UNIT")
    unit_kg, packages, package_price, total, volume_kg = (
        _quantity(row.get(field)) for field in ("unit_qty", "qty", "scsbd_prc", "totprc", "unit_tot_qty")
    )
    if packages != packages.to_integral_value() or unit_kg * packages != volume_kg or package_price * packages != total:
        raise AuctionError("INCONSISTENT_AMOUNT_OR_VOLUME")
    spec = f"{unit}:{format(unit_kg.normalize(), 'f')}:{package}:{size}"
    series = Series(PROVIDER, market, corporation, f"{primary}:{product}", origin, cultivar, grade, spec)
    return AuctionTrade(trade_id, series, trade_day, total, volume_kg)


def validate_query(query: AuctionQuery, codebook: AuctionCodebook) -> None:
    if query.market not in codebook.markets:
        raise AuctionError("Market absent from standard-code reference")
    if query.corporation is not None and (query.market, query.corporation) not in codebook.corporations:
        raise AuctionError("Corporation absent from market reference")
    filters = (query.category, query.product, query.cultivar)
    if any(value is not None for value in filters) and not any(
        all(wanted is None or wanted == actual for wanted, actual in zip(filters, item, strict=True))
        for item in codebook.products
    ):
        raise AuctionError("Product classification absent from standard-code reference")


def parse_edition(
    query: AuctionQuery, captures: tuple[PageCapture, ...], codebook: AuctionCodebook,
) -> AuctionEdition:
    validate_query(query, codebook)
    if not captures or type(captures[0].size) is not int or captures[0].size < 1:
        raise AuctionError("A complete aT edition must include page one")
    received = [_instant(page.received_at) for page in captures]
    if received != sorted(received) or query.settlement_day > received[0].astimezone(KST).date():
        raise AuctionError("Invalid acquisition chronology")
    available_at = received[-1]
    filters = query.filters()
    seen = set()
    encoded_rows = {}
    accepted = []
    rejections = []
    input_rows = duplicates = 0
    total = None
    size = captures[0].size
    for number, capture in enumerate(captures, 1):
        if (
            type(capture.number) is not int or type(capture.size) is not int
            or type(capture.payload) is not bytes or (capture.number, capture.size) != (number, size)
        ):
            raise AuctionError("aT pages are missing, repeated or use different sizes")
        page = _parse_page(capture)
        if total is None:
            total = page.total
            if len(captures) != max(1, (total + size - 1) // size):
                raise AuctionError("Incomplete or surplus aT pages")
        elif page.total != total:
            raise AuctionError("aT total changed during pagination")
        for index, row in enumerate(page.rows, 1):
            input_rows += 1
            if set(row) - set(FIELDS):
                raise AuctionError("aT returned unrequested columns")
            if any(row.get(field) != value for field, value in filters.items()):
                raise AuctionError("aT row outside the exact request scope")
            # Check all source rows before excluding non-auction or malformed trades.
            encoded = json.dumps(row, sort_keys=True, default=str)
            if encoded in encoded_rows:
                if encoded_rows[encoded] != number:
                    raise AuctionError("Repeated record across aT pages")
                duplicates += 1
                continue
            encoded_rows[encoded] = number
            if row.get("trd_se") != "경매":
                reason = "NON_AUCTION_TRADE_TYPE" if row.get("trd_se") == "정가수의" else "UNKNOWN_TRADE_TYPE"
                rejections.append(AuctionRejection(number, index, reason))
                continue
            try:
                trade_id = _trade_id(row)
            except AuctionError:
                rejections.append(AuctionRejection(number, index, "INVALID_SOURCE_RECORD_ID"))
                continue
            if trade_id in seen:
                raise AuctionError("Conflicting source record in one aT edition")
            seen.add(trade_id)
            try:
                accepted.append(_normalize_trade(row, codebook, available_at, trade_id))
            except AuctionError as error:
                rejections.append(AuctionRejection(number, index, str(error)))

    manifest = {"request": filters, "pages": [(p.number, p.size, p.sha256) for p in captures]}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return AuctionEdition(
        query, available_at, digest, captures, tuple(accepted), input_rows, duplicates, tuple(rejections),
        codebook.evidence_sha256,
    )


def fetch_edition(
    query: AuctionQuery,
    codebook: AuctionCodebook,
    transport: Callable[[dict[str, str]], bytes],
    *,
    size: int,
    max_pages: int,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> AuctionEdition:
    validate_query(query, codebook)
    if type(size) is not int or type(max_pages) is not int or size < 1 or max_pages < 1:
        raise AuctionError("Require a positive page size and approved page budget")
    if query.settlement_day > _instant(clock()).astimezone(KST).date():
        raise AuctionError("Requested a future settlement day")
    params = {f"cond[{key}::EQ]": value for key, value in query.filters().items()}
    params.update(returnType="json", numOfRows=str(size), selectable=",".join(FIELDS))
    captures = []
    first_total = None
    for number in range(1, max_pages + 1):
        payload = transport({**params, "pageNo": str(number)})
        capture = PageCapture(number, size, _instant(clock()), payload)
        page = _parse_page(capture)
        if first_total is None:
            first_total = page.total
            required = max(1, (page.total + size - 1) // size)
            if required > max_pages:
                raise AuctionError("aT results exceed the approved page budget")
        elif page.total != first_total:
            raise AuctionError("aT total changed during pagination")
        captures.append(capture)
        if number == required:
            break
    return parse_edition(query, tuple(captures), codebook)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def https_transport(key: str, interval_seconds: float) -> Callable[[dict[str, str]], bytes]:
    if not isinstance(key, str) or not key or key != key.strip():
        raise AuctionError("An approved aT service key is required")
    if not math.isfinite(interval_seconds) or interval_seconds <= 0:
        raise AuctionError("An approved positive request interval is required")
    opener = build_opener(_NoRedirect())
    next_request = 0.0

    def get(params: dict[str, str]) -> bytes:
        nonlocal next_request
        if (wait := next_request - monotonic()) > 0:
            sleep(wait)
        request = Request(f"{ENDPOINT}?{urlencode({**params, 'serviceKey': key})}", headers={"Accept": "application/json"})
        try:
            next_request = monotonic() + interval_seconds
            with opener.open(request, timeout=30) as response:
                data = response.read(MAX_PAGE_BYTES + 1)
                if len(data) > MAX_PAGE_BYTES:
                    raise AuctionError("aT page exceeds response size limit")
                return data
        except HTTPError as error:
            raise AuctionError(f"aT HTTP status {error.code}") from None
        except (URLError, OSError):
            raise AuctionError("aT connection failed") from None

    return get
