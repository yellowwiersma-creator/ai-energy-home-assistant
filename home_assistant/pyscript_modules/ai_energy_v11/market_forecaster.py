from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import math
import statistics

from .config import (
    ACCURACY_DIR,
    LEGACY_NORMALIZED_DIR,
    MODEL_DIR,
    RAW_DIR,
    TIMEZONE,
)

from .storage import (
    read_json,
    write_json_atomic,
)


MARKET_FORECASTER_VERSION = "11.5.1-recent-grouped-daily"

LOCAL_TZ = ZoneInfo(TIMEZONE)

UNIFIED_DIR = LEGACY_NORMALIZED_DIR / "unified"

MARKET_MODEL_DIR = MODEL_DIR / "market"
MARKET_ACCURACY_DIR = ACCURACY_DIR / "market"
MARKET_PREDICTION_DIR = MODEL_DIR.parent / "predictions" / "market"

BACKTEST_FILE = MARKET_ACCURACY_DIR / "market_96h_backtest_latest.json"
MODEL_FILE = MARKET_MODEL_DIR / "market_96h_baseline.json"
FORECAST_FILE = MARKET_PREDICTION_DIR / "market_96h_latest.json"

HORIZON_HOURS = 96
INTERVAL_MINUTES = 15
HORIZON_SLOTS = int(HORIZON_HOURS * 60 / INTERVAL_MINUTES)

MIN_HISTORY_DAYS = 28
DEFAULT_FOLDS = 7

MODEL_NAMES = (
    "weekly_profile",
    "level_adjusted_weekly",
    "weighted_same_week",
    "hybrid_50",
    "hybrid_75",
    "recent_grouped_daily",
)


def safe_float(value):
    try:
        if value is None:
            return None

        if isinstance(value, str):
            text = value.strip().lower()

            if text in (
                "",
                "unknown",
                "unavailable",
                "none",
                "nan",
            ):
                return None

            value = value.replace(",", ".")

        number = float(value)

        if math.isnan(number) or math.isinf(number):
            return None

        return number

    except Exception:
        return None


def parse_datetime(value):
    try:
        if value is None:
            return None

        if isinstance(value, datetime):
            dt = value

        else:
            text = str(value).strip()

            if not text:
                return None

            if text.endswith("Z"):
                text = text[:-1] + "+00:00"

            dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        return None


def median(values):
    clean = []

    for value in values:
        number = safe_float(value)

        if number is not None:
            clean.append(number)

    if not clean:
        return None

    return statistics.median(clean)


def mean(values):
    clean = []

    for value in values:
        number = safe_float(value)

        if number is not None:
            clean.append(number)

    if not clean:
        return None

    return sum(clean) / len(clean)


def _quarter_of_day(local_dt):
    return local_dt.hour * 4 + int(local_dt.minute / 15)


def _quarter_of_week(local_dt):
    return local_dt.weekday() * 96 + _quarter_of_day(local_dt)


def _normalize_time(timestamp):
    dt = parse_datetime(timestamp)

    if dt is None:
        return None

    local_dt = dt.astimezone(LOCAL_TZ)

    return {
        "timestamp": dt.isoformat(),
        "dt": dt,
        "local_dt": local_dt,
        "quarter_of_day": _quarter_of_day(local_dt),
        "quarter_of_week": _quarter_of_week(local_dt),
        "weekday": local_dt.weekday(),
        "hour": local_dt.hour,
    }


def _normalize_unified_row(row):
    if not isinstance(row, dict):
        return None

    market = safe_float(
        row.get("market_price_eur_kwh")
    )

    if market is None:
        return None

    timestamp = (
        row.get("slot_start_utc")
        or row.get("timestamp")
    )

    info = _normalize_time(timestamp)

    if info is None:
        return None

    return {
        "timestamp": info["timestamp"],
        "dt": info["dt"],
        "local_dt": info["local_dt"],
        "quarter_of_day": info["quarter_of_day"],
        "quarter_of_week": info["quarter_of_week"],
        "market": market,
        "source": "unified_history",
        "source_rank": 1,
    }


