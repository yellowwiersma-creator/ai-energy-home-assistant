from .config import ROOT_DIR as CONFIG_ROOT_DIR
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import math

from .config import TIMEZONE

from .storage import (
    read_json,
    write_json_atomic,
)

from .market_forecaster import (
    MARKET_FORECASTER_VERSION,
    FORECAST_FILE,
    build_market_96h_forecast,
)


FORECAST_LEDGER_VERSION = "11.5.1a-known-market-fix"

LOCAL_TZ = ZoneInfo(TIMEZONE)

ROOT_DIR = CONFIG_ROOT_DIR

DATA_DIR = (
    ROOT_DIR
    / "data"
)

FORECAST_INPUT_DIR = (
    DATA_DIR
    / "forecast_inputs"
)

LEDGER_ARCHIVE_DIR = (
    FORECAST_INPUT_DIR
    / "archive"
)

LEDGER_LATEST_FILE = (
    FORECAST_INPUT_DIR
    / "latest.json"
)

NORDPOOL_DIR = (
    DATA_DIR
    / "market"
    / "nordpool"
)

HORIZON_HOURS = 96


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


def parse_datetime(
    value,
    assume_local=False,
):
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
            if assume_local:
                dt = dt.replace(
                    tzinfo=LOCAL_TZ
                )
            else:
                dt = dt.replace(
                    tzinfo=timezone.utc
                )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:
        return None


def _first_value(
    item,
    keys,
):
    if not isinstance(item, dict):
        return None

    for key in keys:
        if key not in item:
            continue

        value = item.get(key)

        if value is not None:
            return value

    return None


def _extract_forecast_list(
    payload,
):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    forecast = payload.get(
        "forecast"
    )

    if isinstance(forecast, list):
        return forecast

    for value in payload.values():
        if not isinstance(
            value,
            dict,
        ):
            continue

        nested = value.get(
            "forecast"
        )

        if isinstance(nested, list):
            return nested

    return []


def normalize_weather_forecast(
    payload,
):
    raw_items = (
        _extract_forecast_list(
            payload
        )
    )

    result = []

    for item in raw_items:
        if not isinstance(
            item,
            dict,
        ):
            continue

        timestamp = _first_value(
            item,
            (
                "datetime",
                "timestamp_utc",
                "timestamp",
                "time",
                "start_utc",
                "start",
            ),
        )

        dt = parse_datetime(
            timestamp,
            assume_local=True,
        )

        if dt is None:
            continue

        temperature = safe_float(
            _first_value(
                item,
                (
                    "temperature",
                    "temp",
                ),
            )
        )

        temperature_low = safe_float(
            _first_value(
                item,
                (
                    "templow",
                    "temperature_low",
                    "low_temperature",
                ),
            )
        )

        wind_speed = safe_float(
            _first_value(
                item,
                (
                    "wind_speed",
                    "windspeed",
                ),
            )
        )

        wind_gust = safe_float(
            _first_value(
                item,
                (
                    "wind_gust_speed",
                    "wind_gust",
                    "windgust",
                ),
            )
        )

        wind_bearing = safe_float(
            _first_value(
                item,
                (
                    "wind_bearing",
                    "wind_direction",
                    "winddirection",
                ),
            )
        )

        cloud_coverage = safe_float(
            _first_value(
                item,
                (
                    "cloud_coverage",
                    "cloudiness",
                    "cloud_cover",
                    "clouds",
                ),
            )
        )

        precipitation_probability = safe_float(
            _first_value(
                item,
                (
                    "precipitation_probability",
                    "precipitation_probability_pct",
                    "pop",
                ),
            )
        )

        precipitation = safe_float(
            _first_value(
                item,
                (
                    "precipitation",
                    "rain",
                ),
            )
        )

        humidity = safe_float(
            _first_value(
                item,
                (
                    "humidity",
                ),
            )
        )

        pressure = safe_float(
            _first_value(
                item,
                (
                    "pressure",
                ),
            )
        )

        condition = _first_value(
            item,
            (
                "condition",
                "weather",
            ),
        )

        result.append(
            {
                "timestamp_utc":
                    dt.isoformat(),

                "timestamp_local":
                    dt.astimezone(
                        LOCAL_TZ
                    ).isoformat(),

                "temperature":
                    temperature,

                "temperature_low":
                    temperature_low,

                "wind_speed":
                    wind_speed,

                "wind_gust":
                    wind_gust,

                "wind_bearing":
                    wind_bearing,

                "cloud_coverage":
                    cloud_coverage,

                "precipitation_probability":
                    precipitation_probability,

                "precipitation":
                    precipitation,

                "humidity":
                    humidity,

                "pressure":
                    pressure,

                "condition":
                    condition,
            }
        )

    result.sort(
        key=lambda row:
            row["timestamp_utc"]
    )

    return result


