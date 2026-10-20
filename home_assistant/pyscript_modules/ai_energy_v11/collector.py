from .config import ENTITIES as PUBLIC_ENTITIES
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import math

from .config import (
    RAW_DIR,
    TIMEZONE,
)

from .storage import (
    read_json,
    write_json_atomic,
)


COLLECTOR_VERSION = "11.4.1-quarter-hour-source"

LOCAL_TZ = ZoneInfo(TIMEZONE)


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

        if isinstance(
            value,
            datetime,
        ):
            result = value

        else:
            text = str(
                value
            ).strip()

            if not text:
                return None

            if text.endswith("Z"):
                text = (
                    text[:-1]
                    + "+00:00"
                )

            result = (
                datetime
                .fromisoformat(
                    text
                )
            )

        if result.tzinfo is None:
            result = result.replace(
                tzinfo=LOCAL_TZ
            )

        return result

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


def quarter_start(value):
    dt = parse_datetime(
        value
    )

    if dt is None:
        return None

    local_dt = dt.astimezone(
        LOCAL_TZ
    )

    minute = (
        local_dt.minute
        - (
            local_dt.minute
            % 15
        )
    )

    return local_dt.replace(
        minute=minute,
        second=0,
        microsecond=0,
    )


def _market_choice(
    nordpool_price,
    entsoe_price,
):
    nordpool = safe_float(
        nordpool_price
    )

    entsoe = safe_float(
        entsoe_price
    )

    if (
        nordpool is not None
        and entsoe is not None
    ):
        difference = abs(
            nordpool
            - entsoe
        )

        difference_cent = (
            difference
            * 100
        )

        quality = 100
        agreement = "strong"
        learning_allowed = True

        if difference > 0.0001:
            quality = 90
            agreement = (
                "small_difference"
            )

        if difference > 0.001:
            quality = 70
            agreement = (
                "source_difference"
            )

        if difference > 0.01:
            quality = 50
            agreement = "mismatch"
            learning_allowed = False

        return {
            "price_eur_kwh":
                nordpool,

            "source":
                "nordpool_verified_by_entsoe",

            "quality":
                quality,

            "agreement":
                agreement,

            "difference_cent_kwh":
                round(
                    difference_cent,
                    5,
                ),

            "learning_allowed":
                learning_allowed,
        }

    if nordpool is not None:
        return {
            "price_eur_kwh":
                nordpool,

            "source":
                "nordpool",

            "quality":
                85,

            "agreement":
                "single_source",

            "difference_cent_kwh":
                None,

            "learning_allowed":
                True,
        }

    if entsoe is not None:
        return {
            "price_eur_kwh":
                entsoe,

            "source":
                "entsoe_fallback",

            "quality":
                75,

            "agreement":
                "single_source",

            "difference_cent_kwh":
                None,

            "learning_allowed":
                True,
        }

    return {
        "price_eur_kwh":
            None,

        "source":
            "missing",

        "quality":
            0,

        "agreement":
            "missing",

        "difference_cent_kwh":
            None,

        "learning_allowed":
            False,
    }


def _collection_quality(
    snapshot
):
    checks = [
        snapshot[
            "price"
        ].get(
            "zonneplan_actual_eur_kwh"
        ),

        snapshot[
            "price"
        ].get(
            "market_price_eur_kwh"
        ),

        snapshot[
            "weather"
        ].get(
            "temperature_c"
        ),

        snapshot[
            "weather"
        ].get(
            "wind_speed_kmh"
        ),

        snapshot[
            "weather"
        ].get(
            "wind_direction_deg"
        ),

        snapshot[
            "weather"
        ].get(
            "cloud_cover_pct"
        ),

        snapshot[
            "pv"
        ].get(
            "actual_w"
        ),

        snapshot[
            "energy"
        ].get(
            "p1_power_w"
        ),
    ]

    available = 0

    for value in checks:
        if value is not None:
            available += 1

    return round(
        (
            available
            / len(checks)
        )
        * 100
    )