def _normalize_live_row(row):
    if not isinstance(row, dict):
        return None

    price = row.get("price", {})

    if not isinstance(price, dict):
        return None

    market = safe_float(
        price.get("market_price_eur_kwh")
    )

    if market is None:
        return None

    timestamp = row.get("slot_start_utc")

    info = _normalize_time(timestamp)

    if info is None:
        return None

    return {
        "timestamp": info["timestamp"],
        "dt": info["dt"],
        "local_dt": info["local_dt"],
        "quarter_of_day": info["quarter_of_day"],
        "quarter_of_week": info["quarter_of_week"],
        "market": market,
        "source": "v11_live",
        "source_rank": 2,
    }


def _read_json_lists(base_dir):
    files = []
    rows = []

    path = Path(base_dir)

    if not path.exists():
        return files, rows

    for file_path in sorted(path.rglob("*.json")):
        payload = read_json(
            file_path,
            default=[],
        )

        if not isinstance(payload, list):
            continue

        files.append(file_path)
        rows.extend(payload)

    return files, rows


def load_market_history():
    unified_files, unified_raw = _read_json_lists(
        UNIFIED_DIR
    )

    live_files, live_raw = _read_json_lists(
        RAW_DIR
    )

    candidates = []

    for row in unified_raw:
        normalized = _normalize_unified_row(row)

        if normalized is not None:
            candidates.append(normalized)

    for row in live_raw:
        normalized = _normalize_live_row(row)

        if normalized is not None:
            candidates.append(normalized)

    deduplicated = {}

    for row in candidates:
        key = row["timestamp"]

        existing = deduplicated.get(key)

        if (
            existing is None
            or row["source_rank"] >= existing["source_rank"]
        ):
            deduplicated[key] = row

    rows = list(deduplicated.values())

    rows.sort(
        key=lambda item: item["dt"]
    )

    source_counts = defaultdict(int)

    for row in rows:
        source_counts[row["source"]] += 1

    return {
        "rows": rows,
        "unified_files": len(unified_files),
        "live_files": len(live_files),
        "source_counts": dict(source_counts),
    }


def _history_before(rows, issue_dt):
    result = []

    for row in rows:
        if row["dt"] < issue_dt:
            result.append(row)

    return result


def _profile_values(
    history,
    target_dt,
    lookback_days=None,
):
    target_local = target_dt.astimezone(LOCAL_TZ)
    target_qow = _quarter_of_week(target_local)

    minimum_dt = None

    if lookback_days is not None:
        minimum_dt = (
            target_dt
            - timedelta(days=lookback_days)
        )

    values = []

    for row in history:
        if minimum_dt is not None:
            if row["dt"] < minimum_dt:
                continue

        if row["quarter_of_week"] == target_qow:
            values.append(row["market"])

    return values


def _daily_profile_values(
    history,
    target_dt,
    lookback_days=28,
):
    target_local = target_dt.astimezone(LOCAL_TZ)
    target_qod = _quarter_of_day(target_local)

    minimum_dt = (
        target_dt
        - timedelta(days=lookback_days)
    )

    values = []

    for row in history:
        if row["dt"] < minimum_dt:
            continue

        if row["quarter_of_day"] == target_qod:
            values.append(row["market"])

    return values


def _exact_lookup(history_map, target_dt):
    key = target_dt.astimezone(
        timezone.utc
    ).isoformat()

    return history_map.get(key)


def _weighted_same_week(
    history_map,
    target_dt,
):
    weighted_sum = 0.0
    weight_total = 0.0

    lags = (
        (7, 4.0),
        (14, 3.0),
        (21, 2.0),
        (28, 1.0),
    )

    for days, weight in lags:
        lag_dt = (
            target_dt
            - timedelta(days=days)
        )

        value = _exact_lookup(
            history_map,
            lag_dt,
        )

        if value is None:
            continue

        weighted_sum += (
            value * weight
        )

        weight_total += weight

    if weight_total <= 0:
        return None

    return (
        weighted_sum
        / weight_total
    )


