from __future__ import annotations

import argparse
import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

if __package__:
    from .baseline import DailyPrice, SERIES_FIELDS, load_daily_prices
    from .incremental_planner import KST, Series
else:
    # Keep the original script invocation working alongside python -m.
    from sys import path as sys_path

    sys_path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ml.price_forecast.baseline import DailyPrice, SERIES_FIELDS, load_daily_prices
    from ml.price_forecast.incremental_planner import KST, Series


DATE_COLUMN = "trade_day"
TARGET_COLUMN = "price_krw_per_kg"
CALENDAR_FEATURES = ("day_of_week", "month", "day_of_year", "week_of_year", "is_weekend")
PRICE_LAGS = (1, 2, 3, 7, 14, 28, 56)
PRICE_ROLL_WINDOWS = (3, 7, 14, 28)
CATBOOST_FEATURES = (
    *SERIES_FIELDS,
    *CALENDAR_FEATURES,
    *(f"price_lag_{lag}" for lag in PRICE_LAGS),
    *(f"price_roll_{stat}_{window}" for window in PRICE_ROLL_WINDOWS for stat in ("mean", "std")),
)
TFT_KNOWN_REALS = ("time_idx", *CALENDAR_FEATURES)
TFT_UNKNOWN_REALS = (TARGET_COLUMN,)


def load_config(path: str | Path) -> dict[str, Any]:
    import yaml

    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def add_training_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data", required=True, type=Path, help="정규화된 버전별 일별 가격 CSV")
    parser.add_argument("--input-sha256", required=True, help="적격 심사 후 고정한 CSV SHA-256")
    parser.add_argument("--labels-as-of", required=True, type=datetime.fromisoformat, help="평가용 버전 고정 시각")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    parser.add_argument("--output", type=Path, help="학습 산출물 폴더")
    parser.add_argument("--train", action="store_true", help="입력 검증 후 학습 실행")


def load_training_prices(path: Path, input_sha256: str, labels_as_of: datetime) -> list[DailyPrice]:
    """Admit frozen, single-edition histories for conservative candidate training."""
    if not isinstance(labels_as_of, datetime) or labels_as_of.utcoffset() is None:
        raise ValueError("labels_as_of must specify a UTC offset")
    labels_as_of = labels_as_of.astimezone(timezone.utc)
    labels_day = labels_as_of.astimezone(KST).date()
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != input_sha256:
        raise ValueError("Input SHA-256 does not match the frozen CSV")
    try:
        rows = load_daily_prices(io.StringIO(payload.decode("utf-8-sig"), newline=""))
    except csv.Error as error:
        raise ValueError("Invalid normalized price CSV") from error
    if not rows:
        raise ValueError("No price history in the frozen CSV")
    seen: set[tuple[Series, date]] = set()
    for row in rows:
        key = (row.series, row.trade_day)
        if row.available_at > labels_as_of or row.trade_day >= labels_day:
            raise ValueError("Training input contains an open or unavailable label at labels_as_of")
        if row.price_krw_per_kg is None or key in seen:
            raise ValueError("Candidate training requires one non-withdrawn version per series and trade day")
        if row.available_at.astimezone(KST).date() != row.trade_day:
            raise ValueError("Candidate training requires availability within the KST trade day")
        seen.add(key)
    return sorted(rows, key=lambda row: (tuple(getattr(row.series, name) for name in SERIES_FIELDS), row.trade_day))


@dataclass(frozen=True)
class TrainingSplit:
    train_end: date
    validation_end: date
    holdout_end: date
    train_rows: int
    validation_rows: int
    holdout_rows: int

    def evidence(self, args: argparse.Namespace) -> dict[str, str | int]:
        return {
            "input_sha256": args.input_sha256,
            "labels_as_of": args.labels_as_of.isoformat(),
            "train_end": self.train_end.isoformat(),
            "selection_validation_end": self.validation_end.isoformat(),
            "holdout_end": self.holdout_end.isoformat(),
            "train_input_rows": self.train_rows,
            "selection_validation_input_rows": self.validation_rows,
            "holdout_rows_excluded": self.holdout_rows,
        }


def split_training_prices(
    rows: list[DailyPrice], *, validation_days: int, holdout_days: int,
) -> TrainingSplit:
    if not rows or validation_days < 1 or holdout_days < 1:
        raise ValueError("Expected positive selection-validation and holdout date ranges")
    holdout_end = max(row.trade_day for row in rows)
    validation_end = holdout_end - timedelta(days=holdout_days)
    train_end = validation_end - timedelta(days=validation_days)
    train_rows = sum(row.trade_day <= train_end for row in rows)
    validation_rows = sum(train_end < row.trade_day <= validation_end for row in rows)
    holdout_rows = len(rows) - train_rows - validation_rows
    if min(train_rows, validation_rows, holdout_rows) == 0:
        raise ValueError("Train, selection validation and holdout must each have rows")
    return TrainingSplit(train_end, validation_end, holdout_end, train_rows, validation_rows, holdout_rows)


def load_training_input(args: argparse.Namespace) -> tuple[list[DailyPrice], dict[str, Any], TrainingSplit]:
    rows = load_training_prices(args.data, args.input_sha256, args.labels_as_of)
    config = load_config(args.config)
    split = split_training_prices(
        rows,
        validation_days=config["validation"]["selection_days"],
        holdout_days=config["validation"]["holdout_days"],
    )
    return rows, config, split


def validate_tft_history(rows: Iterable[DailyPrice]) -> None:
    """Refuse gaps rather than synthesize a past or future price label."""
    previous_day: dict[Series, date] = {}
    for row in rows:
        previous = previous_day.get(row.series)
        if previous is not None and (row.trade_day - previous).days != 1:
            raise ValueError("TFT requires contiguous trade dates for each series through selection validation")
        previous_day[row.series] = row.trade_day


def training_price_frame(rows: Iterable[DailyPrice]) -> pd.DataFrame:
    import pandas as pd

    result = pd.DataFrame([
        {
            **{name: getattr(row.series, name) for name in SERIES_FIELDS},
            DATE_COLUMN: row.trade_day,
            TARGET_COLUMN: row.price_krw_per_kg,
        }
        for row in rows
    ])
    result[DATE_COLUMN] = pd.to_datetime(result[DATE_COLUMN], errors="raise")
    return result.sort_values([*SERIES_FIELDS, DATE_COLUMN]).reset_index(drop=True)


def add_calendar_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    day = result[DATE_COLUMN].dt
    result["day_of_week"] = day.dayofweek.astype("int16")
    result["month"] = day.month.astype("int16")
    result["day_of_year"] = day.dayofyear.astype("int16")
    result["week_of_year"] = day.isocalendar().week.astype("int16")
    result["is_weekend"] = (day.dayofweek >= 5).astype("int8")
    return result


def add_lag_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = add_calendar_features(frame)
    grouped = result.groupby(list(SERIES_FIELDS), observed=True, sort=False)[TARGET_COLUMN]
    for lag in PRICE_LAGS:
        result[f"price_lag_{lag}"] = grouped.shift(lag)
    prior_prices = grouped.shift(1).groupby(
        [result[column] for column in SERIES_FIELDS], observed=True, sort=False
    )
    for window in PRICE_ROLL_WINDOWS:
        result[f"price_roll_mean_{window}"] = prior_prices.transform(
            lambda series: series.rolling(window, min_periods=2).mean()
        )
        result[f"price_roll_std_{window}"] = prior_prices.transform(
            lambda series: series.rolling(window, min_periods=2).std()
        )
    return result
