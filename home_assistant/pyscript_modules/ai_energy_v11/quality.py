from datetime import datetime
import math


QUALITY_VERSION = "11.1.0-quality"


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

        if math.isnan(number):
            return None

        if math.isinf(number):
            return None

        return number

    except Exception:
        return None


def parse_timestamp(value):
    try:
        if value is None:
            return None

        text = str(value).strip()

        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        return datetime.fromisoformat(text)

    except Exception:
        return None


def get_nested(record, *keys):
    current = record

    for key in keys:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def in_range(value, minimum, maximum):
    number = safe_float(value)

    if number is None:
        return False

    return minimum <= number <= maximum


def assess_legacy_record(record):
    if not isinstance(record, dict):
        return {
            "classification": "QUARANTINE",
            "quality_score": 0,
            "reasons": ["record_not_dict"],
            "price_learning_eligible": False,
            "margin_learning_eligible": False,
            "weather_learning_eligible": False,
            "energy_learning_eligible": False,
        }

    reasons = []

    timestamp = parse_timestamp(
        record.get("timestamp")
    )

    zonneplan = safe_float(
        get_nested(
            record,
            "price",
            "zonneplan_current_eur_kwh",
        )
    )

    entsoe_current = safe_float(
        get_nested(
            record,
            "price",
            "entsoe_current_eur_kwh",
        )
    )

    entsoe_average = safe_float(
        get_nested(
            record,
            "price",
            "entsoe_average_eur_kwh",
        )
    )

    market_price = entsoe_current

    if market_price is None:
        market_price = entsoe_average

    temperature = safe_float(
        get_nested(
            record,
            "weather",
            "temperature_c",
        )
    )

    wind_speed = safe_float(
        get_nested(
            record,
            "weather",
            "wind_speed_kmh",
        )
    )

    wind_direction = safe_float(
        get_nested(
            record,
            "weather",
            "wind_direction_deg",
        )
    )

    cloud_cover = safe_float(
        get_nested(
            record,
            "weather",
            "cloud_cover_pct",
        )
    )

    pressure = safe_float(
        get_nested(
            record,
            "weather",
            "pressure_hpa",
        )
    )

    pv_actual = safe_float(
        get_nested(
            record,
            "pv",
            "actual_w",
        )
    )

    p1_power = safe_float(
        get_nested(
            record,
            "energy",
            "p1_power_w",
        )
    )

    hard_error = False

    if timestamp is None:
        reasons.append("timestamp_missing_or_invalid")
        hard_error = True

    if zonneplan is None:
        reasons.append("zonneplan_missing")

    elif not in_range(zonneplan, -5.0, 10.0):
        reasons.append("zonneplan_out_of_range")
        hard_error = True

    if market_price is None:
        reasons.append("market_missing")

    elif not in_range(market_price, -5.0, 10.0):
        reasons.append("market_out_of_range")
        hard_error = True

    weather_available = 0

    weather_values = [
        temperature,
        wind_speed,
        cloud_cover,
    ]

    for value in weather_values:
        if value is not None:
            weather_available += 1

    if temperature is not None:
        if not in_range(temperature, -50, 60):
            reasons.append("temperature_out_of_range")

    if wind_speed is not None:
        if not in_range(wind_speed, 0, 250):
            reasons.append("wind_speed_out_of_range")

    if wind_direction is not None:
        if not in_range(wind_direction, 0, 360):
            reasons.append("wind_direction_out_of_range")

    if cloud_cover is not None:
        if not in_range(cloud_cover, 0, 100):
            reasons.append("cloud_cover_out_of_range")

    if pressure is not None:
        if not in_range(pressure, 800, 1150):
            reasons.append("pressure_out_of_range")

    if weather_available < 2:
        reasons.append("weather_context_incomplete")

    pv_available = pv_actual is not None
    energy_available = p1_power is not None

    score = 0

    if timestamp is not None:
        score += 20

    if zonneplan is not None:
        score += 25

    if market_price is not None:
        score += 25

    if weather_available >= 2:
        score += 15
    elif weather_available == 1:
        score += 7

    if pv_available:
        score += 7

    if energy_available:
        score += 8

    if hard_error:
        classification = "QUARANTINE"

    elif (
        timestamp is not None
        and zonneplan is not None
        and market_price is not None
        and weather_available >= 2
    ):
        classification = "VALID"

    elif (
        timestamp is not None
        and zonneplan is not None
        and market_price is not None
    ):
        classification = "PARTIAL"

    elif (
        timestamp is not None
        and zonneplan is not None
        and market_price is None
    ):
        classification = "SOURCE_MISSING"

    else:
        classification = "QUARANTINE"

    price_learning_eligible = (
        not hard_error
        and timestamp is not None
        and zonneplan is not None
        and market_price is not None
    )

    margin_learning_eligible = (
        price_learning_eligible
    )

    weather_learning_eligible = (
        price_learning_eligible
        and weather_available >= 2
    )

    energy_learning_eligible = (
        not hard_error
        and timestamp is not None
        and (
            pv_available
            or energy_available
        )
    )

    return {
        "classification": classification,
        "quality_score": score,
        "reasons": reasons,

        "timestamp":
            timestamp.isoformat()
            if timestamp is not None
            else None,

        "zonneplan_eur_kwh":
            zonneplan,

        "market_eur_kwh":
            market_price,

        "market_source":
            (
                "entsoe_current"
                if entsoe_current is not None
                else (
                    "entsoe_average"
                    if entsoe_average is not None
                    else None
                )
            ),

        "weather_fields_available":
            weather_available,

        "pv_available":
            pv_available,

        "energy_available":
            energy_available,

        "price_learning_eligible":
            price_learning_eligible,

        "margin_learning_eligible":
            margin_learning_eligible,

        "weather_learning_eligible":
            weather_learning_eligible,

        "energy_learning_eligible":
            energy_learning_eligible,
    }