def _recent_level_adjustment(
    history,
    issue_dt,
):
    recent_start = (
        issue_dt
        - timedelta(days=7)
    )

    reference_start = (
        issue_dt
        - timedelta(days=35)
    )

    reference_end = (
        issue_dt
        - timedelta(days=7)
    )

    recent = []
    reference = []

    for row in history:
        dt = row["dt"]

        if recent_start <= dt < issue_dt:
            recent.append(
                row["market"]
            )

        if reference_start <= dt < reference_end:
            reference.append(
                row["market"]
            )

    recent_median = median(recent)
    reference_median = median(reference)

    if (
        recent_median is None
        or reference_median is None
    ):
        return 0.0

    adjustment = (
        recent_median
        - reference_median
    )

    if adjustment > 0.08:
        adjustment = 0.08

    if adjustment < -0.08:
        adjustment = -0.08

    return adjustment


def _weekly_profile_prediction(
    history,
    target_dt,
):
    values = _profile_values(
        history,
        target_dt,
        lookback_days=56,
    )

    result = median(values)

    if result is not None:
        return result

    values = _daily_profile_values(
        history,
        target_dt,
        28,
    )

    return median(values)


def _recent_grouped_daily_prediction(history, issue_dt, target_dt):
    """Frozen 96h candidate: 28d same-quarter/day-group, 7d half-life.

    Matches the offline development candidate exactly. Workdays and weekend
    days form separate groups. No history at or after issue_dt may enter.
    """
    target_local = target_dt.astimezone(LOCAL_TZ)
    target_qod = _quarter_of_day(target_local)
    target_weekend = target_local.weekday() >= 5
    minimum_dt = issue_dt - timedelta(days=28)
    values = []
    past_history = []
    for row in history:
        row_dt = row["dt"]
        if row_dt >= issue_dt:
            continue
        past_history.append(row)
        if row_dt < minimum_dt:
            continue
        row_local = row_dt.astimezone(LOCAL_TZ)
        if _quarter_of_day(row_local) != target_qod:
            continue
        if (row_local.weekday() >= 5) != target_weekend:
            continue
        age_days = (issue_dt - row_dt).total_seconds() / 86400
        values.append((row["market"], 2 ** (-age_days / 7)))
    if values:
        return sum(value * weight for value, weight in values) / sum(weight for _, weight in values)
    return _weekly_profile_prediction(past_history, target_dt)


def predict_market_slot(
    history,
    history_map,
    issue_dt,
    target_dt,
    model_name,
):
    if model_name == "recent_grouped_daily":
        return _recent_grouped_daily_prediction(history, issue_dt, target_dt)

    weekly = _weekly_profile_prediction(
        history,
        target_dt,
    )

    same_week = _weighted_same_week(
        history_map,
        target_dt,
    )

    level_adjustment = (
        _recent_level_adjustment(
            history,
            issue_dt,
        )
    )

    adjusted_weekly = None

    if weekly is not None:
        adjusted_weekly = (
            weekly
            + level_adjustment
        )

    if model_name == "weekly_profile":
        return weekly

    if model_name == "level_adjusted_weekly":
        return adjusted_weekly

    if model_name == "weighted_same_week":
        if same_week is not None:
            return same_week

        return adjusted_weekly

    if model_name == "hybrid_50":
        if (
            same_week is not None
            and adjusted_weekly is not None
        ):
            return (
                0.50 * same_week
                + 0.50 * adjusted_weekly
            )

        if same_week is not None:
            return same_week

        return adjusted_weekly

    if model_name == "hybrid_75":
        if (
            same_week is not None
            and adjusted_weekly is not None
        ):
            return (
                0.75 * same_week
                + 0.25 * adjusted_weekly
            )

        if same_week is not None:
            return same_week

        return adjusted_weekly

    return None


def _actual_map(rows):
    result = {}

    for row in rows:
        result[
            row["timestamp"]
        ] = row["market"]

    return result


