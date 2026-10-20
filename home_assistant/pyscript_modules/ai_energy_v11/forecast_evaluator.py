from .config import ROOT_DIR as CONFIG_ROOT_DIR
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import math
import json
import os

from .storage import (
    read_json,
    write_json_atomic,
)

from .retail_learner import (
    load_training_rows,
)


EVALUATOR_VERSION = "11.5.8-immutable-forward-evaluator"

ROOT_DIR = CONFIG_ROOT_DIR

DATA_DIR = (
    ROOT_DIR
    / "data"
)

RETAIL_LATEST_FILE = (
    DATA_DIR
    / "predictions"
    / "retail"
    / "retail_96h_latest.json"
)

FORECAST_ARCHIVE_DIR = (
    DATA_DIR
    / "predictions"
    / "retail"
    / "archive"
)

ACCURACY_DIR = (
    DATA_DIR
    / "accuracy"
    / "forecast"
)

EVALUATION_FILE = (
    ACCURACY_DIR
    / "forecast_evaluation_latest.json"
)

DEFAULT_LOOKBACK_DAYS = 35


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


def _archive_path(issue_dt):
    directory = (
        FORECAST_ARCHIVE_DIR
        / issue_dt.strftime("%Y")
        / issue_dt.strftime("%m")
        / issue_dt.strftime("%d")
    )

    filename = (
        issue_dt.strftime(
            "%H%M%S"
        )
        + ".json"
    )

    return (
        directory
        / filename
    )


