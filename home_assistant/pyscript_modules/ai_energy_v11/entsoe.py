from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import math

from .config import (
    MARKET_DIR,
    TIMEZONE,
)

from .storage import (
    write_json_atomic,
)

from .market import (
    expected_slots_for_date,
)


ENTSOE_VERSION = "11.1.0-entsoe-market"

LOCAL_TZ = ZoneInfo(TIMEZONE)

ENTSOE_DIR = MARKET_DIR / "entsoe"


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


def parse_datetime(value):
    try:
        if value is None:
            return None

        if isinstance(value, datetime):
            result = value

        else:
            text = str(value).strip()

            if not text:
                return None

            if text.endswith("Z"):
                text = (
                    text[:-1]
                    + "+00:00"
                )

            result = datetime.fromisoformat(
                text
            )

        if result.tzinfo is None:
            result = result.replace(
                tzinfo=timezone.utc
            )

        return result.astimezone(
            timezone.utc
        )

    except Exception:
        return None


def iso_utc(value):
    if value is None:
        return None

    return (
        value
        .astimezone(timezone.utc)
        .isoformat()
    )


def normalize_unit_text(value):
    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "")
    )


def price_to_eur_kwh(
    value,
    unit_of_measurement=None,
):
    """
    Zet ENTSO-E prijs om naar EUR/kWh.

    We bewaren ook hoe de conversie
    bepaald is.

    Veiligheidslaag:
    waarden > 5 EUR/kWh zijn voor deze
    markt vrijwel zeker EUR/MWh.
    """

    number = safe_float(value)

    if number is None:
        return None, "invalid"

    unit = normalize_unit_text(
        unit_of_measurement
    )

    if "mwh" in unit:
        return (
            round(
                number / 1000,
                7,
            ),
            "unit_eur_mwh",
        )

    if "kwh" in unit:
        if abs(number) > 5:
            return (
                round(
                    number / 1000,
                    7,
                ),
                "unit_conflict_assumed_mwh",
            )

        return (
            round(number, 7),
            "unit_eur_kwh",
        )

    if abs(number) > 5:
        return (
            round(
                number / 1000,
                7,
            ),
            "heuristic_eur_mwh",
        )

    return (
        round(number, 7),
        "heuristic_eur_kwh",
    )


def _extract_start(item):
    if not isinstance(item, dict):
        return None

    for key in (
        "time",
        "datetime",
        "start",
        "start_time",
        "deliveryStart",
    ):
        value = item.get(key)

        if value is not None:
            return value

    return None


def _extract_price(item):
    if not isinstance(item, dict):
        return None

    for key in (
        "price",
        "value",
        "market_price",
    ):
        value = item.get(key)

        if value is not None:
            return value

    return None


def _detect_interval_minutes(
    raw_items
):
    differences = []

    for index in range(
        len(raw_items) - 1
    ):
        current = raw_items[index]
        following = raw_items[
            index + 1
        ]

        seconds = (
            following["start_dt"]
            - current["start_dt"]
        ).total_seconds()

        if seconds <= 0:
            continue

        minutes = int(
            round(seconds / 60)
        )

        if minutes in (
            5,
            10,
            15,
            30,
            60,
        ):
            differences.append(
                minutes
            )

    if not differences:
        return None

    counts = Counter(
        differences
    )

    return counts.most_common(
        1
    )[0][0]


def _source_resolution(
    interval_minutes
):
    if interval_minutes == 15:
        return "quarter_hour"

    if interval_minutes == 30:
        return "half_hour"

    if interval_minutes == 60:
        return "hour"

    if interval_minutes is None:
        return "unknown"

    return (
        str(interval_minutes)
        + "_minute"
    )