def _history_map(rows):
    result = {}

    for row in rows:
        result[
            row["timestamp"]
        ] = row["market"]

    return result


def _bucket_name(horizon_hours):
    if horizon_hours <= 24:
        return "0_24h"

    if horizon_hours <= 48:
        return "24_48h"

    if horizon_hours <= 72:
        return "48_72h"

    return "72_96h"


def _metrics(errors):
    if not errors:
        return {
            "count": 0,
            "mae_cent_kwh": None,
            "rmse_cent_kwh": None,
            "bias_cent_kwh": None,
        }

    abs_errors = []
    squared = []

    for error in errors:
        abs_errors.append(abs(error))
        squared.append(error * error)

    mae = (
        sum(abs_errors)
        / len(abs_errors)
    )

    rmse = math.sqrt(
        sum(squared)
        / len(squared)
    )

    bias = (
        sum(errors)
        / len(errors)
    )

    return {
        "count": len(errors),
        "mae_eur_kwh": round(mae, 8),
        "mae_cent_kwh": round(mae * 100, 5),
        "rmse_eur_kwh": round(rmse, 8),
        "rmse_cent_kwh": round(rmse * 100, 5),
        "bias_eur_kwh": round(bias, 8),
        "bias_cent_kwh": round(bias * 100, 5),
    }


def _forecast_test_window(
    all_rows,
    issue_dt,
    model_name,
):
    history = _history_before(
        all_rows,
        issue_dt,
    )

    history_map = _history_map(
        history
    )

    actuals = _actual_map(
        all_rows
    )

    errors_all = []
    errors_36_96 = []

    bucket_errors = {
        "0_24h": [],
        "24_48h": [],
        "48_72h": [],
        "72_96h": [],
    }

    predictions = 0
    actual_slots = 0

    for slot_index in range(
        1,
        HORIZON_SLOTS + 1,
    ):
        target_dt = (
            issue_dt
            + timedelta(
                minutes=(
                    INTERVAL_MINUTES
                    * slot_index
                )
            )
        )

        key = (
            target_dt
            .astimezone(
                timezone.utc
            )
            .isoformat()
        )

        actual = actuals.get(key)

        if actual is None:
            continue

        actual_slots += 1

        predicted = predict_market_slot(
            history,
            history_map,
            issue_dt,
            target_dt,
            model_name,
        )

        if predicted is None:
            continue

        predictions += 1

        error = (
            predicted
            - actual
        )

        horizon_hours = (
            slot_index
            * INTERVAL_MINUTES
            / 60
        )

        errors_all.append(error)

        bucket = _bucket_name(
            horizon_hours
        )

        bucket_errors[
            bucket
        ].append(
            error
        )

        if horizon_hours > 36:
            errors_36_96.append(
                error
            )

    bucket_metrics = {}

    for name, errors in (
        bucket_errors.items()
    ):
        bucket_metrics[name] = (
            _metrics(errors)
        )

    return {
        "actual_slots": actual_slots,
        "predicted_slots": predictions,
        "coverage_pct": (
            round(
                (
                    predictions
                    / actual_slots
                    * 100
                ),
                2,
            )
            if actual_slots
            else 0.0
        ),
        "all_96h": _metrics(
            errors_all
        ),
        "36_96h": _metrics(
            errors_36_96
        ),
        "horizon_buckets": bucket_metrics,
    }