def build_live_snapshot(
    payload
):
    if not isinstance(
        payload,
        dict,
    ):
        payload = {}

    captured_at = parse_datetime(
        payload.get(
            "captured_at"
        )
    )

    if captured_at is None:
        captured_at = (
            datetime.now(
                LOCAL_TZ
            )
        )

    slot_start_local = (
        quarter_start(
            captured_at
        )
    )

    slot_start_utc = (
        slot_start_local
        .astimezone(
            timezone.utc
        )
    )

    zonneplan = safe_float(
        payload.get(
            "zonneplan_price"
        )
    )

    nordpool = safe_float(
        payload.get(
            "nordpool_price"
        )
    )

    entsoe = safe_float(
        payload.get(
            "entsoe_price"
        )
    )

    market = _market_choice(
        nordpool,
        entsoe,
    )

    market_price = (
        market.get(
            "price_eur_kwh"
        )
    )

    retail_margin = None

    if (
        zonneplan is not None
        and market_price is not None
    ):
        retail_margin = round(
            zonneplan
            - market_price,
            7,
        )

    snapshot = {
        "schema_version":
            1,

        "collector_version":
            COLLECTOR_VERSION,

        "captured_at":
            captured_at.isoformat(),

        "captured_at_utc":
            iso_utc(
                captured_at
            ),

        "slot_start_local":
            slot_start_local
            .isoformat(),

        "slot_start_utc":
            iso_utc(
                slot_start_utc
            ),

        "delivery_date":
            slot_start_local
            .date()
            .isoformat(),

        "collection_reason":
            payload.get(
                "collection_reason",
                "unknown",
            ),

        "price": {
            "zonneplan_actual_eur_kwh":
                zonneplan,
            "actual_price_resolution": payload.get("actual_price_resolution", "legacy_hourly"),
            "actual_price_source": payload.get("actual_price_source", PUBLIC_ENTITIES['zonneplan_current']),

            "nordpool_eur_kwh":
                nordpool,

            "entsoe_eur_kwh":
                entsoe,

            "market_price_eur_kwh":
                market_price,

            "market_source":
                market.get(
                    "source"
                ),

            "market_quality":
                market.get(
                    "quality"
                ),

            "market_agreement":
                market.get(
                    "agreement"
                ),

            "market_difference_cent_kwh":
                market.get(
                    "difference_cent_kwh"
                ),

            "retail_margin_eur_kwh":
                retail_margin,
        },

        "weather": {
            "temperature_c":
                safe_float(
                    payload.get(
                        "temperature"
                    )
                ),

            "wind_speed_kmh":
                safe_float(
                    payload.get(
                        "wind_speed"
                    )
                ),

            "wind_direction_deg":
                safe_float(
                    payload.get(
                        "wind_direction"
                    )
                ),

            "cloud_cover_pct":
                safe_float(
                    payload.get(
                        "cloud_cover"
                    )
                ),

            "humidity_pct":
                safe_float(
                    payload.get(
                        "humidity"
                    )
                ),

            "pressure_hpa":
                safe_float(
                    payload.get(
                        "pressure"
                    )
                ),
        },

        "pv": {
            "actual_w":
                safe_float(
                    payload.get(
                        "pv_actual"
                    )
                ),
        },

        "energy": {
            "p1_power_w":
                safe_float(
                    payload.get(
                        "p1_power"
                    )
                ),
        },

        "context": {
            "golf_state":
                payload.get(
                    "golf_state"
                ),
        },
    }

    quality = (
        _collection_quality(
            snapshot
        )
    )

    snapshot["quality"] = {
        "collection_quality_pct":
            quality,

        "market_quality_pct":
            market.get(
                "quality"
            ),

        "price_learning_eligible":
            (
                zonneplan is not None
                and market_price
                is not None
                and market.get(
                    "learning_allowed"
                )
                is True
            ),

        "weather_learning_eligible":
            (
                snapshot[
                    "weather"
                ][
                    "temperature_c"
                ]
                is not None
                and snapshot[
                    "weather"
                ][
                    "wind_speed_kmh"
                ]
                is not None
            ),

        "energy_learning_eligible":
            (
                snapshot[
                    "energy"
                ][
                    "p1_power_w"
                ]
                is not None
            ),
    }

    return snapshot


def _day_file(
    delivery_date
):
    year = str(
        delivery_date
    )[0:4]

    folder = (
        RAW_DIR
        / year
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        folder
        / (
            str(
                delivery_date
            )
            + ".json"
        )
    )


