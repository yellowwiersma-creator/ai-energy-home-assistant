from .config import ROOT_DIR as CONFIG_ROOT_DIR
from pathlib import Path
import math

from .storage import read_json


DASHBOARD_ADAPTER_VERSION = "11.6.2-dashboard-stable"

ROOT_DIR = CONFIG_ROOT_DIR
DATA_DIR = ROOT_DIR / "data"

FORECAST_FILE = (
    DATA_DIR
    / "predictions"
    / "retail"
    / "retail_96h_latest.json"
)

DECISION_FILE = (
    DATA_DIR
    / "predictions"
    / "decision"
    / "decision_96h_latest.json"
)

GOVERNOR_FILE = (
    DATA_DIR
    / "accuracy"
    / "retail"
    / "governor_latest.json"
)

ACCURACY_FILE = (
    DATA_DIR
    / "accuracy"
    / "forecast"
    / "forecast_evaluation_latest.json"
)

LEDGER_FILE = (
    DATA_DIR
    / "forecast_inputs"
    / "latest.json"
)

FORECAST_ARCHIVE_DIR = (
    DATA_DIR
    / "predictions"
    / "retail"
    / "archive"
)

INPUT_ARCHIVE_DIR = (
    DATA_DIR
    / "forecast_inputs"
    / "archive"
)


def safe_float(value):
    try:
        if value is None:
            return None

        number = float(value)

        if math.isnan(number) or math.isinf(number):
            return None

        return number

    except Exception:
        return None


def safe_int(value):
    try:
        if value is None:
            return None

        return int(value)

    except Exception:
        return None


def _count_json_files(path):
    try:
        if not path.exists():
            return 0

        count = 0

        for _ in path.rglob("*.json"):
            count += 1

        return count

    except Exception:
        return 0


def _price_summary(rows):
    retail = []
    market = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        r = safe_float(
            row.get(
                "retail_price_cent_kwh"
            )
        )

        m = safe_float(
            row.get(
                "market_price_cent_kwh"
            )
        )

        if r is not None:
            retail.append(r)

        if m is not None:
            market.append(m)

    result = {
        "retail_min_cent": None,
        "retail_avg_cent": None,
        "retail_max_cent": None,
        "market_min_cent": None,
        "market_avg_cent": None,
        "market_max_cent": None,
    }

    if retail:
        result["retail_min_cent"] = round(
            min(retail),
            4,
        )

        result["retail_avg_cent"] = round(
            sum(retail) / len(retail),
            4,
        )

        result["retail_max_cent"] = round(
            max(retail),
            4,
        )

    if market:
        result["market_min_cent"] = round(
            min(market),
            4,
        )

        result["market_avg_cent"] = round(
            sum(market) / len(market),
            4,
        )

        result["market_max_cent"] = round(
            max(market),
            4,
        )

    return result


def _weather_summary(ledger):
    if not isinstance(ledger, dict):
        return {}

    weather = ledger.get(
        "weather",
        {},
    )

    if not isinstance(weather, dict):
        weather = {}

    entity = (
        ledger.get("weather_entity")
        or weather.get("entity")
        or weather.get("weather_entity")
    )

    hourly = (
        weather.get("hourly_forecast")
        or weather.get("hourly")
        or weather.get("forecast_hourly")
        or ledger.get("weather_hourly")
        or []
    )

    daily = (
        weather.get("daily_forecast")
        or weather.get("daily")
        or weather.get("forecast_daily")
        or ledger.get("weather_daily")
        or []
    )

    if not isinstance(hourly, list):
        hourly = []

    if not isinstance(daily, list):
        daily = []

    hourly_slots = safe_int(
        ledger.get(
            "weather_hourly_slots"
        )
    )

    daily_slots = safe_int(
        ledger.get(
            "weather_daily_slots"
        )
    )

    if hourly_slots is None:
        hourly_slots = len(hourly)

    if daily_slots is None:
        daily_slots = len(daily)

    return {
        "entity":
            entity,

        "hourly_slots":
            hourly_slots,

        "daily_slots":
            daily_slots,

        "hourly_horizon_hours":
            safe_float(
                ledger.get(
                    "weather_hourly_horizon_hours"
                )
            ),

        "daily_horizon_hours":
            safe_float(
                ledger.get(
                    "weather_daily_horizon_hours"
                )
            ),
    }