def _build_issue_points(
    rows,
    requested_folds,
):
    if not rows:
        return []

    first_dt = rows[0]["dt"]
    last_dt = rows[-1]["dt"]

    earliest_issue = (
        first_dt
        + timedelta(
            days=MIN_HISTORY_DAYS
        )
    )

    latest_issue = (
        last_dt
        - timedelta(
            hours=HORIZON_HOURS
        )
    )

    if latest_issue <= earliest_issue:
        return []

    candidates = []

    local_start = (
        earliest_issue
        .astimezone(
            LOCAL_TZ
        )
        .date()
    )

    local_end = (
        latest_issue
        .astimezone(
            LOCAL_TZ
        )
        .date()
    )

    current_date = local_start

    while current_date <= local_end:
        local_issue = datetime(
            current_date.year,
            current_date.month,
            current_date.day,
            13,
            15,
            tzinfo=LOCAL_TZ,
        )

        issue_dt = (
            local_issue
            .astimezone(
                timezone.utc
            )
        )

        if (
            earliest_issue
            <= issue_dt
            <= latest_issue
        ):
            candidates.append(
                issue_dt
            )

        current_date += timedelta(
            days=1
        )

    if not candidates:
        return []

    try:
        folds = int(
            requested_folds
        )

    except Exception:
        folds = DEFAULT_FOLDS

    if folds < 3:
        folds = 3

    if folds > 10:
        folds = 10

    if len(candidates) <= folds:
        return candidates

    selected = []

    if folds == 1:
        return [
            candidates[-1]
        ]

    last_index = (
        len(candidates)
        - 1
    )

    for index in range(folds):
        position = int(
            round(
                index
                * last_index
                / (
                    folds - 1
                )
            )
        )

        selected.append(
            candidates[position]
        )

    unique = []

    seen = set()

    for item in selected:
        key = item.isoformat()

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    return unique


def _aggregate_model(
    model_name,
    fold_results,
):
    all_mae = []
    future_mae = []

    bucket_values = {
        "0_24h": [],
        "24_48h": [],
        "48_72h": [],
        "72_96h": [],
    }

    wins = 0

    for fold in fold_results:
        model = fold["models"].get(
            model_name,
            {},
        )

        all_metric = (
            model
            .get(
                "all_96h",
                {},
            )
            .get(
                "mae_cent_kwh"
            )
        )

        future_metric = (
            model
            .get(
                "36_96h",
                {},
            )
            .get(
                "mae_cent_kwh"
            )
        )

        if all_metric is not None:
            all_mae.append(
                all_metric
            )

        if future_metric is not None:
            future_mae.append(
                future_metric
            )

        for bucket in bucket_values:
            value = (
                model
                .get(
                    "horizon_buckets",
                    {},
                )
                .get(
                    bucket,
                    {},
                )
                .get(
                    "mae_cent_kwh"
                )
            )

            if value is not None:
                bucket_values[
                    bucket
                ].append(
                    value
                )

        if (
            fold.get(
                "winner_36_96h"
            )
            == model_name
        ):
            wins += 1

    result = {
        "model": model_name,
        "wins_36_96h": wins,
        "folds": len(fold_results),
        "mean_mae_96h_cent_kwh": (
            round(
                mean(all_mae),
                5,
            )
            if all_mae
            else None
        ),
        "mean_mae_36_96h_cent_kwh": (
            round(
                mean(future_mae),
                5,
            )
            if future_mae
            else None
        ),
        "median_mae_36_96h_cent_kwh": (
            round(
                median(future_mae),
                5,
            )
            if future_mae
            else None
        ),
        "worst_mae_36_96h_cent_kwh": (
            round(
                max(future_mae),
                5,
            )
            if future_mae
            else None
        ),
    }

    horizon_summary = {}

    for bucket, values in (
        bucket_values.items()
    ):
        horizon_summary[bucket] = {
            "folds": len(values),
            "mean_mae_cent_kwh": (
                round(
                    mean(values),
                    5,
                )
                if values
                else None
            ),
        }

    result[
        "horizon_summary"
    ] = horizon_summary

    return result


