from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math

from .config import MARKET_DIR

from .storage import (
    read_json,
    write_json_atomic,
)


CONSENSUS_VERSION = "11.2.0-market-consensus"

CONSENSUS_DIR = (
    MARKET_DIR
    / "consensus"
)

NORDPOOL_DIR = (
    MARKET_DIR
    / "nordpool"
)

ENTSOE_DIR = (
    MARKET_DIR
    / "entsoe"
)


# Dit is geen economische afwijkingsgrens.
# Het is een data-integriteitscontrole.
#
# 0.00001 €/kWh = 0.001 ct/kWh
MATCH_TOLERANCE_EUR_KWH = 0.00001

# 0.0001 €/kWh = 0.01 ct/kWh
WARNING_TOLERANCE_EUR_KWH = 0.0001


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


def _day_file(
    base_dir,
    delivery_date,
):
    date_text = str(
        delivery_date
    )

    year = date_text[0:4]

    return (
        Path(base_dir)
        / year
        / (
            date_text
            + ".json"
        )
    )


def nordpool_day_file(
    delivery_date
):
    return _day_file(
        NORDPOOL_DIR,
        delivery_date,
    )


def entsoe_day_file(
    delivery_date
):
    return _day_file(
        ENTSOE_DIR,
        delivery_date,
    )