def _extract_market_items(
    payload,
):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in (
        "slots",
        "prices",
        "data",
        "values",
        "forecast",
    ):
        value = payload.get(key)

        if isinstance(value, list):
            return value

    return []


def _market_item_price(
    item,
):
    explicit = _first_value(
        item,
        (
            "price_eur_kwh",
            "market_price_eur_kwh",
            "value_eur_kwh",
        ),
    )

    price = safe_float(
        explicit
    )

    if price is not None:
        return price

    generic = safe_float(
        _first_value(
            item,
            (
                "price",
                "value",
            ),
        )
    )

    if generic is None:
        return None

    if abs(generic) > 2:
        return (
            generic
            / 1000.0
        )

    return generic


def load_known_nordpool_slots(
    issue_time,
    horizon_hours=HORIZON_HOURS,
):
    issue_dt = parse_datetime(
        issue_time
    )

    if issue_dt is None:
        return []

    now_utc = datetime.now(
        timezone.utc
    )

    age_minutes = abs(
        (
            now_utc
            - issue_dt
        ).total_seconds()
        / 60
    )

    # Alleen echte live captures mogen bestaande
    # Nord Pool-files als "known at issue" gebruiken.
    #
    # Bij historische/test issue-times weten we niet
    # betrouwbaar wanneer een opgeslagen backfill-file
    # destijds werkelijk beschikbaar was.
    if age_minutes > 15:
        return []

    end_dt = (
        issue_dt
        + timedelta(
            hours=horizon_hours
        )
    )

    result = {}

    if not NORDPOOL_DIR.exists():
        return []

    for path in sorted(
        NORDPOOL_DIR.rglob(
            "*.json"
        )
    ):
        payload = read_json(
            path,
            default={},
        )

        items = (
            _extract_market_items(
                payload
            )
        )

        for item in items:
            if not isinstance(
                item,
                dict,
            ):
                continue

            timestamp = _first_value(
                item,
                (
                    "start_utc",
                    "timestamp_utc",
                    "delivery_start_utc",
                    "start",
                    "start_time",
                    "timestamp",
                    "datetime",
                    "time",
                    "delivery_start",
                ),
            )

            dt = parse_datetime(
                timestamp,
                assume_local=True,
            )

            if dt is None:
                continue

            if dt <= issue_dt:
                continue

            if dt > end_dt:
                continue

            price = (
                _market_item_price(
                    item
                )
            )

            if price is None:
                continue

            key = dt.isoformat()

            result[key] = {
                "timestamp_utc":
                    key,

                "timestamp_local":
                    dt.astimezone(
                        LOCAL_TZ
                    ).isoformat(),

                "market_price_eur_kwh":
                    round(
                        price,
                        8,
                    ),

                "market_price_cent_kwh":
                    round(
                        price * 100,
                        5,
                    ),

                "source":
                    "nordpool_known_at_issue",

                "source_file":
                    str(path),
            }

    rows = list(
        result.values()
    )

    rows.sort(
        key=lambda row:
            row["timestamp_utc"]
    )

    return rows


