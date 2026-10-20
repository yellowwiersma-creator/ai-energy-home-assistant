from .config import ROOT_DIR as CONFIG_ROOT_DIR
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import math

from .config import TIMEZONE

from .storage import (
    read_json,
    write_json_atomic,
)

from .retail_learner import (
    predict_row,
)


FORECAST_COMPOSER_VERSION = "11.5.2-end-to-end-composer"

LOCAL_TZ = ZoneInfo(TIMEZONE)

ROOT_DIR = CONFIG_ROOT_DIR

DATA_DIR = (
    ROOT_DIR
    / "data"
)

FORECAST_LEDGER_FILE = (
    DATA_DIR
    / "forecast_inputs"
    / "latest.json"
)

RETAIL_CHAMPION_FILE = (
    DATA_DIR
    / "models"
    / "retail"
    / "retail_champion.json"
)

RETAIL_FORWARD_REPORT_FILE = (
    DATA_DIR
    / "accuracy"
    / "retail"
    / "forward_validation_latest.json"
)

MARKET_BACKTEST_FILE = (
    DATA_DIR
    / "accuracy"
    / "market"
    / "market_96h_backtest_latest.json"
)

OUTPUT_DIR = (
    DATA_DIR
    / "predictions"
    / "retail"
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "retail_96h_latest.json"
)


def safe_float(value):
    try:
        if value is None:
            return None

        if isinstance(value, str):
            text = (
                value
                .strip()
                .lower()
            )

            if text in (
                "",
                "unknown",
                "unavailable",
                "none",
                "nan",
            ):
                return None

            value = value.replace(
                ",",
                ".",
            )

        number = float(value)

        if (
            math.isnan(number)
            or math.isinf(number)
        ):
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
                text = (
                    text[:-1]
                    + "+00:00"
                )

            dt = datetime.fromisoformat(
                text
            )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:
        return None


def _hour_of_week(
    timestamp,
):
    dt = parse_datetime(
        timestamp
    )

    if dt is None:
        return None

    local_dt = (
        dt
        .astimezone(
            LOCAL_TZ
        )
    )

    return (
        local_dt.weekday()
        * 24
        + local_dt.hour
    )


def _known_market_map(
    ledger,
):
    result = {}

    if not isinstance(
        ledger,
        dict,
    ):
        return result

    market = ledger.get(
        "market",
        {},
    )

    if not isinstance(
        market,
        dict,
    ):
        return result

    rows = market.get(
        "known_market",
        [],
    )

    if not isinstance(
        rows,
        list,
    ):
        return result

    for row in rows:
        if not isinstance(
            row,
            dict,
        ):
            continue

        timestamp = row.get(
            "timestamp_utc"
        )

        price = safe_float(
            row.get(
                "market_price_eur_kwh"
            )
        )

        if (
            timestamp is None
            or price is None
        ):
            continue

        dt = parse_datetime(
            timestamp
        )

        if dt is None:
            continue

        result[
            dt.isoformat()
        ] = price

    return result


def _market_baseline_rows(
    ledger,
):
    if not isinstance(
        ledger,
        dict,
    ):
        return []

    market = ledger.get(
        "market",
        {},
    )

    if not isinstance(
        market,
        dict,
    ):
        return []

    rows = market.get(
        "baseline_forecast",
        [],
    )

    if not isinstance(
        rows,
        list,
    ):
        return []

    result = []

    for row in rows:
        if not isinstance(
            row,
            dict,
        ):
            continue

        timestamp = row.get(
            "timestamp_utc"
        )

        price = safe_float(
            row.get(
                "market_price_eur_kwh"
            )
        )

        if (
            timestamp is None
            or price is None
        ):
            continue

        dt = parse_datetime(
            timestamp
        )

        if dt is None:
            continue

        result.append(
            {
                "timestamp_utc":
                    dt.isoformat(),

                "timestamp_local":
                    dt.astimezone(
                        LOCAL_TZ
                    ).isoformat(),

                "horizon_hours":
                    safe_float(
                        row.get(
                            "horizon_hours"
                        )
                    ),

                "market_price_eur_kwh":
                    price,

                "baseline_source":
                    row.get(
                        "source"
                    ),

                "baseline_model":
                    row.get(
                        "model"
                    ),
            }
        )

    result.sort(
        key=lambda row:
            row[
                "timestamp_utc"
            ]
    )

    return result


