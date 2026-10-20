from .config import ROOT_DIR as CONFIG_ROOT_DIR
from datetime import datetime, timedelta, timezone
from pathlib import Path
import math


from .storage import (
    read_json,
    write_json_atomic,
)


DECISION_VERSION = "11.5.7-empirical-decision-confidence"

ROOT_DIR = CONFIG_ROOT_DIR

DATA_DIR = (
    ROOT_DIR
    / "data"
)

FORECAST_FILE = (
    DATA_DIR
    / "predictions"
    / "retail"
    / "retail_96h_latest.json"
)

OUTPUT_DIR = (
    DATA_DIR
    / "predictions"
    / "decision"
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "decision_96h_latest.json"
)

EVALUATION_FILE = DATA_DIR / "accuracy" / "forecast" / "forecast_evaluation_latest.json"
CALIBRATION_MAX_AGE_SECONDS = 12 * 3600
CALIBRATION_MIN_OBSERVATIONS = 96
CALIBRATION_MIN_UNIQUE_SLOTS = 96

BLOCK_SLOTS = {
    "1h": 4,
    "2h": 8,
    "3h": 12,
    "4h": 16,
    "6h": 24,
}


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

        if isinstance(
            value,
            datetime,
        ):
            dt = value

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


def _aware_datetime(value):
    """Do not silently interpret a malformed/local evaluation timestamp as UTC."""
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _empirical_calibration(report, now):
    metadata = {
        "status": "unavailable", "file": str(EVALUATION_FILE),
        "max_age_seconds": CALIBRATION_MAX_AGE_SECONDS,
        "minimum_observations_per_source": CALIBRATION_MIN_OBSERVATIONS,
        "minimum_unique_actual_slots": CALIBRATION_MIN_UNIQUE_SLOTS,
        "sources": {}, "is_probability_interval": False,
        "actual_price_resolution": "quarter_hour",
    }
    if not isinstance(report, dict) or report.get("status") != "ok":
        return {}, metadata
    created = _aware_datetime(report.get("created_utc"))
    age = (now - created).total_seconds() if created is not None else None
    metadata.update(created_utc=report.get("created_utc"), age_seconds=age)
    if age is None or not 0 <= age <= CALIBRATION_MAX_AGE_SECONDS:
        metadata["status"] = "stale_or_invalid_timestamp"
        return {}, metadata
    quarter = report.get("quarter_hour")
    if not isinstance(quarter, dict) or quarter.get("actual_price_resolution") != "quarter_hour":
        metadata["status"] = "awaiting_quarter_hour_actuals"
        return {}, metadata
    unique = safe_float(quarter.get("unique_actual_slots"))
    if isinstance(quarter.get("unique_actual_slots"), bool) or unique is None or unique < CALIBRATION_MIN_UNIQUE_SLOTS or not unique.is_integer():
        metadata["status"] = "insufficient_unique_slots"
        return {}, metadata
    groups = quarter.get("retail_by_market_source")
    groups = groups if isinstance(groups, dict) else {}
    floors = {}
    for source in ("nordpool_known", "ai_market_forecast"):
        group = groups.get(source)
        if not isinstance(group, dict):
            continue
        count = safe_float(group.get("count"))
        mae = safe_float(group.get("mae_cent_kwh"))
        source_unique = safe_float(group.get("unique_actual_slots"))
        if (isinstance(group.get("count"), bool) or isinstance(group.get("mae_cent_kwh"), bool)
                or count is None or not count.is_integer() or count < CALIBRATION_MIN_OBSERVATIONS
                or isinstance(group.get("unique_actual_slots"), bool) or source_unique is None
                or not source_unique.is_integer() or source_unique < CALIBRATION_MIN_UNIQUE_SLOTS
                or mae is None or mae < 0):
            continue
        floors[source] = mae
        metadata["sources"][source] = {"observations": int(count), "unique_actual_slots": int(source_unique), "retail_mae_cent_kwh": mae}
    metadata.update(status="applied" if floors else "insufficient_source_metrics", unique_actual_slots=int(unique))
    return floors, metadata


def _confidence_level(
    market_source,
    horizon_hours,
    market_mae,
):
    if market_source == "nordpool_known":
        return "high"

    horizon = safe_float(
        horizon_hours
    )

    error = safe_float(
        market_mae
    )

    if (
        horizon is None
        or error is None
    ):
        return "unknown"

    if (
        horizon <= 48
        and error <= 2.5
    ):
        return "medium_high"

    if (
        horizon <= 72
        and error <= 3.5
    ):
        return "medium"

    return "low"


