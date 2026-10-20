from collections import Counter
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import hashlib
import json
import math

from .config import (
    MARKET_DIR,
    NORDPOOL_AREA,
    NORDPOOL_CURRENCY,
    TIMEZONE,
)

from .storage import (
    write_json_atomic,
)


MARKET_VERSION = "11.1.0-nordpool-market"

NORDPOOL_DIR = MARKET_DIR / "nordpool"


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

        text = str(value).strip()

        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        result = datetime.fromisoformat(text)

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


def _looks_like_price_row(row):
    if not isinstance(row, dict):
        return False

    has_time = (
        "start" in row
        or "deliveryStart" in row
        or "start_time" in row
    )

    has_price = (
        "price" in row
        or "entryPerArea" in row
    )

    return has_time and has_price


def _extract_rows(payload, area):
    """
    Ondersteunt meerdere vormen:

    officiële HA action response:
        {
            "NL": [
                {
                    "start": ...,
                    "end": ...,
                    "price": ...
                }
            ]
        }

    maar ook ruwe Nord Pool-data met:
        deliveryStart
        deliveryEnd
        entryPerArea
    """

    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    direct_area = payload.get(area)

    if isinstance(direct_area, list):
        return direct_area

    prices = payload.get("prices")

    if isinstance(prices, list):
        return prices

    data = payload.get("data")

    if isinstance(data, dict):
        area_rows = data.get(area)

        if isinstance(area_rows, list):
            return area_rows

    for value in payload.values():
        if not isinstance(value, list):
            continue

        if len(value) == 0:
            continue

        first = value[0]

        if _looks_like_price_row(first):
            return value

    return []


def _extract_price(row, area):
    price = safe_float(
        row.get("price")
    )

    if price is not None:
        return price

    entry_per_area = row.get(
        "entryPerArea"
    )

    if isinstance(entry_per_area, dict):
        return safe_float(
            entry_per_area.get(area)
        )

    return None


def _normalize_slot(row, area):
    if not isinstance(row, dict):
        return None

    start_value = row.get("start")

    if start_value is None:
        start_value = row.get(
            "deliveryStart"
        )

    if start_value is None:
        start_value = row.get(
            "start_time"
        )

    end_value = row.get("end")

    if end_value is None:
        end_value = row.get(
            "deliveryEnd"
        )

    if end_value is None:
        end_value = row.get(
            "end_time"
        )

    start_dt = parse_datetime(
        start_value
    )

    end_dt = parse_datetime(
        end_value
    )

    price_mwh = _extract_price(
        row,
        area,
    )

    if start_dt is None:
        return None

    if end_dt is None:
        return None

    if price_mwh is None:
        return None

    seconds = (
        end_dt - start_dt
    ).total_seconds()

    if seconds <= 0:
        return None

    interval_minutes = int(
        round(seconds / 60)
    )

    if interval_minutes <= 0:
        return None

    # Zeer ruime validatie.
    # Negatieve prijzen zijn normaal mogelijk.
    if (
        price_mwh < -10000
        or price_mwh > 10000
    ):
        return None

    return {
        "start_utc":
            iso_utc(start_dt),

        "end_utc":
            iso_utc(end_dt),

        "interval_minutes":
            interval_minutes,

        "price_eur_mwh":
            round(price_mwh, 6),

        "price_eur_kwh":
            round(
                price_mwh / 1000,
                7,
            ),

        "area":
            area,

        "currency":
            NORDPOOL_CURRENCY,

        "source":
            "nordpool",
    }


def expected_slots_for_date(
    requested_date
):
    """
    Houdt rekening met zomer-/wintertijd.

    Normaal:
        96 kwartieren

    DST-omschakeling:
        92 of 100 kwartieren
    """

    try:
        local_tz = ZoneInfo(
            TIMEZONE
        )

        if isinstance(
            requested_date,
            str,
        ):
            date_value = (
                datetime.strptime(
                    requested_date,
                    "%Y-%m-%d",
                ).date()
            )

        elif isinstance(
            requested_date,
            datetime,
        ):
            date_value = (
                requested_date.date()
            )

        else:
            date_value = requested_date

        start_local = datetime(
            date_value.year,
            date_value.month,
            date_value.day,
            0,
            0,
            tzinfo=local_tz,
        )

        next_local = (
            start_local
            + timedelta(days=1)
        )

        start_utc = (
            start_local
            .astimezone(timezone.utc)
        )

        next_utc = (
            next_local
            .astimezone(timezone.utc)
        )

        minutes = (
            next_utc - start_utc
        ).total_seconds() / 60

        return int(
            round(minutes / 15)
        )

    except Exception:
        return 96


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