def consensus_day_file(
    delivery_date
):
    date_text = str(
        delivery_date
    )

    year = date_text[0:4]

    folder = (
        CONSENSUS_DIR
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


def _slot_start(slot):
    if not isinstance(
        slot,
        dict,
    ):
        return None

    value = slot.get(
        "start_utc"
    )

    if value is None:
        value = slot.get(
            "start"
        )

    if value is None:
        return None

    return str(value)


def _slot_end(slot):
    if not isinstance(
        slot,
        dict,
    ):
        return None

    value = slot.get(
        "end_utc"
    )

    if value is None:
        value = slot.get(
            "end"
        )

    if value is None:
        return None

    return str(value)


def _build_lookup(slots):
    result = {}

    if not isinstance(
        slots,
        list,
    ):
        return result

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

        result[start] = slot

    return result


def _agreement(
    nordpool_price,
    entsoe_price,
):
    if (
        nordpool_price is None
        and entsoe_price is None
    ):
        return {
            "status": "missing",
            "quality": 0,
            "difference_eur_kwh": None,
            "difference_cent_kwh": None,
            "learning_allowed": False,
        }

    if (
        nordpool_price is not None
        and entsoe_price is None
    ):
        return {
            "status": "nordpool_only",
            "quality": 85,
            "difference_eur_kwh": None,
            "difference_cent_kwh": None,
            "learning_allowed": True,
        }

    if (
        nordpool_price is None
        and entsoe_price is not None
    ):
        return {
            "status": "entsoe_only",
            "quality": 75,
            "difference_eur_kwh": None,
            "difference_cent_kwh": None,
            "learning_allowed": True,
        }

    difference = abs(
        nordpool_price
        - entsoe_price
    )

    difference_cent = (
        difference
        * 100
    )

    if (
        difference
        <= MATCH_TOLERANCE_EUR_KWH
    ):
        return {
            "status": "exact",
            "quality": 100,

            "difference_eur_kwh":
                round(
                    difference,
                    7,
                ),

            "difference_cent_kwh":
                round(
                    difference_cent,
                    5,
                ),

            "learning_allowed":
                True,
        }

    if (
        difference
        <= WARNING_TOLERANCE_EUR_KWH
    ):
        return {
            "status": "small_difference",
            "quality": 90,

            "difference_eur_kwh":
                round(
                    difference,
                    7,
                ),

            "difference_cent_kwh":
                round(
                    difference_cent,
                    5,
                ),

            "learning_allowed":
                True,
        }

    return {
        "status": "mismatch",
        "quality": 60,

        "difference_eur_kwh":
            round(
                difference,
                7,
            ),

        "difference_cent_kwh":
            round(
                difference_cent,
                5,
            ),

        "learning_allowed":
            False,
    }


def _payload_hash(slots):
    try:
        text = json.dumps(
            slots,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return hashlib.sha256(
            text.encode(
                "utf-8"
            )
        ).hexdigest()

    except Exception:
        return None


def build_market_consensus(
    delivery_date
):
    date_text = str(
        delivery_date
    )

    nordpool_path = (
        nordpool_day_file(
            date_text
        )
    )

    entsoe_path = (
        entsoe_day_file(
            date_text
        )
    )

    nordpool_payload = read_json(
        nordpool_path,
        default={},
    )

    entsoe_payload = read_json(
        entsoe_path,
        default={},
    )

    nordpool_slots = []

    if isinstance(
        nordpool_payload,
        dict,
    ):
        value = (
            nordpool_payload
            .get("slots")
        )

        if isinstance(
            value,
            list,
        ):
            nordpool_slots = value

    entsoe_slots = []

    if isinstance(
        entsoe_payload,
        dict,
    ):
        value = (
            entsoe_payload
            .get("slots")
        )

        if isinstance(
            value,
            list,
        ):
            entsoe_slots = value

    nordpool_lookup = (
        _build_lookup(
            nordpool_slots
        )
    )

    entsoe_lookup = (
        _build_lookup(
            entsoe_slots
        )
    )

    timestamps = set()

    timestamps.update(
        nordpool_lookup.keys()
    )

    timestamps.update(
        entsoe_lookup.keys()
    )

    ordered_timestamps = sorted(
        timestamps
    )

    consensus_slots = []

    counts = {
        "both_sources": 0,
        "exact": 0,
        "small_difference": 0,
        "mismatch": 0,
        "nordpool_only": 0,
        "entsoe_only": 0,
        "missing": 0,
        "learning_allowed": 0,
    }

    differences = []

    for start in ordered_timestamps:
        nordpool_slot = (
            nordpool_lookup.get(
                start
            )
        )

        entsoe_slot = (
            entsoe_lookup.get(
                start
            )
        )

        nordpool_price = None

        if isinstance(
            nordpool_slot,
            dict,
        ):
            nordpool_price = (
                safe_float(
                    nordpool_slot.get(
                        "price_eur_kwh"
                    )
                )
            )

        entsoe_price = None

        if isinstance(
            entsoe_slot,
            dict,
        ):
            entsoe_price = (
                safe_float(
                    entsoe_slot.get(
                        "price_eur_kwh"
                    )
                )
            )

        agreement = _agreement(
            nordpool_price,
            entsoe_price,
        )

        status = agreement.get(
            "status"
        )

        if status in counts:
            counts[
                status
            ] += 1

        if (
            nordpool_price is not None
            and entsoe_price is not None
        ):
            counts[
                "both_sources"
            ] += 1

        if agreement.get(
            "learning_allowed"
        ):
            counts[
                "learning_allowed"
            ] += 1

        difference = (
            agreement.get(
                "difference_eur_kwh"
            )
        )

        if difference is not None:
            differences.append(
                difference
            )

        market_price = None
        source = "missing"

        # Nord Pool is onze primaire
        # kale marktfeed.
        #
        # ENTSO-E is controle/fallback.
        if nordpool_price is not None:
            market_price = (
                nordpool_price
            )

            if entsoe_price is not None:
                source = (
                    "nordpool_verified_by_entsoe"
                )

            else:
                source = "nordpool"

        elif entsoe_price is not None:
            market_price = (
                entsoe_price
            )

            source = (
                "entsoe_fallback"
            )

        end = None

        if isinstance(
            nordpool_slot,
            dict,
        ):
            end = _slot_end(
                nordpool_slot
            )

        if (
            end is None
            and isinstance(
                entsoe_slot,
                dict,
            )
        ):
            end = _slot_end(
                entsoe_slot
            )

        interval = None

        if isinstance(
            nordpool_slot,
            dict,
        ):
            interval = (
                nordpool_slot
                .get(
                    "interval_minutes"
                )
            )

        if (
            interval is None
            and isinstance(
                entsoe_slot,
                dict,
            )
        ):
            interval = (
                entsoe_slot
                .get(
                    "interval_minutes"
                )
            )

        consensus_slots.append(
            {
                "start_utc":
                    start,

                "end_utc":
                    end,

                "interval_minutes":
                    interval,

                "market_price_eur_kwh":
                    market_price,

                "market_source":
                    source,

                "nordpool_price_eur_kwh":
                    nordpool_price,

                "entsoe_price_eur_kwh":
                    entsoe_price,

                "agreement":
                    status,

                "difference_eur_kwh":
                    agreement.get(
                        "difference_eur_kwh"
                    ),

                "difference_cent_kwh":
                    agreement.get(
                        "difference_cent_kwh"
                    ),

                "source_quality":
                    agreement.get(
                        "quality"
                    ),

                "learning_allowed":
                    agreement.get(
                        "learning_allowed"
                    ),
            }
        )

    max_difference = None
    avg_difference = None

    if differences:
        max_difference = max(
            differences
        )

        avg_difference = (
            sum(differences)
            / len(differences)
        )

    status = "ok"

    if len(
        consensus_slots
    ) == 0:
        status = "no_data"

    elif counts[
        "mismatch"
    ] > 0:
        status = "source_mismatch"

    elif (
        len(nordpool_slots) == 0
        or len(entsoe_slots) == 0
    ):
        status = "single_source"

    elif (
        counts[
            "both_sources"
        ]
        != len(
            consensus_slots
        )
    ):
        status = "partial"

    complete_verified_day = (
        len(consensus_slots) > 0
        and counts[
            "both_sources"
        ]
        == len(
            consensus_slots
        )
        and counts[
            "mismatch"
        ] == 0
        and counts[
            "nordpool_only"
        ] == 0
        and counts[
            "entsoe_only"
        ] == 0
    )

    return {
        "version":
            CONSENSUS_VERSION,

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "delivery_date":
            date_text,

        "status":
            status,

        "primary_source":
            "nordpool",

        "verification_source":
            "entsoe",

        "note":
            (
                "Nord Pool en ENTSO-E zijn "
                "marktbronnen voor dezelfde "
                "day-ahead markt. ENTSO-E wordt "
                "hier gebruikt als data-integriteitscontrole, "
                "niet als onafhankelijk voorspelmodel."
            ),

        "nordpool_file":
            str(
                nordpool_path
            ),

        "entsoe_file":
            str(
                entsoe_path
            ),

        "nordpool_file_exists":
            nordpool_path.exists(),

        "entsoe_file_exists":
            entsoe_path.exists(),

        "nordpool_slots":
            len(
                nordpool_slots
            ),

        "entsoe_slots":
            len(
                entsoe_slots
            ),

        "consensus_slots":
            len(
                consensus_slots
            ),

        "both_sources":
            counts[
                "both_sources"
            ],

        "exact_matches":
            counts[
                "exact"
            ],

        "small_differences":
            counts[
                "small_difference"
            ],

        "mismatches":
            counts[
                "mismatch"
            ],

        "nordpool_only":
            counts[
                "nordpool_only"
            ],

        "entsoe_only":
            counts[
                "entsoe_only"
            ],

        "learning_allowed_slots":
            counts[
                "learning_allowed"
            ],

        "complete_verified_day":
            complete_verified_day,

        "avg_difference_eur_kwh":
            (
                round(
                    avg_difference,
                    7,
                )
                if avg_difference
                is not None
                else None
            ),

        "avg_difference_cent_kwh":
            (
                round(
                    avg_difference
                    * 100,
                    5,
                )
                if avg_difference
                is not None
                else None
            ),

        "max_difference_eur_kwh":
            (
                round(
                    max_difference,
                    7,
                )
                if max_difference
                is not None
                else None
            ),

        "max_difference_cent_kwh":
            (
                round(
                    max_difference
                    * 100,
                    5,
                )
                if max_difference
                is not None
                else None
            ),

        "payload_hash":
            _payload_hash(
                consensus_slots
            ),

        "slots":
            consensus_slots,
    }


def store_market_consensus(
    delivery_date
):
    result = (
        build_market_consensus(
            delivery_date
        )
    )

    path = (
        consensus_day_file(
            delivery_date
        )
    )

    write_json_atomic(
        path,
        result,
    )

    summary = dict(
        result
    )

    summary.pop(
        "slots",
        None,
    )

    summary["file"] = str(
        path
    )

    return summary