def _retail_forward_mae():
    report = read_json(
        RETAIL_FORWARD_REPORT_FILE,
        default={},
    )

    if not isinstance(
        report,
        dict,
    ):
        return None

    recommended = report.get(
        "recommended_model"
    )

    aggregates = report.get(
        "aggregates",
        {},
    )

    if not isinstance(
        aggregates,
        dict,
    ):
        return None

    stats = aggregates.get(
        recommended,
        {},
    )

    if not isinstance(
        stats,
        dict,
    ):
        return None

    return safe_float(
        stats.get(
            "mean_mae_cent_kwh"
        )
    )


def _market_horizon_mae(
    horizon_hours,
):
    report = read_json(
        MARKET_BACKTEST_FILE,
        default={},
    )

    if not isinstance(
        report,
        dict,
    ):
        return None

    champion = report.get(
        "recommended_model"
    )

    aggregates = report.get(
        "aggregates",
        {},
    )

    if not isinstance(
        aggregates,
        dict,
    ):
        return None

    stats = aggregates.get(
        champion,
        {},
    )

    if not isinstance(
        stats,
        dict,
    ):
        return None

    horizons = stats.get(
        "horizon_summary",
        {},
    )

    if not isinstance(
        horizons,
        dict,
    ):
        return None

    horizon = safe_float(
        horizon_hours
    )

    if horizon is None:
        return None

    if horizon <= 24:
        bucket = "0_24h"

    elif horizon <= 48:
        bucket = "24_48h"

    elif horizon <= 72:
        bucket = "48_72h"

    else:
        bucket = "72_96h"

    bucket_stats = horizons.get(
        bucket,
        {},
    )

    if not isinstance(
        bucket_stats,
        dict,
    ):
        return None

    return safe_float(
        bucket_stats.get(
            "mean_mae_cent_kwh"
        )
    )


def _retail_prediction(
    champion,
    market_price,
    timestamp,
):
    how = _hour_of_week(
        timestamp
    )

    if how is None:
        return None

    row = {
        "market":
            market_price,

        "hour_of_week":
            how,
    }

    return predict_row(
        champion,
        row,
    )


def _source_summary(
    rows,
):
    known = 0
    ai = 0

    for row in rows:
        source = row.get(
            "market_source"
        )

        if source == (
            "nordpool_known"
        ):
            known += 1

        elif source == (
            "ai_market_forecast"
        ):
            ai += 1

    return {
        "known_market_slots":
            known,

        "ai_market_slots":
            ai,

        "total_slots":
            len(rows),
    }


def _price_summary(
    rows,
):
    market_prices = []

    retail_prices = []

    for row in rows:
        market = safe_float(
            row.get(
                "market_price_eur_kwh"
            )
        )

        retail = safe_float(
            row.get(
                "retail_price_eur_kwh"
            )
        )

        if market is not None:
            market_prices.append(
                market
            )

        if retail is not None:
            retail_prices.append(
                retail
            )

    result = {
        "market_valid_slots":
            len(
                market_prices
            ),

        "retail_valid_slots":
            len(
                retail_prices
            ),
    }

    if market_prices:
        result[
            "market_min_cent_kwh"
        ] = round(
            min(market_prices)
            * 100,
            4,
        )

        result[
            "market_avg_cent_kwh"
        ] = round(
            (
                sum(market_prices)
                / len(market_prices)
            )
            * 100,
            4,
        )

        result[
            "market_max_cent_kwh"
        ] = round(
            max(market_prices)
            * 100,
            4,
        )

    if retail_prices:
        result[
            "retail_min_cent_kwh"
        ] = round(
            min(retail_prices)
            * 100,
            4,
        )

        result[
            "retail_avg_cent_kwh"
        ] = round(
            (
                sum(retail_prices)
                / len(retail_prices)
            )
            * 100,
            4,
        )

        result[
            "retail_max_cent_kwh"
        ] = round(
            max(retail_prices)
            * 100,
            4,
        )

    return result