def _write_archive_once(path, payload):
    """Exclusive creation prevents overwrites, including competing archive writers."""
    if path.exists():
        return False
    # Serialize first so invalid values never leave a partially created archive.
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2)
    try:
        with open(path, "x", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        return False
    # A crash during the write may leave incomplete JSON; read_json then excludes
    # that archive. Never replace it automatically with a later hindsight forecast.
    return True


def _generation_cutoff(payload, issue_dt):
    """Use recorded times only. Older issue-only snapshots stay identifiable."""
    cutoff = issue_dt
    basis = "issue_time_only"
    for field in ("created_utc", "issued_utc"):
        value = payload.get(field)
        if value is None or value == "":
            continue
        recorded = parse_datetime(value)
        if recorded is None:
            return None, "invalid_generation_time"
        cutoff = max(cutoff, recorded)
        basis = "recorded_generation_and_issue"
    return cutoff, basis


def archive_current_forecast():
    payload = read_json(
        RETAIL_LATEST_FILE,
        default={},
    )

    if not isinstance(
        payload,
        dict,
    ):
        return {
            "version":
                EVALUATOR_VERSION,

            "status":
                "missing_forecast",
        }

    if payload.get(
        "status"
    ) != "ok":
        return {
            "version":
                EVALUATOR_VERSION,

            "status":
                "forecast_not_ok",
        }

    forecast = payload.get(
        "forecast",
        [],
    )

    if not isinstance(
        forecast,
        list,
    ):
        return {
            "version":
                EVALUATOR_VERSION,

            "status":
                "invalid_forecast",
        }

    issue_dt = parse_datetime(
        payload.get(
            "issue_time_utc"
        )
    )

    if issue_dt is None:
        issue_dt = parse_datetime(
            payload.get(
                "created_utc"
            )
        )

    if issue_dt is None:
        return {
            "version":
                EVALUATOR_VERSION,

            "status":
                "missing_issue_time",
        }

    archive_file = (
        _archive_path(
            issue_dt
        )
    )

    archive_payload = dict(
        payload
    )

    archive_payload[
        "archive_version"
    ] = EVALUATOR_VERSION

    archive_payload[
        "archived_utc"
    ] = datetime.now(
        timezone.utc
    ).isoformat()

    archive_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    created = _write_archive_once(archive_file, archive_payload)
    archived_slots = len(forecast)
    if not created:
        existing = read_json(archive_file, default={})
        existing_rows = existing.get("forecast") if isinstance(existing, dict) else None
        archived_slots = len(existing_rows) if isinstance(existing_rows, list) else None

    return {
        "archive_action": "created" if created else "preserved_existing",
        "version":
            EVALUATOR_VERSION,

        "status":
            "ok",

        "issue_time_utc":
            issue_dt.isoformat(),

        "slots":
            archived_slots,

        "archive_file":
            str(
                archive_file
            ),
    }


def _actual_map():
    loaded = (
        load_training_rows()
    )

    rows = loaded.get(
        "rows",
        [],
    )

    result = {}

    for row in rows:
        timestamp = parse_datetime(
            row.get(
                "timestamp"
            )
        )

        if timestamp is None:
            continue

        actual_retail = safe_float(
            row.get(
                "actual"
            )
        )

        actual_market = safe_float(
            row.get(
                "market"
            )
        )

        if (
            actual_retail is None
            and actual_market is None
        ):
            continue

        result[
            timestamp.isoformat()
        ] = {
            "actual_price_resolution": row.get("actual_price_resolution", "legacy_hourly"),
            "actual_price_source": row.get("actual_price_source", "legacy_unrecorded"),
            "retail":
                actual_retail,

            "market":
                actual_market,
        }

    return result


def _bucket(
    horizon_hours
):
    value = safe_float(
        horizon_hours
    )

    if value is None:
        return "unknown"

    if value <= 24:
        return "0_24h"

    if value <= 48:
        return "24_48h"

    if value <= 72:
        return "48_72h"

    return "72_96h"


def _metrics(errors):
    if not errors:
        return {
            "count": 0,
            "mae_cent_kwh": None,
            "rmse_cent_kwh": None,
            "bias_cent_kwh": None,
        }

    absolute = []
    squared = []

    for error in errors:
        absolute.append(
            abs(error)
        )

        squared.append(
            error * error
        )

    mae = (
        sum(absolute)
        / len(absolute)
    )

    rmse = math.sqrt(
        sum(squared)
        / len(squared)
    )

    bias = (
        sum(errors)
        / len(errors)
    )

    return {
        "count":
            len(errors),

        "mae_cent_kwh":
            round(
                mae,
                5,
            ),

        "rmse_cent_kwh":
            round(
                rmse,
                5,
            ),

        "bias_cent_kwh":
            round(
                bias,
                5,
            ),

        "best_abs_error_cent_kwh":
            round(
                min(absolute),
                5,
            ),

        "worst_abs_error_cent_kwh":
            round(
                max(absolute),
                5,
            ),
    }


def _archive_files(
    now_utc,
    lookback_days
):
    if not FORECAST_ARCHIVE_DIR.exists():
        return []

    cutoff = (
        now_utc
        - timedelta(
            days=lookback_days
        )
    )

    result = []

    for path in sorted(
        FORECAST_ARCHIVE_DIR.rglob(
            "*.json"
        )
    ):
        payload = read_json(
            path,
            default={},
        )

        if not isinstance(
            payload,
            dict,
        ):
            continue

        issue_dt = parse_datetime(
            payload.get(
                "issue_time_utc"
            )
        )

        if issue_dt is None:
            continue

        if issue_dt < cutoff:
            continue

        if issue_dt > now_utc:
            continue

        result.append(
            (
                path,
                payload,
                issue_dt,
            )
        )

    return result


def evaluate_forecasts(
    lookback_days=DEFAULT_LOOKBACK_DAYS,
):
    try:
        days = int(
            lookback_days
        )

    except Exception:
        days = (
            DEFAULT_LOOKBACK_DAYS
        )

    if days < 1:
        days = 1

    if days > 120:
        days = 120

    now_utc = datetime.now(
        timezone.utc
    )

    actuals = (
        _actual_map()
    )

    archives = (
        _archive_files(
            now_utc,
            days,
        )
    )

    quarter_errors = []
    quarter_by_source = defaultdict(list)
    quarter_by_horizon = defaultdict(list)
    quarter_targets = set()
    quarter_targets_by_source = defaultdict(set)
    quarter_actual_sources = set()

    retail_errors = []

    market_errors = []

    retail_by_source = defaultdict(
        list
    )

    market_by_source = defaultdict(
        list
    )

    retail_by_horizon = defaultdict(
        list
    )

    market_by_horizon = defaultdict(
        list
    )

    snapshot_summaries = []

    evaluated_targets = set()

    snapshots_with_actuals = 0

    total_forecast_points = 0
    evaluated_points = 0
    skipped_nonforward_points = 0
    skipped_invalid_generation_archives = 0
    generation_time_bases = defaultdict(int)

    for (
        path,
        payload,
        issue_dt,
    ) in archives:
        generation_cutoff, generation_basis = _generation_cutoff(payload, issue_dt)
        if generation_cutoff is None or generation_cutoff > now_utc:
            skipped_invalid_generation_archives += 1
            continue
        generation_time_bases[generation_basis] += 1
        forecast = payload.get(
            "forecast",
            [],
        )

        if not isinstance(
            forecast,
            list,
        ):
            continue

        snapshot_retail_errors = []
        snapshot_market_errors = []

        snapshot_points = 0

        for row in forecast:
            if not isinstance(
                row,
                dict,
            ):
                continue

            total_forecast_points += 1

            target_dt = parse_datetime(
                row.get(
                    "timestamp_utc"
                )
            )

            if target_dt is None:
                continue
            if target_dt <= generation_cutoff:
                skipped_nonforward_points += 1
                continue

            actual = actuals.get(
                target_dt.isoformat()
            )

            if not isinstance(
                actual,
                dict,
            ):
                continue

            predicted_retail = safe_float(
                row.get(
                    "retail_price_cent_kwh"
                )
            )

            predicted_market = safe_float(
                row.get(
                    "market_price_cent_kwh"
                )
            )

            actual_retail_eur = safe_float(
                actual.get(
                    "retail"
                )
            )

            actual_market_eur = safe_float(
                actual.get(
                    "market"
                )
            )

            actual_retail = None
            actual_market = None

            if actual_retail_eur is not None:
                actual_retail = (
                    actual_retail_eur
                    * 100
                )

            if actual_market_eur is not None:
                actual_market = (
                    actual_market_eur
                    * 100
                )

            # The row horizon can refer to an older ledger. Evaluate against
            # the actual recorded generation time, never a caller-provided horizon.
            horizon_hours = (target_dt - generation_cutoff).total_seconds() / 3600

            horizon_bucket = (
                _bucket(
                    horizon_hours
                )
            )

            market_source = row.get(
                "market_source",
                "unknown",
            )

            point_used = False

            if (
                predicted_retail is not None
                and actual_retail is not None
            ):
                error = (
                    predicted_retail
                    - actual_retail
                )

                if actual.get("actual_price_resolution") == "quarter_hour":
                    quarter_errors.append(error)
                    quarter_by_source[market_source].append(error)
                    quarter_by_horizon[horizon_bucket].append(error)
                    quarter_targets.add(target_dt.isoformat())
                    quarter_targets_by_source[market_source].add(target_dt.isoformat())
                    quarter_actual_sources.add(str(actual.get("actual_price_source", "unknown")))

                retail_errors.append(
                    error
                )

                snapshot_retail_errors.append(
                    error
                )

                retail_by_source[
                    market_source
                ].append(
                    error
                )

                retail_by_horizon[
                    horizon_bucket
                ].append(
                    error
                )

                point_used = True

            if (
                predicted_market is not None
                and actual_market is not None
            ):
                error = (
                    predicted_market
                    - actual_market
                )

                market_errors.append(
                    error
                )

                snapshot_market_errors.append(
                    error
                )

                market_by_source[
                    market_source
                ].append(
                    error
                )

                market_by_horizon[
                    horizon_bucket
                ].append(
                    error
                )

                point_used = True

            if point_used:
                evaluated_points += 1
                snapshot_points += 1

                evaluated_targets.add(
                    target_dt.isoformat()
                )

        if snapshot_points > 0:
            snapshots_with_actuals += 1

            snapshot_summaries.append(
                {
                    "issue_time_utc":
                        issue_dt.isoformat(),

                    "generation_cutoff_utc": generation_cutoff.isoformat(),
                    "generation_time_basis": generation_basis,
                    "archive_file":
                        str(path),

                    "evaluated_points":
                        snapshot_points,

                    "retail":
                        _metrics(
                            snapshot_retail_errors
                        ),

                    "market":
                        _metrics(
                            snapshot_market_errors
                        ),
                }
            )

    retail_source_metrics = {}

    for (
        source,
        errors,
    ) in retail_by_source.items():
        retail_source_metrics[
            source
        ] = _metrics(
            errors
        )

    market_source_metrics = {}

    for (
        source,
        errors,
    ) in market_by_source.items():
        market_source_metrics[
            source
        ] = _metrics(
            errors
        )

    retail_horizon_metrics = {}

    for bucket in (
        "0_24h",
        "24_48h",
        "48_72h",
        "72_96h",
        "unknown",
    ):
        retail_horizon_metrics[
            bucket
        ] = _metrics(
            retail_by_horizon.get(
                bucket,
                [],
            )
        )

    market_horizon_metrics = {}

    for bucket in (
        "0_24h",
        "24_48h",
        "48_72h",
        "72_96h",
        "unknown",
    ):
        market_horizon_metrics[
            bucket
        ] = _metrics(
            market_by_horizon.get(
                bucket,
                [],
            )
        )

    snapshot_summaries.sort(
        key=lambda row:
            row[
                "issue_time_utc"
            ]
    )

    quarter_hour = {
        "actual_price_resolution": "quarter_hour",
        "evaluated_points": len(quarter_errors),
        "unique_actual_slots": len(quarter_targets),
        "actual_price_sources": sorted(quarter_actual_sources),
        "retail_overall": _metrics(quarter_errors),
        "retail_by_market_source": {
            source: dict(_metrics(quarter_by_source.get(source, [])),
                         unique_actual_slots=len(quarter_targets_by_source.get(source, set())))
            for source in ("nordpool_known", "ai_market_forecast")
        },
        "retail_by_horizon": {
            bucket: _metrics(quarter_by_horizon.get(bucket, []))
            for bucket in ("0_24h", "24_48h", "48_72h", "72_96h", "unknown")
        },
    }

    forward_quality = {
        "skipped_nonforward_points": skipped_nonforward_points,
        "skipped_invalid_generation_archives": skipped_invalid_generation_archives,
        "generation_time_bases": dict(generation_time_bases),
        "horizon_basis": "target_start_minus_latest_recorded_generation_or_issue",
        "legacy_issue_only_note": "Geen generatiegegevens verzonnen: oude archieven zonder created_utc blijven gebaseerd op hun geregistreerde uitgifte.",
    }
    report = {
        "forward_quality": forward_quality,
        "actual_resolution_scope": "historical_mixed_including_legacy_hourly",
        "quarter_hour": quarter_hour,
        "version":
            EVALUATOR_VERSION,

        "status":
            "ok",

        "created_utc":
            now_utc.isoformat(),

        "lookback_days":
            days,

        "archives_scanned":
            len(archives),

        "snapshots_with_actuals":
            snapshots_with_actuals,

        "total_forecast_points":
            total_forecast_points,

        "evaluated_points":
            evaluated_points,

        "unique_actual_slots":
            len(
                evaluated_targets
            ),

        "retail_overall":
            _metrics(
                retail_errors
            ),

        "market_overall":
            _metrics(
                market_errors
            ),

        "retail_by_market_source":
            retail_source_metrics,

        "market_by_source":
            market_source_metrics,

        "retail_by_horizon":
            retail_horizon_metrics,

        "market_by_horizon":
            market_horizon_metrics,

        "recent_snapshots":
            snapshot_summaries[
                -24:
            ],

        "notes": [
            "Alleen targets na het laatst geregistreerde generatie-/uitgiftemoment tellen mee; horizons worden opnieuw berekend.",
            "Historische hoofdscores bevatten oude uurtarieven; quarter_hour bevat uitsluitend expliciet als kwartiertarief geregistreerde actuals.",
            "Meerdere uitgiftemomenten voor hetzelfde toekomstkwartier blijven afzonderlijke forecast-observaties.",
            "Known Nord Pool en AI market worden afzonderlijk beoordeeld.",
            "Horizonfouten worden apart bijgehouden voor 0-24, 24-48, 48-72 en 72-96 uur.",
            "De evaluator wijzigt geen modellen en verwijdert geen historische gegevens.",
        ],
    }

    ACCURACY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json_atomic(
        EVALUATION_FILE,
        report,
    )

    ai_retail = (
        retail_source_metrics.get(
            "ai_market_forecast",
            {},
        )
    )

    known_retail = (
        retail_source_metrics.get(
            "nordpool_known",
            {},
        )
    )

    ai_market = (
        market_source_metrics.get(
            "ai_market_forecast",
            {},
        )
    )

    return {
        "forward_quality": forward_quality,
        "actual_resolution_scope": "historical_mixed_including_legacy_hourly",
        "quarter_hour": quarter_hour,
        "version":
            EVALUATOR_VERSION,

        "status":
            "ok",

        "archives_scanned":
            len(archives),

        "snapshots_with_actuals":
            snapshots_with_actuals,

        "evaluated_points":
            evaluated_points,

        "unique_actual_slots":
            len(
                evaluated_targets
            ),

        "retail_mae_cent_kwh":
            report[
                "retail_overall"
            ].get(
                "mae_cent_kwh"
            ),

        "known_retail_mae_cent_kwh":
            known_retail.get(
                "mae_cent_kwh"
            ),

        "ai_retail_mae_cent_kwh":
            ai_retail.get(
                "mae_cent_kwh"
            ),

        "ai_market_mae_cent_kwh":
            ai_market.get(
                "mae_cent_kwh"
            ),

        "retail_horizons":
            retail_horizon_metrics,

        "market_horizons":
            market_horizon_metrics,

        "report_file":
            str(
                EVALUATION_FILE
            ),
    }


def forecast_evaluator_self_test():
    errors = [
        -1.0,
        1.0,
        2.0,
        -2.0,
    ]

    result = _metrics(
        errors
    )

    bucket_ok = (
        _bucket(12)
        == "0_24h"
        and _bucket(36)
        == "24_48h"
        and _bucket(60)
        == "48_72h"
        and _bucket(84)
        == "72_96h"
    )

    metrics_ok = (
        result.get(
            "count"
        ) == 4
        and abs(
            result.get(
                "mae_cent_kwh",
                0,
            )
            - 1.5
        )
        < 0.00001
        and abs(
            result.get(
                "bias_cent_kwh",
                999,
            )
        )
        < 0.00001
    )

    ok = (
        bucket_ok
        and metrics_ok
    )

    return {
        "version":
            EVALUATOR_VERSION,

        "status":
            (
                "ok"
                if ok
                else "error"
            ),

        "mae":
            result.get(
                "mae_cent_kwh"
            ),

        "bias":
            result.get(
                "bias_cent_kwh"
            ),

        "bucket_test":
            bucket_ok,
    }