def _annotate_row(row, empirical_floors=None):
    if not isinstance(
        row,
        dict,
    ):
        return None

    price = safe_float(
        row.get(
            "retail_price_cent_kwh"
        )
    )

    if price is None:
        return None

    market_source = row.get(
        "market_source"
    )

    market_mae = safe_float(
        row.get(
            "market_expected_mae_cent_kwh"
        )
    )

    retail_mae = safe_float(
        row.get(
            "retail_expected_mae_cent_kwh"
        )
    )

    if market_source == "nordpool_known":
        market_mae = 0.0

    guard = None

    if (
        market_mae is not None
        and retail_mae is not None
        and market_mae >= 0
        and retail_mae >= 0
    ):
        # Dit is bewust een conservatieve beslisband:
        # markt-MAE + retail-MAE.
        #
        # Het is GEEN statistisch 95%-interval.
        guard = (
            market_mae
            + retail_mae
        )

    old_guard = guard
    empirical_mae = safe_float((empirical_floors or {}).get(market_source))
    if empirical_mae is not None and empirical_mae >= 0:
        guard = max(guard, empirical_mae) if guard is not None else empirical_mae
    else:
        empirical_mae = None
    guard_source = "empirical_retail_mae" if empirical_mae is not None and (old_guard is None or empirical_mae > old_guard) else "market_mae_plus_retail_mae"

    lower = None
    upper = None

    if guard is not None:
        lower = (
            price
            - guard
        )

        upper = (
            price
            + guard
        )

    confidence = (
        _confidence_level(
            market_source,
            row.get(
                "horizon_hours"
            ),
            market_mae,
        )
    )

    return {
        "timestamp_utc":
            row.get(
                "timestamp_utc"
            ),

        "timestamp_local":
            row.get(
                "timestamp_local"
            ),

        "horizon_hours":
            safe_float(
                row.get(
                    "horizon_hours"
                )
            ),

        "market_source":
            market_source,

        "market_model":
            row.get(
                "market_model"
            ),

        "retail_model":
            row.get(
                "retail_model"
            ),

        "market_price_cent_kwh":
            safe_float(
                row.get(
                    "market_price_cent_kwh"
                )
            ),

        "retail_price_cent_kwh":
            price,

        "market_mae_cent_kwh":
            market_mae,

        "retail_mae_cent_kwh":
            retail_mae,

        "empirical_retail_mae_cent_kwh": empirical_mae,
        "decision_guard_source": guard_source,

        "decision_guard_cent_kwh":
            (
                round(
                    guard,
                    5,
                )
                if guard
                is not None
                else None
            ),

        "decision_lower_cent_kwh":
            (
                round(
                    lower,
                    5,
                )
                if lower
                is not None
                else None
            ),

        "decision_upper_cent_kwh":
            (
                round(
                    upper,
                    5,
                )
                if upper
                is not None
                else None
            ),

        "confidence_level":
            confidence,
    }


def _best_by_price(rows):
    candidates = []

    for row in rows:
        price = safe_float(
            row.get(
                "retail_price_cent_kwh"
            )
        )

        if price is None:
            continue

        candidates.append(
            row
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item:
            item[
                "retail_price_cent_kwh"
            ]
    )

    return candidates[0]


def _best_known(rows):
    known = []

    for row in rows:
        if row.get(
            "market_source"
        ) != "nordpool_known":
            continue

        price = safe_float(
            row.get(
                "retail_price_cent_kwh"
            )
        )

        if price is None:
            continue

        known.append(
            row
        )

    if not known:
        return None

    known.sort(
        key=lambda item:
            item[
                "retail_price_cent_kwh"
            ]
    )

    return known[0]


def _best_ai_upper(rows):
    candidates = []

    for row in rows:
        if row.get(
            "market_source"
        ) != "ai_market_forecast":
            continue

        upper = safe_float(
            row.get(
                "decision_upper_cent_kwh"
            )
        )

        if upper is None:
            continue

        candidates.append(
            row
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item:
            item[
                "decision_upper_cent_kwh"
            ]
    )

    return candidates[0]


def _compact_row(row):
    if not isinstance(
        row,
        dict,
    ):
        return None

    return {
        "timestamp_local":
            row.get(
                "timestamp_local"
            ),

        "retail_price_cent_kwh":
            row.get(
                "retail_price_cent_kwh"
            ),

        "market_source":
            row.get(
                "market_source"
            ),

        "confidence_level":
            row.get(
                "confidence_level"
            ),

        "decision_guard_cent_kwh":
            row.get(
                "decision_guard_cent_kwh"
            ),

        "decision_lower_cent_kwh":
            row.get(
                "decision_lower_cent_kwh"
            ),

        "decision_upper_cent_kwh":
            row.get(
                "decision_upper_cent_kwh"
            ),
    }


