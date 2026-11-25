"""Offline rolling-origin evaluation of daily KRW/kg price baselines."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from bisect import bisect_left, insort
from collections import defaultdict
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import fmean
from typing import Iterable

from .incremental_planner import KST, Series


@dataclass(frozen=True)
class DailyPrice:
    series: Series
    trade_day: date
    available_at: datetime
    price_krw_per_kg: float | None
    trade_volume_kg: float | None
    source_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.series, Series) or type(self.trade_day) is not date:
            raise ValueError("Expected an exact series and trade date")
        if not isinstance(self.available_at, datetime) or self.available_at.utcoffset() is None:
            raise ValueError("available_at must have a UTC offset")
        if self.trade_day > self.available_at.astimezone(KST).date():
            raise ValueError("Date of availability precedes the trade day")
        if not isinstance(self.source_sha256, str) or len(self.source_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.source_sha256
        ):
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
        if self.price_krw_per_kg is None and self.trade_volume_kg is None:
            return  # An independently evidenced withdrawal of this day's observation.
        if self.price_krw_per_kg is None or not math.isfinite(self.price_krw_per_kg) or self.price_krw_per_kg < 0:
            raise ValueError("price_krw_per_kg must be finite and nonnegative")
        if self.trade_volume_kg is None or not math.isfinite(self.trade_volume_kg) or self.trade_volume_kg <= 0:
            raise ValueError("trade_volume_kg must be finite and positive")


SERIES_FIELDS = tuple(field.name for field in fields(Series))
CSV_FIELDS = frozenset(
    (*SERIES_FIELDS, "trade_day", "available_at", "status", "price_krw_per_kg", "trade_volume_kg", "source_sha256")
)


def load_daily_prices(stream: Iterable[str]) -> list[DailyPrice]:
    """Read normalized, versioned daily prices without coercing identifier strings."""
    reader = csv.DictReader(stream, strict=True)
    if reader.fieldnames is None or len(reader.fieldnames) != len(CSV_FIELDS) or set(reader.fieldnames) != CSV_FIELDS:
        raise ValueError("Expected exactly these CSV fields: " + ", ".join(sorted(CSV_FIELDS)))
    rows = []
    for row in reader:
        try:
            if None in row or None in row.values():
                raise ValueError("CSV row length differs from the header")
            trade_day = date.fromisoformat(row["trade_day"])
            if trade_day.isoformat() != row["trade_day"]:
                raise ValueError("trade_day must have YYYY-MM-DD format")
            price, volume = row["price_krw_per_kg"], row["trade_volume_kg"]
            status = row["status"]
            if status == "TRADED":
                price, volume = float(price), float(volume)
            elif status == "WITHDRAWN" and not price and not volume:
                price, volume = None, None
            else:
                raise ValueError("Expected TRADED with price and volume or WITHDRAWN with both fields empty")
            rows.append(DailyPrice(
                series=Series(**{name: row[name] for name in SERIES_FIELDS}),
                trade_day=trade_day,
                available_at=datetime.fromisoformat(row["available_at"]),
                price_krw_per_kg=price,
                trade_volume_kg=volume,
                source_sha256=row["source_sha256"],
            ))
        except ValueError as error:
            raise ValueError(f"CSV line {reader.line_num}: {error}") from error
    return rows


def _metrics(actual: list[float], predicted: list[float]) -> dict[str, float | None]:
    errors = [abs(observed - forecast) for observed, forecast in zip(actual, predicted, strict=True)]
    denominators = [observed + forecast for observed, forecast in zip(actual, predicted, strict=True)]
    total = math.fsum(actual)
    return {
        "mae_krw_per_kg": fmean(errors),
        "rmse_krw_per_kg": math.sqrt(fmean(error ** 2 for error in errors)),
        "smape_percent": fmean(
            2 * (error / denominator) if denominator else 0.0
            for error, denominator in zip(errors, denominators, strict=True)
        ) * 100,
        "wape_percent": math.fsum(errors) / total * 100 if total else None,
    }


def _evaluate_series(
    series: Series,
    versions: list[DailyPrice],
    start: date,
    end: date,
    horizon_days: int,
    window: int,
) -> dict:
    # Each ordered version updates the price for its day at its own availability.
    actual_by_day = {row.trade_day: row.price_krw_per_kg for row in versions}
    history: dict[date, float] = {}
    ordered_days: list[date] = []
    next_version = 0
    no_actual_days = withdrawn_actual_days = insufficient_history_days = 0
    predictions = []
    for offset in range((end - start).days + 1):
        target = start + timedelta(days=offset)
        cutoff_day = target - timedelta(days=horizon_days - 1)
        cutoff = datetime.combine(cutoff_day, time.min, KST)
        while next_version < len(versions) and versions[next_version].available_at < cutoff:
            row = versions[next_version]
            next_version += 1
            if row.price_krw_per_kg is None:
                if row.trade_day in history:
                    del history[row.trade_day]
                    ordered_days.pop(bisect_left(ordered_days, row.trade_day))
                continue
            if row.trade_day not in history:
                insort(ordered_days, row.trade_day)
            history[row.trade_day] = row.price_krw_per_kg
        if target not in actual_by_day:
            no_actual_days += 1
            continue
        actual = actual_by_day[target]
        if actual is None:
            withdrawn_actual_days += 1
            continue
        stop = bisect_left(ordered_days, target)
        if stop < window:
            insufficient_history_days += 1
            continue
        prices = [history[day] for day in ordered_days[stop - window:stop]]
        predictions.append({
            "trade_day": target.isoformat(),
            "history_cutoff_exclusive": cutoff.isoformat(),
            "latest_history_trade_day": ordered_days[stop - 1].isoformat(),
            "actual_krw_per_kg": actual,
            "latest_krw_per_kg": prices[-1],
            "moving_average_krw_per_kg": fmean(prices),
        })

    actual_prices = [row["actual_krw_per_kg"] for row in predictions]
    return {
        "series": asdict(series),
        "scored_days": len(predictions),
        "no_actual_days": no_actual_days,
        "withdrawn_actual_days": withdrawn_actual_days,
        "insufficient_history_days": insufficient_history_days,
        "metrics": {
            name: _metrics(actual_prices, [row[f"{name}_krw_per_kg"] for row in predictions])
            for name in ("latest", "moving_average")
        } if predictions else None,
        "predictions": predictions,
    }


def evaluate_baselines(
    rows: Iterable[DailyPrice],
    *,
    start: date,
    end: date,
    labels_as_of: datetime,
    horizon_days: int = 1,
    window: int = 7,
) -> dict:
    """Replay a fixed holdout, scoring both baselines on each identical target."""
    if type(start) is not date or type(end) is not date or start > end:
        raise ValueError("Expected an inclusive holdout date range")
    if type(horizon_days) is not int or horizon_days < 1 or horizon_days > start.toordinal():
        raise ValueError("horizon_days must be a positive calendar-day lead")
    if type(window) is not int or window < 2:
        raise ValueError("window must contain at least two trade observations")
    if (
        not isinstance(labels_as_of, datetime)
        or labels_as_of.utcoffset() is None
        or labels_as_of.astimezone(KST).date() <= end
    ):
        raise ValueError("labels_as_of must have an offset and follow the full holdout")
    labels_as_of = labels_as_of.astimezone(timezone.utc)

    versions_by_series: dict[Series, list[DailyPrice]] = defaultdict(list)
    seen: dict[tuple[Series, date, datetime], DailyPrice] = {}
    input_rows = duplicate_rows = after_labels_as_of_rows = 0
    for row in rows:
        input_rows += 1
        available_at = row.available_at.astimezone(timezone.utc)
        if available_at > labels_as_of:
            after_labels_as_of_rows += 1
            continue
        key = (row.series, row.trade_day, available_at)
        previous = seen.get(key)
        if previous is not None:
            if (row.price_krw_per_kg, row.trade_volume_kg) != (previous.price_krw_per_kg, previous.trade_volume_kg):
                raise ValueError(f"Conflicting price versions for {row.series!r} on {row.trade_day} at {key[2]}")
            duplicate_rows += 1
            continue
        seen[key] = row
        versions_by_series[row.series].append(row)

    return {
        "holdout_start": start.isoformat(),
        "holdout_end": end.isoformat(),
        "labels_as_of": labels_as_of.isoformat(),
        "horizon_days": horizon_days,
        "moving_average_window": window,
        "input_rows": input_rows,
        "duplicate_rows": duplicate_rows,
        "after_labels_as_of_rows": after_labels_as_of_rows,
        "admitted_versions": len(seen),
        "series": [
            _evaluate_series(
                series, sorted(versions, key=lambda row: row.available_at.astimezone(timezone.utc)),
                start, end, horizon_days, window,
            )
            for series, versions in sorted(versions_by_series.items(), key=lambda item: tuple(vars(item[0]).values()))
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="Normalized versioned daily-price CSV")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--labels-as-of", type=datetime.fromisoformat, required=True)
    parser.add_argument("--horizon-days", type=int, default=1, help="Calendar days from the KST origin day to the target")
    parser.add_argument("--window", type=int, default=7, help="Number of distinct trade observations for the moving average")
    args = parser.parse_args()

    try:
        source = args.data.read_bytes()
        rows = load_daily_prices(io.StringIO(source.decode("utf-8-sig"), newline=""))
        report = evaluate_baselines(
            rows, start=args.start, end=args.end, labels_as_of=args.labels_as_of,
            horizon_days=args.horizon_days, window=args.window,
        )
        report["input_sha256"] = hashlib.sha256(source).hexdigest()
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, OverflowError, csv.Error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