def normalize_nordpool_response(
    response,
    requested_date=None,
    area=None,
):
    if area is None:
        area = NORDPOOL_AREA

    raw_rows = _extract_rows(
        response,
        area,
    )

    normalized = []
    invalid_rows = 0

    for row in raw_rows:
        slot = _normalize_slot(
            row,
            area,
        )

        if slot is None:
            invalid_rows += 1
            continue

        normalized.append(slot)

    # Zelfde starttijd maar één keer bewaren.
    by_start = {}

    for slot in normalized:
        by_start[
            slot["start_utc"]
        ] = slot

    slots = list(
        by_start.values()
    )

    slots.sort(
        key=lambda item:
            item["start_utc"]
    )

    interval_values = []

    prices = []

    for slot in slots:
        interval_values.append(
            slot[
                "interval_minutes"
            ]
        )

        prices.append(
            slot[
                "price_eur_kwh"
            ]
        )

    detected_interval = None

    if interval_values:
        counts = Counter(
            interval_values
        )

        detected_interval = (
            counts.most_common(1)[0][0]
        )

    expected_slots = None

    if requested_date is not None:
        expected_slots = (
            expected_slots_for_date(
                requested_date
            )
        )

    complete_day = False

    if expected_slots is not None:
        complete_day = (
            len(slots)
            == expected_slots
        )

    min_price = None
    max_price = None
    avg_price = None

    if prices:
        min_price = round(
            min(prices),
            7,
        )

        max_price = round(
            max(prices),
            7,
        )

        avg_price = round(
            sum(prices)
            / len(prices),
            7,
        )

    status = "ok"

    if len(slots) == 0:
        status = "no_data"

    elif invalid_rows > 0:
        status = "partial"

    elif (
        expected_slots is not None
        and not complete_day
    ):
        status = "incomplete"

    return {
        "version":
            MARKET_VERSION,

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "requested_date":
            str(requested_date)
            if requested_date is not None
            else None,

        "area":
            area,

        "currency":
            NORDPOOL_CURRENCY,

        "source":
            "nordpool",

        "status":
            status,

        "raw_rows":
            len(raw_rows),

        "valid_slots":
            len(slots),

        "invalid_rows":
            invalid_rows,

        "expected_slots":
            expected_slots,

        "complete_day":
            complete_day,

        "detected_interval_minutes":
            detected_interval,

        "min_price_eur_kwh":
            min_price,

        "max_price_eur_kwh":
            max_price,

        "avg_price_eur_kwh":
            avg_price,

        "payload_hash":
            _payload_hash(slots),

        "slots":
            slots,
    }


def nordpool_day_file(
    requested_date
):
    NORDPOOL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    date_text = str(
        requested_date
    )

    year = date_text[0:4]

    folder = (
        NORDPOOL_DIR
        / year
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        folder
        / (
            date_text
            + ".json"
        )
    )


def store_nordpool_day(
    response,
    requested_date,
    area=None,
):
    result = (
        normalize_nordpool_response(
            response=response,
            requested_date=requested_date,
            area=area,
        )
    )

    path = nordpool_day_file(
        requested_date
    )

    write_json_atomic(
        path,
        result,
    )

    summary = dict(result)

    # Geen 96 slots terugsturen naar HA
    # als we alleen statusinformatie nodig hebben.
    summary.pop(
        "slots",
        None,
    )

    summary["file"] = str(
        path
    )

    return summary


def market_self_test():
    """
    Volledig native test zonder Home Assistant.

    Bewijst:
    - service-response parsing
    - negatieve prijs
    - EUR/MWh -> EUR/kWh
    - 15-minuten interval
    - opslag
    """

    test_date = "2026-09-03"

    response = {
        "NL": [
            {
                "start":
                    "2026-09-02T22:00:00+00:00",

                "end":
                    "2026-09-02T22:15:00+00:00",

                "price":
                    42.64,
            },
            {
                "start":
                    "2026-09-02T22:15:00+00:00",

                "end":
                    "2026-09-02T22:30:00+00:00",

                "price":
                    -5.50,
            },
        ]
    }

    result = (
        normalize_nordpool_response(
            response=response,
            requested_date=test_date,
            area="NL",
        )
    )

    return {
        "status":
            "ok"
            if (
                result[
                    "valid_slots"
                ] == 2
                and result[
                    "detected_interval_minutes"
                ] == 15
                and result[
                    "slots"
                ][0][
                    "price_eur_kwh"
                ] == 0.04264
                and result[
                    "slots"
                ][1][
                    "price_eur_kwh"
                ] == -0.0055
            )
            else "error",

        "version":
            MARKET_VERSION,

        "valid_slots":
            result[
                "valid_slots"
            ],

        "interval_minutes":
            result[
                "detected_interval_minutes"
            ],

        "first_price":
            result[
                "slots"
            ][0][
                "price_eur_kwh"
            ],

        "second_price":
            result[
                "slots"
            ][1][
                "price_eur_kwh"
            ],

        "expected_slots":
            result[
                "expected_slots"
            ],
    }