def normalize_entsoe_prices(
    prices,
    unit_of_measurement=None,
):
    if not isinstance(prices, list):
        return {
            "status": "no_prices_attribute",

            "total_items": 0,

            "valid_slots": 0,

            "invalid_items": 0,

            "detected_interval_minutes":
                None,

            "source_resolution":
                "unknown",

            "conversion_modes": {},

            "slots": [],
        }

    raw_items = []

    invalid_items = 0

    conversion_modes = Counter()

    for item in prices:
        if not isinstance(item, dict):
            invalid_items += 1
            continue

        start_value = _extract_start(
            item
        )

        raw_price = _extract_price(
            item
        )

        start_dt = parse_datetime(
            start_value
        )

        (
            price_eur_kwh,
            conversion_mode,
        ) = price_to_eur_kwh(
            raw_price,
            unit_of_measurement,
        )

        if (
            start_dt is None
            or price_eur_kwh is None
        ):
            invalid_items += 1
            continue

        if (
            price_eur_kwh < -10
            or price_eur_kwh > 10
        ):
            invalid_items += 1
            continue

        conversion_modes[
            conversion_mode
        ] += 1

        raw_items.append(
            {
                "start_dt":
                    start_dt,

                "price_raw":
                    safe_float(
                        raw_price
                    ),

                "price_eur_kwh":
                    price_eur_kwh,

                "conversion_mode":
                    conversion_mode,
            }
        )

    raw_items.sort(
        key=lambda item:
            item["start_dt"]
    )

    deduplicated = {}

    for item in raw_items:
        key = iso_utc(
            item["start_dt"]
        )

        deduplicated[key] = item

    raw_items = list(
        deduplicated.values()
    )

    raw_items.sort(
        key=lambda item:
            item["start_dt"]
    )

    interval = (
        _detect_interval_minutes(
            raw_items
        )
    )

    slots = []

    for index in range(
        len(raw_items)
    ):
        item = raw_items[index]

        slot_interval = interval

        if index + 1 < len(
            raw_items
        ):
            following = raw_items[
                index + 1
            ]

            difference = int(
                round(
                    (
                        following["start_dt"]
                        - item["start_dt"]
                    ).total_seconds()
                    / 60
                )
            )

            if difference in (
                5,
                10,
                15,
                30,
                60,
            ):
                slot_interval = (
                    difference
                )

        if slot_interval is None:
            slot_interval = 15

        end_dt = (
            item["start_dt"]
            + __import__(
                "datetime"
            ).timedelta(
                minutes=slot_interval
            )
        )

        local_start = (
            item["start_dt"]
            .astimezone(LOCAL_TZ)
        )

        slots.append(
            {
                "start_utc":
                    iso_utc(
                        item["start_dt"]
                    ),

                "end_utc":
                    iso_utc(end_dt),

                "delivery_date":
                    local_start
                    .date()
                    .isoformat(),

                "interval_minutes":
                    slot_interval,

                "source_resolution":
                    _source_resolution(
                        slot_interval
                    ),

                "price_raw":
                    item[
                        "price_raw"
                    ],

                "price_eur_kwh":
                    item[
                        "price_eur_kwh"
                    ],

                "conversion_mode":
                    item[
                        "conversion_mode"
                    ],

                "source":
                    "entsoe",
            }
        )

    status = "ok"

    if len(slots) == 0:
        status = "no_data"

    elif invalid_items > 0:
        status = "partial"

    return {
        "status":
            status,

        "total_items":
            len(prices),

        "valid_slots":
            len(slots),

        "invalid_items":
            invalid_items,

        "detected_interval_minutes":
            interval,

        "source_resolution":
            _source_resolution(
                interval
            ),

        "conversion_modes":
            dict(
                conversion_modes
            ),

        "slots":
            slots,
    }


def _expected_slots(
    delivery_date,
    interval_minutes,
):
    if interval_minutes is None:
        return None

    expected_quarters = (
        expected_slots_for_date(
            delivery_date
        )
    )

    day_minutes = (
        expected_quarters
        * 15
    )

    if (
        day_minutes
        % interval_minutes
        != 0
    ):
        return None

    return int(
        day_minutes
        / interval_minutes
    )