def _build_safe_choice(rows):
    expected = (
        _best_by_price(
            rows
        )
    )

    known = (
        _best_known(
            rows
        )
    )

    ai = (
        _best_ai_upper(
            rows
        )
    )

    if expected is None:
        return {
            "decision":
                "no_forecast",
        }

    if known is None:
        return {
            "decision":
                "use_best_expected",

            "reason":
                "no_known_market_slot_available",

            "selected":
                _compact_row(
                    expected
                ),

            "best_expected":
                _compact_row(
                    expected
                ),

            "best_known":
                None,
        }

    if ai is None:
        return {
            "decision":
                "prefer_known",

            "reason":
                "no_ai_slot_with_valid_uncertainty",

            "selected":
                _compact_row(
                    known
                ),

            "best_expected":
                _compact_row(
                    expected
                ),

            "best_known":
                _compact_row(
                    known
                ),
        }

    known_lower = safe_float(
        known.get(
            "decision_lower_cent_kwh"
        )
    )

    ai_upper = safe_float(
        ai.get(
            "decision_upper_cent_kwh"
        )
    )

    expected_saving = (
        known[
            "retail_price_cent_kwh"
        ]
        - ai[
            "retail_price_cent_kwh"
        ]
    )

    if (
        known_lower is not None
        and ai_upper is not None
        and ai_upper < known_lower
    ):
        return {
            "decision":
                "use_ai_forecast",

            "reason":
                "ai_upper_band_below_known_lower_band",

            "selected":
                _compact_row(
                    ai
                ),

            "best_expected":
                _compact_row(
                    expected
                ),

            "best_known":
                _compact_row(
                    known
                ),

            "best_ai":
                _compact_row(
                    ai
                ),

            "expected_saving_vs_known_cent_kwh":
                round(
                    expected_saving,
                    4,
                ),

            "safety_gap_cent_kwh":
                round(
                    known_lower
                    - ai_upper,
                    4,
                ),
        }

    return {
        "decision":
            "prefer_known",

        "reason":
            "predicted_saving_not_large_enough_for_uncertainty",

        "selected":
            _compact_row(
                known
            ),

        "best_expected":
            _compact_row(
                expected
            ),

        "best_known":
            _compact_row(
                known
            ),

        "best_ai":
            _compact_row(
                ai
            ),

        "expected_saving_vs_known_cent_kwh":
            round(
                expected_saving,
                4,
            ),

        "required_extra_advantage_cent_kwh":
            (
                round(
                    ai_upper
                    - known_lower,
                    4,
                )
                if (
                    ai_upper is not None
                    and known_lower
                    is not None
                )
                else None
            ),
    }


def _is_contiguous(window):
    if len(window) < 2:
        return True

    previous = None

    for row in window:
        dt = parse_datetime(
            row.get(
                "timestamp_utc"
            )
        )

        if dt is None:
            return False

        if previous is not None:
            difference = (
                dt
                - previous
            ).total_seconds()

            if difference != 900:
                return False

        previous = dt

    return True


def _block_summary(window):
    if not window:
        return None

    prices = []

    upper_prices = []

    known_count = 0

    for row in window:
        price = safe_float(
            row.get(
                "retail_price_cent_kwh"
            )
        )

        upper = safe_float(
            row.get(
                "decision_upper_cent_kwh"
            )
        )

        if price is None:
            return None

        prices.append(
            price
        )

        if upper is not None:
            upper_prices.append(
                upper
            )

        if row.get(
            "market_source"
        ) == "nordpool_known":
            known_count += 1

    average_price = (
        sum(prices)
        / len(prices)
    )

    average_upper = None

    if len(upper_prices) == len(
        prices
    ):
        average_upper = (
            sum(upper_prices)
            / len(upper_prices)
        )

    return {
        "start_local":
            window[0].get(
                "timestamp_local"
            ),

        "end_local":
            window[-1].get(
                "timestamp_local"
            ),

        "slots":
            len(window),

        "average_price_cent_kwh":
            round(
                average_price,
                4,
            ),

        "average_upper_cent_kwh":
            (
                round(
                    average_upper,
                    4,
                )
                if average_upper
                is not None
                else None
            ),

        "known_market_slots":
            known_count,

        "ai_market_slots":
            (
                len(window)
                - known_count
            ),

        "known_market_pct":
            round(
                known_count
                / len(window)
                * 100,
                1,
            ),
    }


