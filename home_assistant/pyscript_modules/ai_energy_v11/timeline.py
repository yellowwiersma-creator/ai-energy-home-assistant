from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import math

from .config import (
    LEGACY_NORMALIZED_DIR,
    MARKET_DIR,
    TIMEZONE,
)

from .storage import (
    read_json,
    write_json_atomic,
    legacy_month_files,
)


TIMELINE_VERSION = "11.3.0-unified-history"

LOCAL_TZ = ZoneInfo(TIMEZONE)

UNIFIED_DIR = (
    LEGACY_NORMALIZED_DIR
    / "unified"
)

SUMMARY_FILE = (
    LEGACY_NORMALIZED_DIR
    / "unified_timeline_summary.json"
)

NORDPOOL_DIR = (
    MARKET_DIR
    / "nordpool"
)

CONSENSUS_DIR = (
    MARKET_DIR
    / "consensus"
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
            result = (
                result.replace(
                    tzinfo=LOCAL_TZ
                )
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


def quarter_start(
    value
):
    dt = parse_datetime(
        value
    )

    if dt is None:
        return None

    utc_dt = dt.astimezone(
        timezone.utc
    )

    minute = (
        utc_dt.minute
        - (
            utc_dt.minute
            % 15
        )
    )

    return utc_dt.replace(
        minute=minute,
        second=0,
        microsecond=0,
    )


def get_nested(
    payload,
    *keys,
):
    current = payload

    for key in keys:
        if not isinstance(
            current,
            dict,
        ):
            return None

        current = current.get(
            key
        )

    return current


def _record_score(
    record
):
    """
    Bij meerdere legacy records binnen
    hetzelfde kwartier bewaren we het
    meest complete meetrecord.
    """

    checks = [
        get_nested(
            record,
            "price",
            "zonneplan_current_eur_kwh",
        ),

        get_nested(
            record,
            "price",
            "entsoe_current_eur_kwh",
        ),

        get_nested(
            record,
            "weather",
            "temperature_c",
        ),

        get_nested(
            record,
            "weather",
            "wind_speed_kmh",
        ),

        get_nested(
            record,
            "weather",
            "wind_direction_deg",
        ),

        get_nested(
            record,
            "weather",
            "cloud_cover_pct",
        ),

        get_nested(
            record,
            "pv",
            "actual_w",
        ),

        get_nested(
            record,
            "pv",
            "solcast_now_w",
        ),

        get_nested(
            record,
            "energy",
            "p1_power_w",
        ),

        get_nested(
            record,
            "energy",
            "p1_import_total_kwh",
        ),

        get_nested(
            record,
            "energy",
            "p1_export_total_kwh",
        ),
    ]

    score = 0

    for value in checks:
        if value is not None:
            score += 1

    return score


def _day_path(
    base_dir,
    delivery_date,
):
    text = str(
        delivery_date
    )

    return (
        Path(base_dir)
        / text[0:4]
        / (
            text
            + ".json"
        )
    )


def _slot_start(
    slot
):
    if not isinstance(
        slot,
        dict,
    ):
        return None

    for key in (
        "start_utc",
        "start",
        "deliveryStart",
    ):
        value = slot.get(
            key
        )

        if value is not None:
            dt = parse_datetime(
                value
            )

            if dt is not None:
                return iso_utc(
                    dt
                )

    return None


def _build_lookup(
    slots
):
    lookup = {}

    if not isinstance(
        slots,
        list,
    ):
        return lookup

    for slot in slots:
        if not isinstance(
            slot,
            dict,
        ):
            continue

        start = _slot_start(
            slot
        )

        if start is None:
            continue

        lookup[start] = slot

    return lookup


def _load_market_day(
    delivery_date,
    cache,
):
    if delivery_date in cache:
        return cache[
            delivery_date
        ]

    consensus_path = (
        _day_path(
            CONSENSUS_DIR,
            delivery_date,
        )
    )

    nordpool_path = (
        _day_path(
            NORDPOOL_DIR,
            delivery_date,
        )
    )

    consensus = read_json(
        consensus_path,
        default={},
    )

    nordpool = read_json(
        nordpool_path,
        default={},
    )

    consensus_lookup = {}

    nordpool_lookup = {}

    if isinstance(
        consensus,
        dict,
    ):
        consensus_lookup = (
            _build_lookup(
                consensus.get(
                    "slots",
                    [],
                )
            )
        )

    if isinstance(
        nordpool,
        dict,
    ):
        nordpool_lookup = (
            _build_lookup(
                nordpool.get(
                    "slots",
                    [],
                )
            )
        )

    result = {
        "consensus":
            consensus_lookup,

        "nordpool":
            nordpool_lookup,

        "nordpool_complete":
            (
                isinstance(
                    nordpool,
                    dict,
                )
                and nordpool.get(
                    "complete_day"
                )
                is True
            ),
    }

    cache[
        delivery_date
    ] = result

    return result


def _market_for_slot(
    slot_start,
    delivery_date,
    legacy_record,
    cache,
):
    start_key = iso_utc(
        slot_start
    )

    market_day = (
        _load_market_day(
            delivery_date,
            cache,
        )
    )

    consensus_slot = (
        market_day[
            "consensus"
        ].get(
            start_key
        )
    )

    if isinstance(
        consensus_slot,
        dict,
    ):
        price = safe_float(
            consensus_slot.get(
                "market_price_eur_kwh"
            )
        )

        if price is not None:
            return {
                "price_eur_kwh":
                    price,

                "source":
                    consensus_slot.get(
                        "market_source",
                        "consensus",
                    ),

                "quality":
                    safe_float(
                        consensus_slot.get(
                            "source_quality"
                        )
                    ),

                "learning_allowed":
                    consensus_slot.get(
                        "learning_allowed"
                    )
                    is True,

                "nordpool_price_eur_kwh":
                    safe_float(
                        consensus_slot.get(
                            "nordpool_price_eur_kwh"
                        )
                    ),

                "entsoe_price_eur_kwh":
                    safe_float(
                        consensus_slot.get(
                            "entsoe_price_eur_kwh"
                        )
                    ),

                "agreement":
                    consensus_slot.get(
                        "agreement"
                    ),
            }

    nordpool_slot = (
        market_day[
            "nordpool"
        ].get(
            start_key
        )
    )

    if isinstance(
        nordpool_slot,
        dict,
    ):
        price = safe_float(
            nordpool_slot.get(
                "price_eur_kwh"
            )
        )

        if price is not None:
            quality = 85

            if not market_day.get(
                "nordpool_complete"
            ):
                quality = 70

            return {
                "price_eur_kwh":
                    price,

                "source":
                    "nordpool_historical",

                "quality":
                    quality,

                "learning_allowed":
                    True,

                "nordpool_price_eur_kwh":
                    price,

                "entsoe_price_eur_kwh":
                    None,

                "agreement":
                    "nordpool_only",
            }

    legacy_entsoe_current = (
        safe_float(
            get_nested(
                legacy_record,
                "price",
                "entsoe_current_eur_kwh",
            )
        )
    )

    if (
        legacy_entsoe_current
        is not None
    ):
        return {
            "price_eur_kwh":
                legacy_entsoe_current,

            "source":
                "legacy_entsoe_current_fallback",

            "quality":
                70,

            "learning_allowed":
                True,

            "nordpool_price_eur_kwh":
                None,

            "entsoe_price_eur_kwh":
                legacy_entsoe_current,

            "agreement":
                "legacy_fallback",
        }

    legacy_entsoe_average = (
        safe_float(
            get_nested(
                legacy_record,
                "price",
                "entsoe_average_eur_kwh",
            )
        )
    )

    if (
        legacy_entsoe_average
        is not None
    ):
        return {
            "price_eur_kwh":
                legacy_entsoe_average,

            "source":
                "legacy_entsoe_average_fallback",

            "quality":
                60,

            "learning_allowed":
                True,

            "nordpool_price_eur_kwh":
                None,

            "entsoe_price_eur_kwh":
                legacy_entsoe_average,

            "agreement":
                "legacy_fallback",
        }

    return {
        "price_eur_kwh":
            None,

        "source":
            "missing",

        "quality":
            0,

        "learning_allowed":
            False,

        "nordpool_price_eur_kwh":
            None,

        "entsoe_price_eur_kwh":
            None,

        "agreement":
            "missing",
    }


def _selected_legacy_data(
    record
):
    price = (
        record.get(
            "price",
            {},
        )
        if isinstance(
            record,
            dict,
        )
        else {}
    )

    weather = (
        record.get(
            "weather",
            {},
        )
        if isinstance(
            record,
            dict,
        )
        else {}
    )

    pv = (
        record.get(
            "pv",
            {},
        )
        if isinstance(
            record,
            dict,
        )
        else {}
    )

    energy = (
        record.get(
            "energy",
            {},
        )
        if isinstance(
            record,
            dict,
        )
        else {}
    )

    time_data = (
        record.get(
            "time",
            {},
        )
        if isinstance(
            record,
            dict,
        )
        else {}
    )

    return {
        "time":
            time_data,

        "weather":
            weather,

        "pv":
            pv,

        "energy":
            energy,

        "legacy_price":
            price,
    }


def _build_unified_row(
    record,
    slot_start,
    market,
):
    timestamp = record.get(
        "timestamp"
    )

    source_dt = parse_datetime(
        timestamp
    )

    local_dt = (
        source_dt
        .astimezone(LOCAL_TZ)
    )

    delivery_date = (
        local_dt
        .date()
        .isoformat()
    )

    zonneplan_price = safe_float(
        get_nested(
            record,
            "price",
            "zonneplan_current_eur_kwh",
        )
    )

    market_price = (
        market.get(
            "price_eur_kwh"
        )
    )

    retail_margin = None

    if (
        zonneplan_price
        is not None
        and market_price
        is not None
    ):
        retail_margin = round(
            zonneplan_price
            - market_price,
            7,
        )

    original_market = safe_float(
        get_nested(
            record,
            "price",
            "market_current_eur_kwh",
        )
    )

    original_entsoe_current = (
        safe_float(
            get_nested(
                record,
                "price",
                "entsoe_current_eur_kwh",
            )
        )
    )

    original_entsoe_average = (
        safe_float(
            get_nested(
                record,
                "price",
                "entsoe_average_eur_kwh",
            )
        )
    )

    original_market_missing = (
        original_market is None
        and original_entsoe_current
        is None
        and original_entsoe_average
        is None
    )

    market_recovered = (
        original_market_missing
        and market_price
        is not None
    )

    price_learning_eligible = (
        zonneplan_price
        is not None
        and market_price
        is not None
        and market.get(
            "learning_allowed"
        )
        is True
    )

    weather_learning_eligible = (
        safe_float(
            get_nested(
                record,
                "weather",
                "temperature_c",
            )
        )
        is not None
        and safe_float(
            get_nested(
                record,
                "weather",
                "wind_speed_kmh",
            )
        )
        is not None
    )

    energy_learning_eligible = (
        safe_float(
            get_nested(
                record,
                "energy",
                "p1_power_w",
            )
        )
        is not None
    )

    legacy = (
        _selected_legacy_data(
            record
        )
    )

    return {
        "schema_version":
            1,

        "timeline_version":
            TIMELINE_VERSION,

        "timestamp":
            timestamp,

        "slot_start_utc":
            iso_utc(
                slot_start
            ),

        "delivery_date":
            delivery_date,

        "local_hour":
            local_dt.hour,

        "local_weekday":
            local_dt.weekday(),

        "local_month":
            local_dt.month,

        "zonneplan_actual_eur_kwh":
            zonneplan_price,

        "market_price_eur_kwh":
            market_price,

        "retail_margin_eur_kwh":
            retail_margin,

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

        "nordpool_price_eur_kwh":
            market.get(
                "nordpool_price_eur_kwh"
            ),

        "entsoe_price_eur_kwh":
            market.get(
                "entsoe_price_eur_kwh"
            ),

        "original_market_missing":
            original_market_missing,

        "market_recovered":
            market_recovered,

        "learning": {
            "price":
                price_learning_eligible,

            "margin":
                price_learning_eligible,

            "weather":
                weather_learning_eligible,

            "energy":
                energy_learning_eligible,
        },

        "time":
            legacy.get(
                "time"
            ),

        "weather":
            legacy.get(
                "weather"
            ),

        "pv":
            legacy.get(
                "pv"
            ),

        "energy":
            legacy.get(
                "energy"
            ),

        "legacy_price":
            legacy.get(
                "legacy_price"
            ),
    }


def _month_file(
    year_month
):
    year = year_month[0:4]

    folder = (
        UNIFIED_DIR
        / year
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        folder
        / (
            year_month
            + ".json"
        )
    )


def build_unified_history():
    files = (
        legacy_month_files()
    )

    raw_records = 0
    invalid_records = 0

    slot_candidates = (
        defaultdict(list)
    )

    for path in files:
        payload = read_json(
            path,
            default=[],
        )

        if not isinstance(
            payload,
            list,
        ):
            continue

        for record in payload:
            raw_records += 1

            if not isinstance(
                record,
                dict,
            ):
                invalid_records += 1
                continue

            timestamp = record.get(
                "timestamp"
            )

            slot_start = (
                quarter_start(
                    timestamp
                )
            )

            if slot_start is None:
                invalid_records += 1
                continue

            key = iso_utc(
                slot_start
            )

            slot_candidates[
                key
            ].append(
                record
            )

    selected = []

    duplicates_removed = 0

    for (
        slot_key,
        candidates,
    ) in slot_candidates.items():
        if len(candidates) > 1:
            duplicates_removed += (
                len(candidates)
                - 1
            )

        candidates.sort(
            key=lambda record: (
                _record_score(
                    record
                ),
                str(
                    record.get(
                        "timestamp",
                        "",
                    )
                ),
            ),
            reverse=True,
        )

        selected.append(
            candidates[0]
        )

    selected.sort(
        key=lambda record:
            str(
                record.get(
                    "timestamp",
                    "",
                )
            )
    )

    market_cache = {}

    rows = []

    market_recovered = 0
    market_missing = 0

    market_nordpool = 0
    market_consensus = 0
    market_legacy_fallback = 0

    price_learning = 0
    margin_learning = 0
    weather_learning = 0
    energy_learning = 0

    source_counts = defaultdict(
        int
    )

    for record in selected:
        timestamp = record.get(
            "timestamp"
        )

        dt = parse_datetime(
            timestamp
        )

        if dt is None:
            continue

        slot_start = (
            quarter_start(
                dt
            )
        )

        local_dt = (
            dt
            .astimezone(
                LOCAL_TZ
            )
        )

        delivery_date = (
            local_dt
            .date()
            .isoformat()
        )

        market = (
            _market_for_slot(
                slot_start,
                delivery_date,
                record,
                market_cache,
            )
        )

        row = (
            _build_unified_row(
                record,
                slot_start,
                market,
            )
        )

        rows.append(row)

        source = row.get(
            "market_source",
            "missing",
        )

        source_counts[
            source
        ] += 1

        if row.get(
            "market_recovered"
        ):
            market_recovered += 1

        if row.get(
            "market_price_eur_kwh"
        ) is None:
            market_missing += 1

        if (
            source
            == "nordpool_historical"
        ):
            market_nordpool += 1

        if "verified" in str(
            source
        ):
            market_consensus += 1

        if "legacy_entsoe" in str(
            source
        ):
            market_legacy_fallback += 1

        learning = row.get(
            "learning",
            {},
        )

        if learning.get(
            "price"
        ):
            price_learning += 1

        if learning.get(
            "margin"
        ):
            margin_learning += 1

        if learning.get(
            "weather"
        ):
            weather_learning += 1

        if learning.get(
            "energy"
        ):
            energy_learning += 1

    months = defaultdict(
        list
    )

    for row in rows:
        timestamp = str(
            row.get(
                "timestamp",
                ""
            )
        )

        if len(timestamp) < 7:
            continue

        year_month = (
            timestamp[0:7]
        )

        months[
            year_month
        ].append(row)

    output_files = {}

    for (
        year_month,
        month_rows,
    ) in sorted(
        months.items()
    ):
        path = (
            _month_file(
                year_month
            )
        )

        write_json_atomic(
            path,
            month_rows,
        )

        output_files[
            year_month
        ] = str(path)

    summary = {
        "version":
            TIMELINE_VERSION,

        "status":
            "ok",

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "legacy_files":
            len(files),

        "raw_records":
            raw_records,

        "invalid_records":
            invalid_records,

        "unique_quarter_slots":
            len(selected),

        "duplicates_removed":
            duplicates_removed,

        "unified_rows":
            len(rows),

        "market_recovered":
            market_recovered,

        "market_still_missing":
            market_missing,

        "market_nordpool_rows":
            market_nordpool,

        "market_consensus_rows":
            market_consensus,

        "market_legacy_fallback_rows":
            market_legacy_fallback,

        "price_learning_eligible":
            price_learning,

        "margin_learning_eligible":
            margin_learning,

        "weather_learning_eligible":
            weather_learning,

        "energy_learning_eligible":
            energy_learning,

        "market_sources":
            dict(
                sorted(
                    source_counts.items()
                )
            ),

        "months":
            {
                key:
                    len(value)

                for (
                    key,
                    value,
                ) in sorted(
                    months.items()
                )
            },

        "files":
            output_files,
    }

    write_json_atomic(
        SUMMARY_FILE,
        summary,
    )

    summary[
        "summary_file"
    ] = str(
        SUMMARY_FILE
    )

    return summary