def run_market_96h_backtest(
    folds=DEFAULT_FOLDS,
):
    loaded = load_market_history()

    rows = loaded["rows"]

    if len(rows) < 2500:
        return {
            "status": "not_enough_data",
            "version": MARKET_FORECASTER_VERSION,
            "rows": len(rows),
        }

    issue_points = _build_issue_points(
        rows,
        folds,
    )

    if len(issue_points) < 3:
        return {
            "status": "not_enough_folds",
            "version": MARKET_FORECASTER_VERSION,
            "rows": len(rows),
            "folds": len(issue_points),
        }

    fold_results = []

    for fold_number, issue_dt in enumerate(
        issue_points,
        start=1,
    ):
        models = {}

        winner = None
        winner_mae = None

        for model_name in MODEL_NAMES:
            result = _forecast_test_window(
                rows,
                issue_dt,
                model_name,
            )

            models[model_name] = result

            mae = safe_float(
                result
                .get(
                    "36_96h",
                    {},
                )
                .get(
                    "mae_cent_kwh"
                )
            )

            if mae is None:
                continue

            if (
                winner_mae is None
                or mae < winner_mae
            ):
                winner_mae = mae
                winner = model_name

        fold_results.append(
            {
                "fold": fold_number,
                "issue_time_utc": issue_dt.isoformat(),
                "issue_time_local": (
                    issue_dt
                    .astimezone(
                        LOCAL_TZ
                    )
                    .isoformat()
                ),
                "winner_36_96h": winner,
                "winner_mae_36_96h_cent_kwh": (
                    round(
                        winner_mae,
                        5,
                    )
                    if winner_mae
                    is not None
                    else None
                ),
                "models": models,
            }
        )

    aggregates = {}

    for model_name in MODEL_NAMES:
        aggregates[model_name] = (
            _aggregate_model(
                model_name,
                fold_results,
            )
        )

    ranked = []

    for model_name, stats in (
        aggregates.items()
    ):
        mae = safe_float(
            stats.get(
                "mean_mae_36_96h_cent_kwh"
            )
        )

        if mae is None:
            continue

        ranked.append(
            {
                "model": model_name,
                "mae": mae,
            }
        )

    ranked.sort(
        key=lambda item: item["mae"]
    )

    champion = None
    runner_up = None

    if ranked:
        champion = ranked[0]["model"]

    if len(ranked) >= 2:
        runner_up = ranked[1]["model"]

    gain_vs_runner = None

    if (
        champion is not None
        and runner_up is not None
    ):
        best_mae = ranked[0]["mae"]
        runner_mae = ranked[1]["mae"]

        if runner_mae > 0:
            gain_vs_runner = (
                (
                    runner_mae
                    - best_mae
                )
                / runner_mae
                * 100
            )

    model_payload = {
        "version": MARKET_FORECASTER_VERSION,
        "created_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "model_type": champion,
        "selection_metric": "mean_mae_36_96h_cent_kwh",
        "folds": len(fold_results),
        "training_rows": len(rows),
        "trained_through": rows[-1]["timestamp"],
        "aggregate": (
            aggregates.get(
                champion
            )
            if champion
            else None
        ),
    }

    report = {
        "version": MARKET_FORECASTER_VERSION,
        "status": "ok",
        "created_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "rows": len(rows),
        "first_timestamp": rows[0]["timestamp"],
        "last_timestamp": rows[-1]["timestamp"],
        "source_counts": loaded[
            "source_counts"
        ],
        "folds": len(fold_results),
        "issue_points": [
            item.isoformat()
            for item in issue_points
        ],
        "selection_horizon": "36_96h",
        "recommended_model": champion,
        "runner_up_model": runner_up,
        "gain_vs_runner_up_pct": (
            round(
                gain_vs_runner,
                3,
            )
            if gain_vs_runner
            is not None
            else None
        ),
        "aggregates": aggregates,
        "fold_results": fold_results,
        "notes": [
            "Elke forecast gebruikt uitsluitend marktdata van vóór het uitgiftemoment.",
            "Modelselectie gebeurt op horizon 36-96 uur omdat bekende day-ahead marktprijzen later de korte horizon vervangen.",
            "Nog geen weer, wind, PV of Solcast features.",
            "Deze versie vormt de baseline die toekomstige feature-modellen moeten verslaan.",
        ],
    }

    MARKET_MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    MARKET_ACCURACY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json_atomic(
        MODEL_FILE,
        model_payload,
    )

    write_json_atomic(
        BACKTEST_FILE,
        report,
    )

    return {
        "version": MARKET_FORECASTER_VERSION,
        "status": "ok",
        "rows": len(rows),
        "folds": len(fold_results),
        "recommended_model": champion,
        "runner_up_model": runner_up,
        "gain_vs_runner_up_pct": (
            round(
                gain_vs_runner,
                3,
            )
            if gain_vs_runner
            is not None
            else None
        ),
        "champion_mean_mae_36_96h_cent_kwh": (
            aggregates
            .get(
                champion,
                {},
            )
            .get(
                "mean_mae_36_96h_cent_kwh"
            )
            if champion
            else None
        ),
        "champion_median_mae_36_96h_cent_kwh": (
            aggregates
            .get(
                champion,
                {},
            )
            .get(
                "median_mae_36_96h_cent_kwh"
            )
            if champion
            else None
        ),
        "champion_worst_mae_36_96h_cent_kwh": (
            aggregates
            .get(
                champion,
                {},
            )
            .get(
                "worst_mae_36_96h_cent_kwh"
            )
            if champion
            else None
        ),
        "aggregates": aggregates,
        "model_file": str(
            MODEL_FILE
        ),
        "report_file": str(
            BACKTEST_FILE
        ),
    }