def _best_blocks(
    rows,
    slot_count,
):
    candidates = []

    if len(rows) < slot_count:
        return {
            "best_expected":
                None,

            "best_guarded":
                None,
        }

    for start in range(
        0,
        len(rows)
        - slot_count
        + 1,
    ):
        window = rows[
            start:
            start
            + slot_count
        ]

        if not _is_contiguous(
            window
        ):
            continue

        summary = (
            _block_summary(
                window
            )
        )

        if summary is not None:
            candidates.append(
                summary
            )

    if not candidates:
        return {
            "best_expected":
                None,

            "best_guarded":
                None,
        }

    expected_candidates = list(
        candidates
    )

    expected_candidates.sort(
        key=lambda item:
            item[
                "average_price_cent_kwh"
            ]
    )

    guarded_candidates = []

    for candidate in candidates:
        if candidate.get(
            "average_upper_cent_kwh"
        ) is not None:
            guarded_candidates.append(
                candidate
            )

    guarded_candidates.sort(
        key=lambda item:
            item[
                "average_upper_cent_kwh"
            ]
    )

    return {
        "best_expected":
            expected_candidates[0],

        "best_guarded":
            (
                guarded_candidates[0]
                if guarded_candidates
                else None
            ),
    }


def build_decision_confidence():
    now = datetime.now(timezone.utc)
    empirical_floors, calibration = _empirical_calibration(read_json(EVALUATION_FILE, default={}), now)
    forecast_payload = read_json(
        FORECAST_FILE,
        default={},
    )

    if not isinstance(
        forecast_payload,
        dict,
    ):
        return {
            "status":
                "missing_forecast",

            "version":
                DECISION_VERSION,
        }

    raw_rows = forecast_payload.get(
        "forecast",
        [],
    )

    if not isinstance(
        raw_rows,
        list,
    ):
        return {
            "status":
                "invalid_forecast",

            "version":
                DECISION_VERSION,
        }

    rows = []

    discarded_expired_slots = 0
    discarded_invalid_timestamps = 0
    for raw in raw_rows:
        stamp = _aware_datetime(raw.get("timestamp_utc")) if isinstance(raw, dict) else None
        if stamp is None:
            discarded_invalid_timestamps += 1
            continue
        if stamp + timedelta(minutes=15) <= now:
            discarded_expired_slots += 1
            continue
        annotated = (
            _annotate_row(
                raw, empirical_floors
            )
        )

        if annotated is not None:
            rows.append(
                annotated
            )

    rows.sort(
        key=lambda item:
            str(
                item.get(
                    "timestamp_utc",
                    "",
                )
            )
    )

    confidence_counts = {
        "high": 0,
        "medium_high": 0,
        "medium": 0,
        "low": 0,
        "unknown": 0,
    }

    for row in rows:
        level = row.get(
            "confidence_level",
            "unknown",
        )

        if level not in confidence_counts:
            level = "unknown"

        confidence_counts[
            level
        ] += 1

    safe_choice = (
        _build_safe_choice(
            rows
        )
    )

    blocks = {}

    for name, slots in (
        BLOCK_SLOTS.items()
    ):
        blocks[name] = (
            _best_blocks(
                rows,
                slots,
            )
        )

    payload = {
        "version":
            DECISION_VERSION,

        "status":
            "ok",

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "forecast_version":
            forecast_payload.get(
                "version"
            ),

        "issue_time_utc":
            forecast_payload.get(
                "issue_time_utc"
            ),

        "issue_time_local":
            forecast_payload.get(
                "issue_time_local"
            ),

        "slots":
            len(rows),

        "confidence_counts":
            confidence_counts,

        "safe_choice":
            safe_choice,

        "blocks":
            blocks,

        "forecast":
            rows,

        "empirical_calibration": calibration,
        "discarded_expired_slots": discarded_expired_slots,
        "discarded_invalid_timestamps": discarded_invalid_timestamps,

        "rules": {
            "decision_guard":
                "max(market_mae_plus_retail_mae, recent_source_retail_mae)",

            "guard_is_probability_interval":
                False,

            "known_market_preferred_when_bands_overlap":
                True,

            "ai_selected_only_when_upper_band_beats_known_lower_band":
                True,
        },

        "notes": [
            "Alleen recente MAE tegen expliciete kwartiertarieven is per marktbron een ondergrens voor de beslisband; historische uurtarieven kalibreren deze band niet.",
            "De MAE telt forecast-observaties; meerdere uitgiftes voor hetzelfde kwartier zijn niet onafhankelijk.",
            "Verlopen kwartieren en ongeldige tijdstempels doen niet mee aan de keuze.",
            "Decision guard is een conservatieve beslisband, geen statistisch betrouwbaarheidsinterval.",
            "Officiële Nord Pool-prijzen krijgen hoge confidence omdat de kale marktprijs dan bekend is.",
            "AI-prijzen worden alleen als veilige winnaar gekozen wanneer hun conservatieve bovengrens onder de ondergrens van de beste bekende prijs ligt.",
            "Expected block en guarded block worden apart gerapporteerd.",
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

    selected = safe_choice.get(
        "selected",
        {},
    )

    if not isinstance(
        selected,
        dict,
    ):
        selected = {}

    best_expected = safe_choice.get(
        "best_expected",
        {},
    )

    if not isinstance(
        best_expected,
        dict,
    ):
        best_expected = {}

    best_known = safe_choice.get(
        "best_known",
        {},
    )

    if not isinstance(
        best_known,
        dict,
    ):
        best_known = {}

    return {
        "version":
            DECISION_VERSION,

        "status":
            "ok",

        "slots":
            len(rows),

        "confidence_counts":
            confidence_counts,

        "decision":
            safe_choice.get(
                "decision"
            ),

        "decision_reason":
            safe_choice.get(
                "reason"
            ),

        "selected_timestamp":
            selected.get(
                "timestamp_local"
            ),

        "selected_price_cent_kwh":
            selected.get(
                "retail_price_cent_kwh"
            ),

        "selected_market_source":
            selected.get(
                "market_source"
            ),

        "selected_confidence":
            selected.get(
                "confidence_level"
            ),

        "best_expected_timestamp":
            best_expected.get(
                "timestamp_local"
            ),

        "best_expected_price_cent_kwh":
            best_expected.get(
                "retail_price_cent_kwh"
            ),

        "best_expected_source":
            best_expected.get(
                "market_source"
            ),

        "best_known_timestamp":
            best_known.get(
                "timestamp_local"
            ),

        "best_known_price_cent_kwh":
            best_known.get(
                "retail_price_cent_kwh"
            ),

        "expected_saving_vs_known_cent_kwh":
            safe_choice.get(
                "expected_saving_vs_known_cent_kwh"
            ),

        "safety_gap_cent_kwh":
            safe_choice.get(
                "safety_gap_cent_kwh"
            ),

        "required_extra_advantage_cent_kwh":
            safe_choice.get(
                "required_extra_advantage_cent_kwh"
            ),

        "blocks":
            blocks,

        "empirical_calibration": calibration,
        "discarded_expired_slots": discarded_expired_slots,
        "discarded_invalid_timestamps": discarded_invalid_timestamps,

        "output_file":
            str(
                OUTPUT_FILE
            ),
    }


def decision_confidence_self_test():
    rows = [
        {
            "timestamp_utc":
                "2026-09-04T10:00:00+00:00",

            "timestamp_local":
                "2026-09-04T12:00:00+02:00",

            "horizon_hours":
                20,

            "market_source":
                "nordpool_known",

            "retail_price_cent_kwh":
                20.0,

            "market_expected_mae_cent_kwh":
                0.0,

            "retail_expected_mae_cent_kwh":
                1.0,
        },
        {
            "timestamp_utc":
                "2026-09-05T10:00:00+00:00",

            "timestamp_local":
                "2026-09-05T12:00:00+02:00",

            "horizon_hours":
                44,

            "market_source":
                "ai_market_forecast",

            "retail_price_cent_kwh":
                19.5,

            "market_expected_mae_cent_kwh":
                2.0,

            "retail_expected_mae_cent_kwh":
                1.0,
        },
    ]

    annotated = []

    for row in rows:
        item = _annotate_row(
            row
        )

        if item is not None:
            annotated.append(
                item
            )

    decision = (
        _build_safe_choice(
            annotated
        )
    )

    ok = (
        len(annotated) == 2
        and annotated[0].get(
            "confidence_level"
        ) == "high"
        and annotated[1].get(
            "decision_guard_cent_kwh"
        ) == 3.0
        and decision.get(
            "decision"
        ) == "prefer_known"
    )

    return {
        "status":
            (
                "ok"
                if ok
                else "error"
            ),

        "version":
            DECISION_VERSION,

        "known_confidence":
            annotated[0].get(
                "confidence_level"
            ),

        "ai_guard":
            annotated[1].get(
                "decision_guard_cent_kwh"
            ),

        "decision":
            decision.get(
                "decision"
            ),
    }