def _weather_horizon_hours(
    issue_dt,
    rows,
):
    maximum = None

    for row in rows:
        dt = parse_datetime(
            row.get(
                "timestamp_utc"
            )
        )

        if dt is None:
            continue

        hours = (
            (
                dt
                - issue_dt
            ).total_seconds()
            / 3600
        )

        if hours < 0:
            continue

        if (
            maximum is None
            or hours > maximum
        ):
            maximum = hours

    if maximum is None:
        return 0.0

    return round(
        maximum,
        2,
    )


def _snapshot_path(
    issue_dt,
):
    local_dt = (
        issue_dt
        .astimezone(
            LOCAL_TZ
        )
    )

    directory = (
        LEDGER_ARCHIVE_DIR
        / local_dt.strftime("%Y")
        / local_dt.strftime("%m")
        / local_dt.strftime("%d")
    )

    filename = (
        local_dt.strftime(
            "%H%M%S"
        )
        + ".json"
    )

    return (
        directory
        / filename
    )


def capture_forecast_inputs(
    payload=None,
):
    if payload is None:
        payload = {}

    if not isinstance(
        payload,
        dict,
    ):
        payload = {}

    now_utc = datetime.now(
        timezone.utc
    )

    requested_issue = payload.get(
        "issue_time"
    )

    issue_dt = parse_datetime(
        requested_issue
    )

    if issue_dt is None:
        issue_dt = now_utc

    replay_age_minutes = abs(
        (
            now_utc
            - issue_dt
        ).total_seconds()
        / 60
    )

    capture_mode = "live"

    if replay_age_minutes > 15:
        capture_mode = (
            "historical_or_test"
        )

    market_result = (
        build_market_96h_forecast(
            issue_dt.isoformat()
        )
    )

    market_payload = read_json(
        FORECAST_FILE,
        default={},
    )

    market_forecast = []

    if isinstance(
        market_payload,
        dict,
    ):
        candidate = (
            market_payload.get(
                "forecast"
            )
        )

        if isinstance(
            candidate,
            list,
        ):
            market_forecast = candidate

    known_market = (
        load_known_nordpool_slots(
            issue_dt,
            HORIZON_HOURS,
        )
    )

    hourly_weather = (
        normalize_weather_forecast(
            payload.get(
                "weather_hourly_response"
            )
        )
    )

    daily_weather = (
        normalize_weather_forecast(
            payload.get(
                "weather_daily_response"
            )
        )
    )

    weather_entity = payload.get(
        "weather_entity"
    )

    weather_state = payload.get(
        "weather_state"
    )

    weather_attributes = payload.get(
        "weather_attributes"
    )

    if not isinstance(
        weather_attributes,
        dict,
    ):
        weather_attributes = {}

    hourly_error = payload.get(
        "weather_hourly_error"
    )

    daily_error = payload.get(
        "weather_daily_error"
    )

    market_model = None

    if isinstance(
        market_payload,
        dict,
    ):
        market_model = (
            market_payload.get(
                "model"
            )
        )

    snapshot = {
        "version":
            FORECAST_LEDGER_VERSION,

        "created_utc":
            now_utc.isoformat(),

        "reason":
            payload.get(
                "reason"
            ),

        "capture_mode":
            capture_mode,

        "issue_time_utc":
            issue_dt.isoformat(),

        "issue_time_local":
            issue_dt.astimezone(
                LOCAL_TZ
            ).isoformat(),

        "horizon_hours":
            HORIZON_HOURS,

        "market": {
            "forecaster_version":
                MARKET_FORECASTER_VERSION,

            "forecast_status":
                market_result.get(
                    "status"
                ),

            "baseline_model":
                market_model,

            "baseline_slots":
                len(
                    market_forecast
                ),

            "known_nordpool_slots":
                len(
                    known_market
                ),

            "baseline_forecast":
                market_forecast,

            "known_market":
                known_market,
        },

        "weather": {
            "entity":
                weather_entity,

            "current_state":
                weather_state,

            "current_attributes":
                weather_attributes,

            "hourly_slots":
                len(
                    hourly_weather
                ),

            "daily_slots":
                len(
                    daily_weather
                ),

            "hourly_horizon_hours":
                _weather_horizon_hours(
                    issue_dt,
                    hourly_weather,
                ),

            "daily_horizon_hours":
                _weather_horizon_hours(
                    issue_dt,
                    daily_weather,
                ),

            "hourly_error":
                hourly_error,

            "daily_error":
                daily_error,

            "hourly_forecast":
                hourly_weather,

            "daily_forecast":
                daily_weather,
        },

        "learning_rules": {
            "historical_actual_weather_as_future_feature":
                False,

            "forecast_weather_may_be_used":
                True,

            "known_market_only_if_available_at_issue":
                True,

            "historical_known_market_reconstruction":
                False,

            "snapshot_is_immutable_training_input":
                True,
        },
    }

    archive_file = (
        _snapshot_path(
            issue_dt
        )
    )

    archive_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    FORECAST_INPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json_atomic(
        archive_file,
        snapshot,
    )

    write_json_atomic(
        LEDGER_LATEST_FILE,
        snapshot,
    )

    return {
        "version":
            FORECAST_LEDGER_VERSION,

        "status":
            "ok",

        "capture_mode":
            capture_mode,

        "issue_time_local":
            snapshot[
                "issue_time_local"
            ],

        "market_model":
            market_model,

        "market_baseline_slots":
            len(
                market_forecast
            ),

        "known_market_slots":
            len(
                known_market
            ),

        "weather_entity":
            weather_entity,

        "weather_hourly_slots":
            len(
                hourly_weather
            ),

        "weather_hourly_horizon_hours":
            snapshot[
                "weather"
            ][
                "hourly_horizon_hours"
            ],

        "weather_daily_slots":
            len(
                daily_weather
            ),

        "weather_daily_horizon_hours":
            snapshot[
                "weather"
            ][
                "daily_horizon_hours"
            ],

        "weather_hourly_error":
            hourly_error,

        "weather_daily_error":
            daily_error,

        "archive_file":
            str(
                archive_file
            ),

        "latest_file":
            str(
                LEDGER_LATEST_FILE
            ),
    }