def _cheapest_slots(
    rows,
    count=12,
):
    candidates = []

    for row in rows:
        price = safe_float(
            row.get(
                "retail_price_eur_kwh"
            )
        )

        if price is None:
            continue

        candidates.append(
            {
                "timestamp_local":
                    row.get(
                        "timestamp_local"
                    ),

                "retail_price_cent_kwh":
                    round(
                        price
                        * 100,
                        4,
                    ),

                "market_source":
                    row.get(
                        "market_source"
                    ),
            }
        )

    candidates.sort(
        key=lambda row:
            row[
                "retail_price_cent_kwh"
            ]
    )

    return candidates[
        :count
    ]


def build_end_to_end_forecast():
    ledger = read_json(
        FORECAST_LEDGER_FILE,
        default={},
    )

    if not isinstance(
        ledger,
        dict,
    ):
        return {
            "status":
                "missing_ledger",

            "version":
                FORECAST_COMPOSER_VERSION,
        }

    baseline_rows = (
        _market_baseline_rows(
            ledger
        )
    )

    if not baseline_rows:
        return {
            "status":
                "missing_market_baseline",

            "version":
                FORECAST_COMPOSER_VERSION,
        }

    known_map = (
        _known_market_map(
            ledger
        )
    )

    champion = read_json(
        RETAIL_CHAMPION_FILE,
        default={},
    )

    if not isinstance(
        champion,
        dict,
    ):
        return {
            "status":
                "missing_retail_champion",

            "version":
                FORECAST_COMPOSER_VERSION,
        }

    champion_type = champion.get(
        "model_type"
    )

    if not champion_type:
        return {
            "status":
                "invalid_retail_champion",

            "version":
                FORECAST_COMPOSER_VERSION,
        }

    retail_mae = (
        _retail_forward_mae()
    )

    output_rows = []

    for baseline in baseline_rows:
        timestamp = baseline[
            "timestamp_utc"
        ]

        baseline_price = (
            baseline[
                "market_price_eur_kwh"
            ]
        )

        known_price = (
            known_map.get(
                timestamp
            )
        )

        if known_price is not None:
            market_price = known_price

            market_source = (
                "nordpool_known"
            )

            market_model = (
                "official_nordpool"
            )

            market_mae = 0.0

        else:
            market_price = (
                baseline_price
            )

            market_source = (
                "ai_market_forecast"
            )

            market_model = (
                baseline.get(
                    "baseline_model"
                )
            )

            market_mae = (
                _market_horizon_mae(
                    baseline.get(
                        "horizon_hours"
                    )
                )
            )

        retail_price = (
            _retail_prediction(
                champion,
                market_price,
                timestamp,
            )
        )

        output_rows.append(
            {
                "timestamp_utc":
                    timestamp,

                "timestamp_local":
                    baseline.get(
                        "timestamp_local"
                    ),

                "horizon_hours":
                    baseline.get(
                        "horizon_hours"
                    ),

                "market_price_eur_kwh":
                    round(
                        market_price,
                        7,
                    ),

                "market_price_cent_kwh":
                    round(
                        market_price
                        * 100,
                        4,
                    ),

                "market_source":
                    market_source,

                "market_model":
                    market_model,

                "market_expected_mae_cent_kwh":
                    (
                        round(
                            market_mae,
                            4,
                        )
                        if market_mae
                        is not None
                        else None
                    ),

                "retail_price_eur_kwh":
                    (
                        round(
                            retail_price,
                            7,
                        )
                        if retail_price
                        is not None
                        else None
                    ),

                "retail_price_cent_kwh":
                    (
                        round(
                            retail_price
                            * 100,
                            4,
                        )
                        if retail_price
                        is not None
                        else None
                    ),

                "retail_model":
                    champion_type,

                "retail_expected_mae_cent_kwh":
                    (
                        round(
                            retail_mae,
                            4,
                        )
                        if retail_mae
                        is not None
                        else None
                    ),

                "confidence_basis":
                    (
                        "official_market_plus_retail_model"
                        if market_source
                        == "nordpool_known"
                        else
                        "ai_market_plus_retail_model"
                    ),
            }
        )

    source_summary = (
        _source_summary(
            output_rows
        )
    )

    price_summary = (
        _price_summary(
            output_rows
        )
    )

    payload = {
        "version":
            FORECAST_COMPOSER_VERSION,

        "status":
            "ok",

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "ledger_version":
            ledger.get(
                "version"
            ),

        "issue_time_utc":
            ledger.get(
                "issue_time_utc"
            ),

        "issue_time_local":
            ledger.get(
                "issue_time_local"
            ),

        "market_baseline_model":
            ledger.get(
                "market",
                {},
            ).get(
                "baseline_model"
            ),

        "retail_champion":
            champion_type,

        "slots":
            len(
                output_rows
            ),

        "source_summary":
            source_summary,

        "price_summary":
            price_summary,

        "cheapest_12_quarters":
            _cheapest_slots(
                output_rows,
                12,
            ),

        "forecast":
            output_rows,

        "notes": [
            "Bekende Nord Pool-prijzen overschrijven altijd de AI-marktforecast.",
            "Onbekende marktkwartieren gebruiken de geselecteerde 96-uurs marktbaseline.",
            "Retailprijs wordt berekend met het forward-gevalideerde retail champion-model.",
            "Markt- en retail-MAE worden afzonderlijk gerapporteerd en niet kunstmatig gecombineerd tot één confidencegetal.",
        ],
    }

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json_atomic(
        OUTPUT_FILE,
        payload,
    )

    return {
        "version":
            FORECAST_COMPOSER_VERSION,

        "status":
            "ok",

        "slots":
            len(
                output_rows
            ),

        "known_market_slots":
            source_summary.get(
                "known_market_slots"
            ),

        "ai_market_slots":
            source_summary.get(
                "ai_market_slots"
            ),

        "retail_model":
            champion_type,

        "market_baseline_model":
            ledger.get(
                "market",
                {},
            ).get(
                "baseline_model"
            ),

        "market_min_cent_kwh":
            price_summary.get(
                "market_min_cent_kwh"
            ),

        "market_avg_cent_kwh":
            price_summary.get(
                "market_avg_cent_kwh"
            ),

        "market_max_cent_kwh":
            price_summary.get(
                "market_max_cent_kwh"
            ),

        "retail_min_cent_kwh":
            price_summary.get(
                "retail_min_cent_kwh"
            ),

        "retail_avg_cent_kwh":
            price_summary.get(
                "retail_avg_cent_kwh"
            ),

        "retail_max_cent_kwh":
            price_summary.get(
                "retail_max_cent_kwh"
            ),

        "retail_expected_mae_cent_kwh":
            retail_mae,

        "cheapest_12_quarters":
            payload.get(
                "cheapest_12_quarters"
            ),

        "output_file":
            str(
                OUTPUT_FILE
            ),
    }


def forecast_composer_self_test():
    champion = {
        "model_type":
            "linear_market",

        "parameters": {
            "slope":
                1.15,

            "intercept":
                0.13,
        },
    }

    timestamp = (
        "2026-09-04T10:00:00+00:00"
    )

    market = 0.10

    retail = (
        _retail_prediction(
            champion,
            market,
            timestamp,
        )
    )

    expected = (
        0.13
        + 1.15
        * 0.10
    )

    ok = (
        retail is not None
        and abs(
            retail
            - expected
        )
        < 0.0000001
    )

    return {
        "status":
            (
                "ok"
                if ok
                else "error"
            ),

        "version":
            FORECAST_COMPOSER_VERSION,

        "market":
            market,

        "retail":
            retail,

        "expected":
            expected,
    }