def store_live_snapshot(
    payload
):
    snapshot = (
        build_live_snapshot(
            payload
        )
    )

    delivery_date = (
        snapshot[
            "delivery_date"
        ]
    )

    path = _day_file(
        delivery_date
    )

    rows = read_json(
        path,
        default=[],
    )

    if not isinstance(
        rows,
        list,
    ):
        rows = []

    slot_key = snapshot[
        "slot_start_utc"
    ]

    replaced = False

    new_rows = []

    for row in rows:
        if not isinstance(
            row,
            dict,
        ):
            continue

        existing_key = (
            row.get(
                "slot_start_utc"
            )
        )

        if (
            existing_key
            == slot_key
        ):
            if not replaced:
                new_rows.append(
                    snapshot
                )

                replaced = True

            continue

        new_rows.append(
            row
        )

    if not replaced:
        new_rows.append(
            snapshot
        )

    new_rows.sort(
        key=lambda row:
            str(
                row.get(
                    "slot_start_utc",
                    "",
                )
            )
    )

    write_json_atomic(
        path,
        new_rows,
    )

    return {
        "version":
            COLLECTOR_VERSION,

        "status":
            "ok",

        "captured_at":
            snapshot.get(
                "captured_at"
            ),

        "slot_start_local":
            snapshot.get(
                "slot_start_local"
            ),

        "slot_start_utc":
            snapshot.get(
                "slot_start_utc"
            ),

        "delivery_date":
            delivery_date,

        "collection_reason":
            snapshot.get(
                "collection_reason"
            ),

        "replaced_existing":
            replaced,

        "rows_today":
            len(
                new_rows
            ),

        "collection_quality_pct":
            snapshot[
                "quality"
            ].get(
                "collection_quality_pct"
            ),

        "market_quality_pct":
            snapshot[
                "quality"
            ].get(
                "market_quality_pct"
            ),

        "price_learning_eligible":
            snapshot[
                "quality"
            ].get(
                "price_learning_eligible"
            ),

        "weather_learning_eligible":
            snapshot[
                "quality"
            ].get(
                "weather_learning_eligible"
            ),

        "energy_learning_eligible":
            snapshot[
                "quality"
            ].get(
                "energy_learning_eligible"
            ),

        "zonneplan_price_eur_kwh":
            snapshot[
                "price"
            ].get(
                "zonneplan_actual_eur_kwh"
            ),

        "market_price_eur_kwh":
            snapshot[
                "price"
            ].get(
                "market_price_eur_kwh"
            ),

        "market_source":
            snapshot[
                "price"
            ].get(
                "market_source"
            ),

        "retail_margin_eur_kwh":
            snapshot[
                "price"
            ].get(
                "retail_margin_eur_kwh"
            ),

        "pv_actual_w":
            snapshot[
                "pv"
            ].get(
                "actual_w"
            ),

        "p1_power_w":
            snapshot[
                "energy"
            ].get(
                "p1_power_w"
            ),

        "file":
            str(path),
    }


def collector_self_test():
    payload = {
        "captured_at":
            "2026-09-03T14:32:00+02:00",

        "collection_reason":
            "self_test",

        "zonneplan_price":
            0.245,

        "nordpool_price":
            0.138,

        "entsoe_price":
            0.138,

        "temperature":
            20.5,

        "wind_speed":
            12.0,

        "wind_direction":
            240,

        "cloud_cover":
            35,

        "humidity":
            65,

        "pressure":
            1014,

        "pv_actual":
            4200,

        "p1_power":
            -1800,

        "golf_state":
            "idle",
    }

    snapshot = (
        build_live_snapshot(
            payload
        )
    )

    ok = (
        snapshot.get(
            "slot_start_local"
        )
        == "2026-09-03T14:30:00+02:00"
        and snapshot[
            "price"
        ][
            "market_price_eur_kwh"
        ]
        == 0.138
        and snapshot[
            "price"
        ][
            "retail_margin_eur_kwh"
        ]
        == 0.107
        and snapshot[
            "quality"
        ][
            "price_learning_eligible"
        ]
        is True
    )

    return {
        "status":
            "ok"
            if ok
            else "error",

        "version":
            COLLECTOR_VERSION,

        "slot_start_local":
            snapshot.get(
                "slot_start_local"
            ),

        "market_source":
            snapshot[
                "price"
            ].get(
                "market_source"
            ),

        "quality":
            snapshot[
                "quality"
            ].get(
                "collection_quality_pct"
            ),
    }