def forecast_ledger_self_test():
    weather_payload = {
        "forecast": [
            {
                "datetime":
                    "2026-09-04T12:00:00+02:00",

                "temperature":
                    19.5,

                "wind_speed":
                    18.0,

                "wind_bearing":
                    245,

                "cloud_coverage":
                    70,

                "precipitation_probability":
                    20,

                "condition":
                    "cloudy",
            },
            {
                "datetime":
                    "2026-09-04T13:00:00+02:00",

                "temperature":
                    20.1,

                "wind_speed":
                    19.5,

                "wind_bearing":
                    250,

                "cloud_coverage":
                    65,

                "precipitation_probability":
                    15,

                "condition":
                    "partlycloudy",
            },
        ]
    }

    normalized = (
        normalize_weather_forecast(
            weather_payload
        )
    )

    market_test_item = {
        "start_utc":
            "2026-09-04T10:00:00+00:00",

        "price_eur_mwh":
            123.45,

        "price_eur_kwh":
            0.12345,
    }

    market_time = parse_datetime(
        _first_value(
            market_test_item,
            (
                "start_utc",
                "timestamp_utc",
                "start",
            ),
        )
    )

    market_price = (
        _market_item_price(
            market_test_item
        )
    )

    weather_ok = (
        len(normalized) == 2
        and normalized[0].get(
            "temperature"
        ) == 19.5
        and normalized[0].get(
            "wind_speed"
        ) == 18.0
        and normalized[0].get(
            "cloud_coverage"
        ) == 70.0
    )

    market_ok = (
        market_time is not None
        and market_price == 0.12345
    )

    ok = (
        weather_ok
        and market_ok
    )

    return {
        "status":
            (
                "ok"
                if ok
                else "error"
            ),

        "version":
            FORECAST_LEDGER_VERSION,

        "weather_rows":
            len(
                normalized
            ),

        "market_start_utc_parsed":
            (
                market_time.isoformat()
                if market_time
                is not None
                else None
            ),

        "market_price_eur_kwh":
            market_price,

        "first":
            (
                normalized[0]
                if normalized
                else None
            ),
    }