def load_dashboard_payload():
    forecast_payload = read_json(
        FORECAST_FILE,
        default={},
    )

    decision_payload = read_json(
        DECISION_FILE,
        default={},
    )

    governor_payload = read_json(
        GOVERNOR_FILE,
        default={},
    )

    accuracy_payload = read_json(
        ACCURACY_FILE,
        default={},
    )

    ledger_payload = read_json(
        LEDGER_FILE,
        default={},
    )

    if not isinstance(
        forecast_payload,
        dict,
    ):
        return {
            "version":
                DASHBOARD_ADAPTER_VERSION,

            "status":
                "missing_forecast",

            "core_ready":
                False,
        }

    raw_forecast = forecast_payload.get(
        "forecast",
        [],
    )

    if not isinstance(
        raw_forecast,
        list,
    ):
        return {
            "version":
                DASHBOARD_ADAPTER_VERSION,

            "status":
                "invalid_forecast",

            "core_ready":
                False,
        }

    confidence_map = {}

    if isinstance(
        decision_payload,
        dict,
    ):
        decision_rows = decision_payload.get(
            "forecast",
            [],
        )

        if isinstance(
            decision_rows,
            list,
        ):
            for row in decision_rows:
                if not isinstance(
                    row,
                    dict,
                ):
                    continue

                timestamp = row.get(
                    "timestamp_utc"
                )

                if timestamp:
                    confidence_map[
                        timestamp
                    ] = row.get(
                        "confidence_level"
                    )

    compact = []

    known_slots = 0
    ai_slots = 0

    for row in raw_forecast:
        if not isinstance(
            row,
            dict,
        ):
            continue

        timestamp_utc = row.get(
            "timestamp_utc"
        )

        timestamp_local = row.get(
            "timestamp_local"
        )

        retail = safe_float(
            row.get(
                "retail_price_cent_kwh"
            )
        )

        market = safe_float(
            row.get(
                "market_price_cent_kwh"
            )
        )

        if not timestamp_utc:
            continue

        if retail is None:
            continue

        source = row.get(
            "market_source",
            "unknown",
        )

        if source == "nordpool_known":
            known_slots += 1

        elif source == "ai_market_forecast":
            ai_slots += 1

        compact.append(
            {
                "timestamp":
                    (
                        timestamp_local
                        or timestamp_utc
                    ),

                "timestamp_utc":
                    timestamp_utc,

                "retail_cent":
                    round(
                        retail,
                        5,
                    ),

                "market_cent":
                    (
                        round(
                            market,
                            5,
                        )
                        if market is not None
                        else None
                    ),

                "source":
                    source,

                "confidence":
                    confidence_map.get(
                        timestamp_utc
                    ),
            }
        )

    summary = _price_summary(
        raw_forecast
    )

    safe_choice = {}

    blocks = {}

    confidence_counts = {}

    if isinstance(
        decision_payload,
        dict,
    ):
        safe_choice = decision_payload.get(
            "safe_choice",
            {},
        )

        blocks = decision_payload.get(
            "blocks",
            {},
        )

        confidence_counts = decision_payload.get(
            "confidence_counts",
            {},
        )

    if not isinstance(
        safe_choice,
        dict,
    ):
        safe_choice = {}

    if not isinstance(
        blocks,
        dict,
    ):
        blocks = {}

    if not isinstance(
        confidence_counts,
        dict,
    ):
        confidence_counts = {}

    selected = safe_choice.get(
        "selected",
        {},
    )

    best_expected = safe_choice.get(
        "best_expected",
        {},
    )

    best_known = safe_choice.get(
        "best_known",
        {},
    )

    if not isinstance(
        selected,
        dict,
    ):
        selected = {}

    if not isinstance(
        best_expected,
        dict,
    ):
        best_expected = {}

    if not isinstance(
        best_known,
        dict,
    ):
        best_known = {}

    governor = {}

    if isinstance(
        governor_payload,
        dict,
    ):
        governor = {
            "status":
                governor_payload.get(
                    "status"
                ),

            "champion":
                governor_payload.get(
                    "champion_after"
                ),

            "champion_strength":
                governor_payload.get(
                    "champion_strength_after"
                ),

            "trained_rows":
                governor_payload.get(
                    "champion_trained_rows_after"
                ),

            "new_rows":
                governor_payload.get(
                    "new_rows"
                ),

            "runner_up":
                governor_payload.get(
                    "runner_up_model"
                ),

            "forward_validated":
                governor_payload.get(
                    "forward_validated"
                ),

            "mean_mae_cent":
                governor_payload.get(
                    "recommended_mean_mae_cent_kwh"
                ),

            "gain_vs_constant_pct":
                governor_payload.get(
                    "gain_vs_constant_pct"
                ),

            "gain_vs_runner_up_pct":
                governor_payload.get(
                    "gain_vs_runner_up_pct"
                ),

            "action":
                governor_payload.get(
                    "policy_action"
                ),

            "action_reason":
                governor_payload.get(
                    "policy_reason"
                ),
        }

    accuracy = {
        "evaluated_points": 0,
        "unique_actual_slots": 0,
        "retail_mae_cent": None,
        "ai_market_mae_cent": None,
        "known_retail_mae_cent": None,
    }

    if isinstance(
        accuracy_payload,
        dict,
    ):
        retail_overall = accuracy_payload.get(
            "retail_overall",
            {},
        )

        market_by_source = accuracy_payload.get(
            "market_by_source",
            {},
        )

        retail_by_source = accuracy_payload.get(
            "retail_by_market_source",
            {},
        )

        if not isinstance(
            retail_overall,
            dict,
        ):
            retail_overall = {}

        if not isinstance(
            market_by_source,
            dict,
        ):
            market_by_source = {}

        if not isinstance(
            retail_by_source,
            dict,
        ):
            retail_by_source = {}

        ai_market = market_by_source.get(
            "ai_market_forecast",
            {},
        )

        known_retail = retail_by_source.get(
            "nordpool_known",
            {},
        )

        if not isinstance(
            ai_market,
            dict,
        ):
            ai_market = {}

        if not isinstance(
            known_retail,
            dict,
        ):
            known_retail = {}

        accuracy = {
            "evaluated_points":
                accuracy_payload.get(
                    "evaluated_points",
                    0,
                ),

            "unique_actual_slots":
                accuracy_payload.get(
                    "unique_actual_slots",
                    0,
                ),

            "retail_mae_cent":
                retail_overall.get(
                    "mae_cent_kwh"
                ),

            "ai_market_mae_cent":
                ai_market.get(
                    "mae_cent_kwh"
                ),

            "known_retail_mae_cent":
                known_retail.get(
                    "mae_cent_kwh"
                ),
        }

    weather = _weather_summary(
        ledger_payload
    )

    decision_ok = (
        isinstance(
            decision_payload,
            dict,
        )
        and decision_payload.get(
            "status"
        )
        == "ok"
    )

    core_ready = (
        len(compact) == 384
        and decision_ok
    )

    return {
        "version":
            DASHBOARD_ADAPTER_VERSION,

        "status":
            "ok",

        "core_ready":
            core_ready,

        "issue_time_local":
            forecast_payload.get(
                "issue_time_local"
            ),

        "forecast_points":
            len(compact),

        "known_market_slots":
            known_slots,

        "ai_market_slots":
            ai_slots,

        "known_market_pct":
            round(
                (
                    known_slots
                    / len(compact)
                    * 100
                )
                if compact
                else 0,
                1,
            ),

        "market_model":
            forecast_payload.get(
                "market_baseline_model"
            ),

        "retail_model":
            forecast_payload.get(
                "retail_champion"
            ),

        "retail_min_cent":
            summary.get(
                "retail_min_cent"
            ),

        "retail_avg_cent":
            summary.get(
                "retail_avg_cent"
            ),

        "retail_max_cent":
            summary.get(
                "retail_max_cent"
            ),

        "market_min_cent":
            summary.get(
                "market_min_cent"
            ),

        "market_avg_cent":
            summary.get(
                "market_avg_cent"
            ),

        "market_max_cent":
            summary.get(
                "market_max_cent"
            ),

        "decision":
            safe_choice.get(
                "decision"
            ),

        "decision_reason":
            safe_choice.get(
                "reason"
            ),

        "selected":
            selected,

        "best_expected":
            best_expected,

        "best_known":
            best_known,

        "expected_saving_cent":
            safe_choice.get(
                "expected_saving_vs_known_cent_kwh"
            ),

        "required_extra_advantage_cent":
            safe_choice.get(
                "required_extra_advantage_cent_kwh"
            ),

        "safety_gap_cent":
            safe_choice.get(
                "safety_gap_cent_kwh"
            ),

        "confidence_counts":
            confidence_counts,

        "blocks":
            blocks,

        "governor":
            governor,

        "accuracy":
            accuracy,

        "weather":
            weather,

        "forecast_archive_count":
            _count_json_files(
                FORECAST_ARCHIVE_DIR
            ),

        "forecast_input_snapshot_count":
            _count_json_files(
                INPUT_ARCHIVE_DIR
            ),

        "retail_unit": "ct/kWh",
            "retail_price_unit": "ct/kWh",
        "market_unit": "ct/kWh",
        "interval_minutes": 15,

        "forecast":
            compact,
    }


def dashboard_adapter_self_test():
    result = load_dashboard_payload()

    return {
        "version":
            DASHBOARD_ADAPTER_VERSION,

        "status":
            result.get(
                "status"
            ),

        "core_ready":
            result.get(
                "core_ready"
            ),

        "forecast_points":
            result.get(
                "forecast_points"
            ),

        "known_market_slots":
            result.get(
                "known_market_slots"
            ),

        "ai_market_slots":
            result.get(
                "ai_market_slots"
            ),
    }