def build_market_96h_forecast(
    issue_time=None,
):
    loaded = load_market_history()
    rows = loaded["rows"]

    if not rows:
        return {
            "status": "no_history",
            "version": MARKET_FORECASTER_VERSION,
        }

    model_info = read_json(
        MODEL_FILE,
        default={},
    )

    model_name = None

    if isinstance(
        model_info,
        dict,
    ):
        model_name = (
            model_info.get(
                "model_type"
            )
        )

    if model_name not in MODEL_NAMES:
        model_name = (
            "level_adjusted_weekly"
        )

    if issue_time is None:
        issue_dt = datetime.now(
            timezone.utc
        )

    else:
        issue_dt = parse_datetime(
            issue_time
        )

    if issue_dt is None:
        return {
            "status": "invalid_issue_time",
            "version": MARKET_FORECASTER_VERSION,
        }

    minute = (
        int(
            issue_dt.minute
            / 15
        )
        * 15
    )

    issue_dt = issue_dt.replace(
        minute=minute,
        second=0,
        microsecond=0,
    )

    history = _history_before(
        rows,
        issue_dt,
    )

    history_map = _history_map(
        history
    )

    forecast_rows = []

    for slot_index in range(
        1,
        HORIZON_SLOTS + 1,
    ):
        target_dt = (
            issue_dt
            + timedelta(
                minutes=(
                    INTERVAL_MINUTES
                    * slot_index
                )
            )
        )

        predicted = predict_market_slot(
            history,
            history_map,
            issue_dt,
            target_dt,
            model_name,
        )

        horizon_hours = (
            slot_index
            * INTERVAL_MINUTES
            / 60
        )

        confidence = 45

        if horizon_hours <= 24:
            confidence = 65

        elif horizon_hours <= 48:
            confidence = 55

        elif horizon_hours <= 72:
            confidence = 48

        forecast_rows.append(
            {
                "timestamp_utc": (
                    target_dt
                    .astimezone(
                        timezone.utc
                    )
                    .isoformat()
                ),
                "timestamp_local": (
                    target_dt
                    .astimezone(
                        LOCAL_TZ
                    )
                    .isoformat()
                ),
                "horizon_hours": round(
                    horizon_hours,
                    2,
                ),
                "market_price_eur_kwh": (
                    round(
                        predicted,
                        7,
                    )
                    if predicted
                    is not None
                    else None
                ),
                "market_price_cent_kwh": (
                    round(
                        predicted * 100,
                        4,
                    )
                    if predicted
                    is not None
                    else None
                ),
                "source": "ai_market_baseline",
                "model": model_name,
                "confidence_pct": confidence,
            }
        )

    valid_prices = [
        row["market_price_eur_kwh"]
        for row in forecast_rows
        if row["market_price_eur_kwh"]
        is not None
    ]

    payload = {
        "version": MARKET_FORECASTER_VERSION,
        "status": "ok",
        "created_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "issue_time_utc": issue_dt.isoformat(),
        "issue_time_local": (
            issue_dt
            .astimezone(
                LOCAL_TZ
            )
            .isoformat()
        ),
        "model": model_name,
        "horizon_hours": HORIZON_HOURS,
        "interval_minutes": INTERVAL_MINUTES,
        "slots": len(forecast_rows),
        "valid_slots": len(valid_prices),
        "minimum_eur_kwh": (
            round(
                min(valid_prices),
                7,
            )
            if valid_prices
            else None
        ),
        "maximum_eur_kwh": (
            round(
                max(valid_prices),
                7,
            )
            if valid_prices
            else None
        ),
        "average_eur_kwh": (
            round(
                mean(valid_prices),
                7,
            )
            if valid_prices
            else None
        ),
        "forecast": forecast_rows,
    }

    MARKET_PREDICTION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json_atomic(
        FORECAST_FILE,
        payload,
    )

    return {
        "version": MARKET_FORECASTER_VERSION,
        "status": "ok",
        "model": model_name,
        "slots": len(forecast_rows),
        "valid_slots": len(valid_prices),
        "minimum_cent_kwh": (
            round(
                min(valid_prices) * 100,
                4,
            )
            if valid_prices
            else None
        ),
        "maximum_cent_kwh": (
            round(
                max(valid_prices) * 100,
                4,
            )
            if valid_prices
            else None
        ),
        "average_cent_kwh": (
            round(
                mean(valid_prices) * 100,
                4,
            )
            if valid_prices
            else None
        ),
        "forecast_file": str(
            FORECAST_FILE
        ),
    }