def _payload_hash(slots):
    try:
        text = json.dumps(
            slots,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

    except Exception:
        return None


def entsoe_day_file(
    delivery_date
):
    year = str(
        delivery_date
    )[0:4]

    folder = (
        ENTSOE_DIR
        / year
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        folder
        / (
            str(delivery_date)
            + ".json"
        )
    )


def _build_day_payload(
    delivery_date,
    slots,
    unit_of_measurement,
    conversion_modes,
):
    prices = []

    intervals = []

    for slot in slots:
        price = safe_float(
            slot.get(
                "price_eur_kwh"
            )
        )

        if price is not None:
            prices.append(price)

        interval = slot.get(
            "interval_minutes"
        )

        if isinstance(
            interval,
            int,
        ):
            intervals.append(
                interval
            )

    detected_interval = None

    if intervals:
        counts = Counter(
            intervals
        )

        detected_interval = (
            counts.most_common(
                1
            )[0][0]
        )

    expected = _expected_slots(
        delivery_date,
        detected_interval,
    )

    complete_day = False

    if expected is not None:
        complete_day = (
            len(slots)
            == expected
        )

    return {
        "version":
            ENTSOE_VERSION,

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "delivery_date":
            delivery_date,

        "source":
            "entsoe",

        "source_unit":
            unit_of_measurement,

        "conversion_modes":
            conversion_modes,

        "valid_slots":
            len(slots),

        "expected_slots":
            expected,

        "complete_day":
            complete_day,

        "detected_interval_minutes":
            detected_interval,

        "source_resolution":
            _source_resolution(
                detected_interval
            ),

        "min_price_eur_kwh":
            (
                round(
                    min(prices),
                    7,
                )
                if prices
                else None
            ),

        "max_price_eur_kwh":
            (
                round(
                    max(prices),
                    7,
                )
                if prices
                else None
            ),

        "avg_price_eur_kwh":
            (
                round(
                    sum(prices)
                    / len(prices),
                    7,
                )
                if prices
                else None
            ),

        "payload_hash":
            _payload_hash(slots),

        "slots":
            slots,
    }


def store_entsoe_prices(
    payload
):
    if not isinstance(
        payload,
        dict,
    ):
        payload = {}

    prices = payload.get(
        "prices"
    )

    unit = payload.get(
        "unit_of_measurement"
    )

    normalized = (
        normalize_entsoe_prices(
            prices,
            unit,
        )
    )

    slots = normalized.get(
        "slots"
    )

    if not isinstance(
        slots,
        list,
    ):
        slots = []

    grouped = {}

    for slot in slots:
        delivery_date = slot.get(
            "delivery_date"
        )

        if delivery_date is None:
            continue

        if delivery_date not in grouped:
            grouped[
                delivery_date
            ] = []

        grouped[
            delivery_date
        ].append(slot)

    files = {}

    dates = {}

    for (
        delivery_date,
        day_slots,
    ) in sorted(
        grouped.items()
    ):
        day_slots.sort(
            key=lambda item:
                item.get(
                    "start_utc",
                    "",
                )
        )

        day_payload = (
            _build_day_payload(
                delivery_date,
                day_slots,
                unit,
                normalized.get(
                    "conversion_modes",
                    {},
                ),
            )
        )

        path = entsoe_day_file(
            delivery_date
        )

        write_json_atomic(
            path,
            day_payload,
        )

        files[
            delivery_date
        ] = str(path)

        dates[
            delivery_date
        ] = {
            "slots":
                day_payload.get(
                    "valid_slots"
                ),

            "expected_slots":
                day_payload.get(
                    "expected_slots"
                ),

            "complete_day":
                day_payload.get(
                    "complete_day"
                ),

            "interval_minutes":
                day_payload.get(
                    "detected_interval_minutes"
                ),

            "avg_price_eur_kwh":
                day_payload.get(
                    "avg_price_eur_kwh"
                ),
        }

    return {
        "version":
            ENTSOE_VERSION,

        "status":
            normalized.get(
                "status"
            ),

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source":
            "entsoe",

        "source_unit":
            unit,

        "total_items":
            normalized.get(
                "total_items"
            ),

        "valid_slots":
            normalized.get(
                "valid_slots"
            ),

        "invalid_items":
            normalized.get(
                "invalid_items"
            ),

        "detected_interval_minutes":
            normalized.get(
                "detected_interval_minutes"
            ),

        "source_resolution":
            normalized.get(
                "source_resolution"
            ),

        "conversion_modes":
            normalized.get(
                "conversion_modes"
            ),

        "dates":
            dates,

        "files":
            files,
    }


def entsoe_self_test():
    payload = {
        "unit_of_measurement":
            "€/kWh",

        "prices": [
            {
                "time":
                    "2026-09-03T00:00:00+02:00",

                "price":
                    0.04264,
            },
            {
                "time":
                    "2026-09-03T00:15:00+02:00",

                "price":
                    0.04000,
            },
            {
                "time":
                    "2026-09-03T00:30:00+02:00",

                "price":
                    -0.00550,
            },
        ],
    }

    result = (
        normalize_entsoe_prices(
            payload["prices"],
            payload[
                "unit_of_measurement"
            ],
        )
    )

    ok = (
        result.get(
            "valid_slots"
        ) == 3
        and result.get(
            "detected_interval_minutes"
        ) == 15
        and result[
            "slots"
        ][0][
            "price_eur_kwh"
        ] == 0.04264
        and result[
            "slots"
        ][2][
            "price_eur_kwh"
        ] == -0.0055
    )

    return {
        "status":
            "ok"
            if ok
            else "error",

        "version":
            ENTSOE_VERSION,

        "valid_slots":
            result.get(
                "valid_slots"
            ),

        "interval_minutes":
            result.get(
                "detected_interval_minutes"
            ),

        "source_resolution":
            result.get(
                "source_resolution"
            ),
    }