def market_forecaster_self_test():
    rows = []

    start = datetime(
        2026,
        1,
        1,
        tzinfo=timezone.utc,
    )

    for index in range(
        70 * 96
    ):
        dt = (
            start
            + timedelta(
                minutes=(
                    index * 15
                )
            )
        )

        local_dt = dt.astimezone(
            LOCAL_TZ
        )

        qod = _quarter_of_day(
            local_dt
        )

        weekday = (
            local_dt.weekday()
        )

        daily_shape = (
            math.sin(
                (
                    qod
                    / 96
                )
                * math.pi
                * 2
            )
            * 0.025
        )

        weekend_effect = (
            -0.01
            if weekday >= 5
            else 0.0
        )

        weekly_wave = (
            math.sin(
                (
                    index
                    / (
                        96 * 7
                    )
                )
                * math.pi
                * 2
            )
            * 0.008
        )

        market = (
            0.09
            + daily_shape
            + weekend_effect
            + weekly_wave
        )

        rows.append(
            {
                "timestamp": dt.isoformat(),
                "dt": dt,
                "local_dt": local_dt,
                "quarter_of_day": qod,
                "quarter_of_week": (
                    weekday * 96
                    + qod
                ),
                "market": market,
                "source": "synthetic",
                "source_rank": 1,
            }
        )

    issues = _build_issue_points(
        rows,
        5,
    )

    if not issues:
        return {
            "status": "error",
            "version": MARKET_FORECASTER_VERSION,
            "reason": "no_test_folds",
        }

    results = {}

    for model_name in MODEL_NAMES:
        maes = []

        for issue_dt in issues:
            result = _forecast_test_window(
                rows,
                issue_dt,
                model_name,
            )

            mae = safe_float(
                result
                .get(
                    "36_96h",
                    {},
                )
                .get(
                    "mae_cent_kwh"
                )
            )

            if mae is not None:
                maes.append(mae)

        results[model_name] = (
            mean(maes)
            if maes
            else None
        )

    valid = {
        key: value
        for key, value in results.items()
        if value is not None
    }

    ok = (
        len(valid) >= 3
        and min(valid.values()) < 2.0
    )

    return {
        "status": (
            "ok"
            if ok
            else "error"
        ),
        "version": MARKET_FORECASTER_VERSION,
        "folds": len(issues),
        "models": {
            key: (
                round(value, 5)
                if value
                is not None
                else None
            )
            for key, value in results.items()
        },
    }
