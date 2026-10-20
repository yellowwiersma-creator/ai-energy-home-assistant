from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import math
import statistics

from .config import (
    ACCURACY_DIR,
    LEGACY_NORMALIZED_DIR,
    MODEL_DIR,
    RAW_DIR,
    TIMEZONE,
)

from .storage import (
    read_json,
    write_json_atomic,
)


LEARNER_VERSION = "11.4.3-retail-actual-resolution"

LOCAL_TZ = ZoneInfo(TIMEZONE)

UNIFIED_DIR = (
    LEGACY_NORMALIZED_DIR
    / "unified"
)

LEARNER_MODEL_DIR = (
    MODEL_DIR
    / "retail"
)

LEARNER_ACCURACY_DIR = (
    ACCURACY_DIR
    / "retail"
)

CHAMPION_FILE = (
    LEARNER_MODEL_DIR
    / "retail_champion.json"
)

CHALLENGER_FILE = (
    LEARNER_MODEL_DIR
    / "retail_challenger_latest.json"
)

REPORT_FILE = (
    LEARNER_ACCURACY_DIR
    / "retail_learner_latest.json"
)

MARGIN_AUDIT_FILE = (
    ACCURACY_DIR
    / "margin"
    / "margin_audit_latest.json"
)

SHRINKAGE_STRENGTHS = (
    0,
    4,
    8,
    16,
    24,
    48,
)

MIN_TOTAL_ROWS = 500
MIN_TEST_ROWS = 100


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
                tzinfo=timezone.utc
            )

        return result

    except Exception:
        return None


def median(values):
    clean = []

    for value in values:
        number = safe_float(
            value
        )

        if number is not None:
            clean.append(
                number
            )

    if not clean:
        return None

    return statistics.median(
        clean
    )


def error_metrics(
    rows,
    predictions,
):
    absolute_errors = []
    squared_errors = []
    errors = []

    count = min(
        len(rows),
        len(predictions),
    )

    for index in range(
        count
    ):
        actual = safe_float(
            rows[index].get(
                "actual"
            )
        )

        predicted = safe_float(
            predictions[index]
        )

        if (
            actual is None
            or predicted is None
        ):
            continue

        error = (
            predicted
            - actual
        )

        errors.append(
            error
        )

        absolute_errors.append(
            abs(error)
        )

        squared_errors.append(
            error * error
        )

    if not absolute_errors:
        return {
            "count": 0,
            "mae_eur_kwh": None,
            "mae_cent_kwh": None,
            "rmse_eur_kwh": None,
            "rmse_cent_kwh": None,
            "bias_eur_kwh": None,
            "bias_cent_kwh": None,
        }

    mae = (
        sum(
            absolute_errors
        )
        / len(
            absolute_errors
        )
    )

    rmse = math.sqrt(
        sum(
            squared_errors
        )
        / len(
            squared_errors
        )
    )

    bias = (
        sum(errors)
        / len(errors)
    )

    return {
        "count":
            len(
                absolute_errors
            ),

        "mae_eur_kwh":
            round(
                mae,
                8,
            ),

        "mae_cent_kwh":
            round(
                mae * 100,
                5,
            ),

        "rmse_eur_kwh":
            round(
                rmse,
                8,
            ),

        "rmse_cent_kwh":
            round(
                rmse * 100,
                5,
            ),

        "bias_eur_kwh":
            round(
                bias,
                8,
            ),

        "bias_cent_kwh":
            round(
                bias * 100,
                5,
            ),
    }


def _normalize_datetime_fields(
    timestamp,
    local_hour=None,
    local_weekday=None,
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

    hour = local_hour
    weekday = local_weekday

    try:
        hour = int(
            hour
        )

    except Exception:
        hour = (
            local_dt.hour
        )

    try:
        weekday = int(
            weekday
        )

    except Exception:
        weekday = (
            local_dt.weekday()
        )

    return {
        "timestamp":
            dt.astimezone(
                timezone.utc
            ).isoformat(),

        "hour":
            hour,

        "weekday":
            weekday,

        "hour_of_week":
            (
                weekday
                * 24
                + hour
            ),
    }


def _normalize_unified_row(
    row
):
    if not isinstance(
        row,
        dict,
    ):
        return None

    learning = row.get(
        "learning",
        {},
    )

    if not isinstance(
        learning,
        dict,
    ):
        return None

    if learning.get(
        "margin"
    ) is not True:
        return None

    market = safe_float(
        row.get(
            "market_price_eur_kwh"
        )
    )

    actual = safe_float(
        row.get(
            "zonneplan_actual_eur_kwh"
        )
    )

    if (
        market is None
        or actual is None
    ):
        return None

    timestamp = (
        row.get(
            "slot_start_utc"
        )
        or row.get(
            "timestamp"
        )
    )

    time_fields = (
        _normalize_datetime_fields(
            timestamp,
            row.get(
                "local_hour"
            ),
            row.get(
                "local_weekday"
            ),
        )
    )

    if time_fields is None:
        return None

    return {
        "timestamp":
            time_fields[
                "timestamp"
            ],

        "hour":
            time_fields[
                "hour"
            ],

        "weekday":
            time_fields[
                "weekday"
            ],

        "hour_of_week":
            time_fields[
                "hour_of_week"
            ],

        "market":
            market,

        "actual":
            actual,

        "margin":
            (
                actual
                - market
            ),

        "actual_price_resolution": "quarter_hour" if row.get("actual_price_resolution") == "quarter_hour" else "legacy_hourly",
        "actual_price_source": row.get("actual_price_source", "legacy_unrecorded"),

        "data_source":
            "unified_history",

        "source_rank":
            1,
    }


def _normalize_live_row(
    row
):
    if not isinstance(
        row,
        dict,
    ):
        return None

    quality = row.get(
        "quality",
        {},
    )

    if not isinstance(
        quality,
        dict,
    ):
        return None

    if quality.get(
        "price_learning_eligible"
    ) is not True:
        return None

    price = row.get(
        "price",
        {},
    )

    if not isinstance(
        price,
        dict,
    ):
        return None

    market = safe_float(
        price.get(
            "market_price_eur_kwh"
        )
    )

    actual = safe_float(
        price.get(
            "zonneplan_actual_eur_kwh"
        )
    )

    if (
        market is None
        or actual is None
    ):
        return None

    timestamp = row.get(
        "slot_start_utc"
    )

    local_timestamp = row.get(
        "slot_start_local"
    )

    local_dt = parse_datetime(
        local_timestamp
    )

    hour = None
    weekday = None

    if local_dt is not None:
        local_dt = (
            local_dt
            .astimezone(
                LOCAL_TZ
            )
        )

        hour = local_dt.hour
        weekday = (
            local_dt.weekday()
        )

    time_fields = (
        _normalize_datetime_fields(
            timestamp,
            hour,
            weekday,
        )
    )

    if time_fields is None:
        return None

    return {
        "timestamp":
            time_fields[
                "timestamp"
            ],

        "hour":
            time_fields[
                "hour"
            ],

        "weekday":
            time_fields[
                "weekday"
            ],

        "hour_of_week":
            time_fields[
                "hour_of_week"
            ],

        "market":
            market,

        "actual":
            actual,

        "margin":
            (
                actual
                - market
            ),

        "actual_price_resolution": "quarter_hour" if price.get("actual_price_resolution") == "quarter_hour" else "legacy_hourly",
        "actual_price_source": price.get("actual_price_source", "legacy_unrecorded"),

        "data_source":
            "v11_live",

        "source_rank":
            2,
    }


def _read_json_lists(
    base_dir
):
    rows = []

    files = []

    path = Path(
        base_dir
    )

    if not path.exists():
        return files, rows

    for file_path in sorted(
        path.rglob(
            "*.json"
        )
    ):
        payload = read_json(
            file_path,
            default=[],
        )

        if not isinstance(
            payload,
            list,
        ):
            continue

        files.append(
            file_path
        )

        rows.extend(
            payload
        )

    return (
        files,
        rows,
    )


def load_training_rows():
    (
        unified_files,
        unified_raw,
    ) = _read_json_lists(
        UNIFIED_DIR
    )

    (
        live_files,
        live_raw,
    ) = _read_json_lists(
        RAW_DIR
    )

    candidates = []

    for row in unified_raw:
        normalized = (
            _normalize_unified_row(
                row
            )
        )

        if normalized is not None:
            candidates.append(
                normalized
            )

    for row in live_raw:
        normalized = (
            _normalize_live_row(
                row
            )
        )

        if normalized is not None:
            candidates.append(
                normalized
            )

    deduplicated = {}

    for row in candidates:
        key = row.get(
            "timestamp"
        )

        if key is None:
            continue

        existing = (
            deduplicated.get(
                key
            )
        )

        if existing is None:
            deduplicated[
                key
            ] = row

            continue

        if (
            row.get(
                "source_rank",
                0,
            )
            >= existing.get(
                "source_rank",
                0,
            )
        ):
            deduplicated[
                key
            ] = row

    rows = list(
        deduplicated.values()
    )

    rows.sort(
        key=lambda row:
            row.get(
                "timestamp",
                "",
            )
    )

    source_counts = defaultdict(
        int
    )

    for row in rows:
        source_counts[
            row.get(
                "data_source",
                "unknown",
            )
        ] += 1

    return {
        "rows":
            rows,

        "unified_files":
            len(
                unified_files
            ),

        "live_files":
            len(
                live_files
            ),

        "unified_raw_rows":
            len(
                unified_raw
            ),

        "live_raw_rows":
            len(
                live_raw
            ),

        "eligible_unique_rows":
            len(
                rows
            ),

        "source_counts":
            dict(
                source_counts
            ),
    }


def dataset_signature(
    rows
):
    digest = hashlib.sha256()

    for row in rows:
        text = (
            str(
                row.get(
                    "timestamp"
                )
            )
            + "|"
            + str(
                round(
                    row.get(
                        "market",
                        0.0,
                    ),
                    7,
                )
            )
            + "|"
            + str(
                round(
                    row.get(
                        "actual",
                        0.0,
                    ),
                    7,
                )
            )
            + "\n"
        )

        digest.update(
            text.encode(
                "utf-8"
            )
        )

    return digest.hexdigest()


def _fit_linear(
    rows
):
    if len(rows) < 2:
        return {
            "slope": 1.0,
            "intercept": 0.0,
        }

    x_values = [
        row["market"]
        for row in rows
    ]

    y_values = [
        row["actual"]
        for row in rows
    ]

    mean_x = (
        sum(x_values)
        / len(x_values)
    )

    mean_y = (
        sum(y_values)
        / len(y_values)
    )

    numerator = 0.0
    denominator = 0.0

    for index in range(
        len(rows)
    ):
        dx = (
            x_values[index]
            - mean_x
        )

        dy = (
            y_values[index]
            - mean_y
        )

        numerator += (
            dx * dy
        )

        denominator += (
            dx * dx
        )

    if denominator == 0:
        return {
            "slope":
                1.0,

            "intercept":
                median(
                    [
                        row["margin"]
                        for row in rows
                    ]
                )
                or 0.0,
        }

    slope = (
        numerator
        / denominator
    )

    intercept = (
        mean_y
        - slope
        * mean_x
    )

    return {
        "slope":
            slope,

        "intercept":
            intercept,
    }


def _shrink_value(
    bucket_value,
    global_value,
    count,
    strength,
):
    if bucket_value is None:
        return global_value

    if strength <= 0:
        return bucket_value

    weight = (
        count
        / (
            count
            + strength
        )
    )

    return (
        global_value
        + weight
        * (
            bucket_value
            - global_value
        )
    )


def fit_model(
    rows,
    model_type,
    strength=0,
):
    if model_type == (
        "constant_margin"
    ):
        global_margin = median(
            [
                row["margin"]
                for row in rows
            ]
        )

        return {
            "model_type":
                model_type,

            "strength":
                None,

            "parameters": {
                "global_margin":
                    global_margin,
            },
        }

    if model_type == (
        "linear_market"
    ):
        linear = _fit_linear(
            rows
        )

        return {
            "model_type":
                model_type,

            "strength":
                None,

            "parameters": {
                "slope":
                    linear[
                        "slope"
                    ],

                "intercept":
                    linear[
                        "intercept"
                    ],
            },
        }

    if model_type == (
        "hour_of_week_margin"
    ):
        global_margin = median(
            [
                row["margin"]
                for row in rows
            ]
        )

        buckets = defaultdict(
            list
        )

        for row in rows:
            buckets[
                str(
                    row[
                        "hour_of_week"
                    ]
                )
            ].append(
                row[
                    "margin"
                ]
            )

        learned = {}

        for key, values in (
            buckets.items()
        ):
            bucket_median = (
                median(
                    values
                )
            )

            learned[key] = {
                "count":
                    len(values),

                "raw_median":
                    bucket_median,

                "value":
                    _shrink_value(
                        bucket_median,
                        global_margin,
                        len(values),
                        strength,
                    ),
            }

        return {
            "model_type":
                model_type,

            "strength":
                strength,

            "parameters": {
                "global_margin":
                    global_margin,

                "hour_of_week":
                    learned,
            },
        }

    if model_type == (
        "linear_hour_residual"
    ):
        linear = _fit_linear(
            rows
        )

        slope = linear[
            "slope"
        ]

        intercept = linear[
            "intercept"
        ]

        residual_rows = []

        residuals = []

        for row in rows:
            base_prediction = (
                intercept
                + slope
                * row[
                    "market"
                ]
            )

            residual = (
                row[
                    "actual"
                ]
                - base_prediction
            )

            residuals.append(
                residual
            )

            residual_rows.append(
                {
                    "hour_of_week":
                        row[
                            "hour_of_week"
                        ],

                    "residual":
                        residual,
                }
            )

        global_residual = (
            median(
                residuals
            )
            or 0.0
        )

        buckets = defaultdict(
            list
        )

        for row in residual_rows:
            buckets[
                str(
                    row[
                        "hour_of_week"
                    ]
                )
            ].append(
                row[
                    "residual"
                ]
            )

        learned = {}

        for key, values in (
            buckets.items()
        ):
            bucket_median = (
                median(
                    values
                )
            )

            learned[key] = {
                "count":
                    len(values),

                "raw_median":
                    bucket_median,

                "value":
                    _shrink_value(
                        bucket_median,
                        global_residual,
                        len(values),
                        strength,
                    ),
            }

        return {
            "model_type":
                model_type,

            "strength":
                strength,

            "parameters": {
                "slope":
                    slope,

                "intercept":
                    intercept,

                "global_residual":
                    global_residual,

                "hour_of_week_residual":
                    learned,
            },
        }

    raise ValueError(
        "Onbekend model_type: "
        + str(
            model_type
        )
    )


def predict_row(
    model,
    row
):
    model_type = model.get(
        "model_type"
    )

    parameters = model.get(
        "parameters",
        {},
    )

    market = row[
        "market"
    ]

    if model_type == (
        "constant_margin"
    ):
        margin = safe_float(
            parameters.get(
                "global_margin"
            )
        )

        if margin is None:
            return None

        return (
            market
            + margin
        )

    if model_type == (
        "linear_market"
    ):
        slope = safe_float(
            parameters.get(
                "slope"
            )
        )

        intercept = safe_float(
            parameters.get(
                "intercept"
            )
        )

        if (
            slope is None
            or intercept is None
        ):
            return None

        return (
            intercept
            + slope
            * market
        )

    if model_type == (
        "hour_of_week_margin"
    ):
        global_margin = safe_float(
            parameters.get(
                "global_margin"
            )
        )

        buckets = parameters.get(
            "hour_of_week",
            {},
        )

        bucket = buckets.get(
            str(
                row[
                    "hour_of_week"
                ]
            ),
            {},
        )

        margin = safe_float(
            bucket.get(
                "value"
            )
        )

        if margin is None:
            margin = global_margin

        if margin is None:
            return None

        return (
            market
            + margin
        )

    if model_type == (
        "linear_hour_residual"
    ):
        slope = safe_float(
            parameters.get(
                "slope"
            )
        )

        intercept = safe_float(
            parameters.get(
                "intercept"
            )
        )

        global_residual = safe_float(
            parameters.get(
                "global_residual"
            )
        )

        if (
            slope is None
            or intercept is None
        ):
            return None

        if global_residual is None:
            global_residual = 0.0

        buckets = parameters.get(
            "hour_of_week_residual",
            {},
        )

        bucket = buckets.get(
            str(
                row[
                    "hour_of_week"
                ]
            ),
            {},
        )

        residual = safe_float(
            bucket.get(
                "value"
            )
        )

        if residual is None:
            residual = (
                global_residual
            )

        return (
            intercept
            + slope
            * market
            + residual
        )

    return None


def evaluate_model(
    model,
    rows
):
    predictions = []

    for row in rows:
        predictions.append(
            predict_row(
                model,
                row,
            )
        )

    return error_metrics(
        rows,
        predictions,
    )


def _split_rows(
    rows
):
    total = len(
        rows
    )

    train_end = int(
        total * 0.70
    )

    validation_end = int(
        total * 0.85
    )

    if train_end < 1:
        train_end = 1

    if validation_end <= train_end:
        validation_end = (
            train_end + 1
        )

    if validation_end >= total:
        validation_end = (
            total - 1
        )

    return {
        "train":
            rows[
                :train_end
            ],

        "validation":
            rows[
                train_end:
                validation_end
            ],

        "test":
            rows[
                validation_end:
            ],
    }


def _candidate_specs():
    specs = [
        {
            "model_type":
                "constant_margin",

            "strength":
                0,
        },
        {
            "model_type":
                "linear_market",

            "strength":
                0,
        },
    ]

    for strength in (
        SHRINKAGE_STRENGTHS
    ):
        specs.append(
            {
                "model_type":
                    "hour_of_week_margin",

                "strength":
                    strength,
            }
        )

        specs.append(
            {
                "model_type":
                    "linear_hour_residual",

                "strength":
                    strength,
            }
        )

    return specs


def _select_validation_models(
    train,
    validation,
):
    candidates = []

    best_per_family = {}

    for spec in (
        _candidate_specs()
    ):
        model = fit_model(
            train,
            spec[
                "model_type"
            ],
            spec[
                "strength"
            ],
        )

        metrics = (
            evaluate_model(
                model,
                validation,
            )
        )

        mae = safe_float(
            metrics.get(
                "mae_eur_kwh"
            )
        )

        result = {
            "model_type":
                spec[
                    "model_type"
                ],

            "strength":
                spec[
                    "strength"
                ],

            "validation":
                metrics,
        }

        candidates.append(
            result
        )

        if mae is None:
            continue

        previous = (
            best_per_family.get(
                spec[
                    "model_type"
                ]
            )
        )

        if previous is None:
            best_per_family[
                spec[
                    "model_type"
                ]
            ] = result

            continue

        previous_mae = safe_float(
            previous[
                "validation"
            ].get(
                "mae_eur_kwh"
            )
        )

        if (
            previous_mae is None
            or mae < previous_mae
        ):
            best_per_family[
                spec[
                    "model_type"
                ]
            ] = result

    valid_candidates = []

    for candidate in candidates:
        mae = safe_float(
            candidate[
                "validation"
            ].get(
                "mae_eur_kwh"
            )
        )

        if mae is not None:
            valid_candidates.append(
                candidate
            )

    if not valid_candidates:
        return {
            "best":
                None,

            "best_per_family":
                best_per_family,

            "candidates":
                candidates,
        }

    valid_candidates.sort(
        key=lambda item:
            item[
                "validation"
            ][
                "mae_eur_kwh"
            ]
    )

    return {
        "best":
            valid_candidates[0],

        "best_per_family":
            best_per_family,

        "candidates":
            candidates,
    }


def _audit_reference():
    audit = read_json(
        MARGIN_AUDIT_FILE,
        default={},
    )

    if not isinstance(
        audit,
        dict,
    ):
        return None

    baselines = audit.get(
        "chronological_baselines",
        {},
    )

    if not isinstance(
        baselines,
        dict,
    ):
        return None

    return safe_float(
        baselines.get(
            "best_mae_cent_kwh"
        )
    )


def _model_summary(
    model
):
    parameters = model.get(
        "parameters",
        {},
    )

    return {
        "model_type":
            model.get(
                "model_type"
            ),

        "strength":
            model.get(
                "strength"
            ),

        "slope":
            safe_float(
                parameters.get(
                    "slope"
                )
            ),

        "intercept_eur_kwh":
            safe_float(
                parameters.get(
                    "intercept"
                )
            ),

        "intercept_cent_kwh":
            (
                round(
                    safe_float(
                        parameters.get(
                            "intercept"
                        )
                    )
                    * 100,
                    5,
                )
                if safe_float(
                    parameters.get(
                        "intercept"
                    )
                )
                is not None
                else None
            ),

        "global_margin_eur_kwh":
            safe_float(
                parameters.get(
                    "global_margin"
                )
            ),

        "global_residual_eur_kwh":
            safe_float(
                parameters.get(
                    "global_residual"
                )
            ),
    }


def run_retail_learning():
    loaded = (
        load_training_rows()
    )

    rows = loaded[
        "rows"
    ]

    if len(rows) < (
        MIN_TOTAL_ROWS
    ):
        return {
            "status":
                "not_enough_data",

            "version":
                LEARNER_VERSION,

            "rows":
                len(rows),

            "required":
                MIN_TOTAL_ROWS,
        }

    signature = (
        dataset_signature(
            rows
        )
    )

    split = (
        _split_rows(
            rows
        )
    )

    train = split[
        "train"
    ]

    validation = split[
        "validation"
    ]

    test = split[
        "test"
    ]

    selection = (
        _select_validation_models(
            train,
            validation,
        )
    )

    best = selection.get(
        "best"
    )

    if best is None:
        return {
            "status":
                "selection_failed",

            "version":
                LEARNER_VERSION,
        }

    development = (
        train
        + validation
    )

    selected_model = fit_model(
        development,
        best[
            "model_type"
        ],
        best[
            "strength"
        ],
    )

    selected_test = (
        evaluate_model(
            selected_model,
            test,
        )
    )

    family_test_results = {}

    for (
        family,
        family_selection,
    ) in (
        selection[
            "best_per_family"
        ].items()
    ):
        model = fit_model(
            development,
            family,
            family_selection[
                "strength"
            ],
        )

        metrics = evaluate_model(
            model,
            test,
        )

        family_test_results[
            family
        ] = {
            "strength":
                family_selection[
                    "strength"
                ],

            "validation_mae_cent_kwh":
                family_selection[
                    "validation"
                ].get(
                    "mae_cent_kwh"
                ),

            "test":
                metrics,
        }

    constant_test = (
        family_test_results.get(
            "constant_margin",
            {},
        ).get(
            "test",
            {},
        )
    )

    constant_mae = safe_float(
        constant_test.get(
            "mae_eur_kwh"
        )
    )

    selected_mae = safe_float(
        selected_test.get(
            "mae_eur_kwh"
        )
    )

    gain_vs_constant = None

    if (
        constant_mae is not None
        and constant_mae > 0
        and selected_mae is not None
    ):
        gain_vs_constant = (
            (
                constant_mae
                - selected_mae
            )
            / constant_mae
            * 100
        )

    audit_reference = (
        _audit_reference()
    )

    beats_audit_reference = None

    if (
        audit_reference is not None
        and selected_test.get(
            "mae_cent_kwh"
        )
        is not None
    ):
        beats_audit_reference = (
            selected_test[
                "mae_cent_kwh"
            ]
            < audit_reference
        )

    production_model = fit_model(
        rows,
        best[
            "model_type"
        ],
        best[
            "strength"
        ],
    )

    production_model[
        "version"
    ] = LEARNER_VERSION

    production_model[
        "created_utc"
    ] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    production_model[
        "dataset_signature"
    ] = signature

    production_model[
        "trained_rows"
    ] = len(rows)

    production_model[
        "trained_from"
    ] = rows[0][
        "timestamp"
    ]

    production_model[
        "trained_through"
    ] = rows[-1][
        "timestamp"
    ]

    production_model[
        "holdout_evaluation"
    ] = selected_test

    production_model[
        "validation_mae_cent_kwh"
    ] = best[
        "validation"
    ].get(
        "mae_cent_kwh"
    )

    production_model[
        "audit_reference_mae_cent_kwh"
    ] = audit_reference

    existing_champion = read_json(
        CHAMPION_FILE,
        default={},
    )

    existing_signature = None

    if isinstance(
        existing_champion,
        dict,
    ):
        existing_signature = (
            existing_champion.get(
                "dataset_signature"
            )
        )

    champion_action = (
        "challenger_saved"
    )

    promote = False

    if not existing_signature:
        if (
            len(test)
            >= MIN_TEST_ROWS
            and selected_mae
            is not None
            and constant_mae
            is not None
            and selected_mae
            < constant_mae
        ):
            promote = True

            champion_action = (
                "first_champion_promoted"
            )

        else:
            champion_action = (
                "first_champion_rejected"
            )

    elif (
        existing_signature
        == signature
    ):
        champion_action = (
            "dataset_unchanged"
        )

    else:
        champion_action = (
            "new_challenger_waiting_for_forward_validation"
        )

    LEARNER_MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    LEARNER_ACCURACY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json_atomic(
        CHALLENGER_FILE,
        production_model,
    )

    if promote:
        write_json_atomic(
            CHAMPION_FILE,
            production_model,
        )

    report = {
        "version":
            LEARNER_VERSION,

        "status":
            "ok",

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "dataset": {
            "signature":
                signature,

            "eligible_unique_rows":
                len(rows),

            "first_timestamp":
                rows[0][
                    "timestamp"
                ],

            "last_timestamp":
                rows[-1][
                    "timestamp"
                ],

            "sources":
                loaded[
                    "source_counts"
                ],

            "unified_files":
                loaded[
                    "unified_files"
                ],

            "live_files":
                loaded[
                    "live_files"
                ],
        },

        "split": {
            "method":
                "chronological_70_15_15",

            "train_rows":
                len(train),

            "validation_rows":
                len(validation),

            "test_rows":
                len(test),

            "train_first":
                train[0][
                    "timestamp"
                ],

            "train_last":
                train[-1][
                    "timestamp"
                ],

            "validation_first":
                validation[0][
                    "timestamp"
                ],

            "validation_last":
                validation[-1][
                    "timestamp"
                ],

            "test_first":
                test[0][
                    "timestamp"
                ],

            "test_last":
                test[-1][
                    "timestamp"
                ],
        },

        "selected": {
            "model_type":
                best[
                    "model_type"
                ],

            "strength":
                best[
                    "strength"
                ],

            "validation":
                best[
                    "validation"
                ],

            "test":
                selected_test,

            "model_summary":
                _model_summary(
                    selected_model
                ),
        },

        "family_test_results":
            family_test_results,

        "gain_vs_constant_pct":
            (
                round(
                    gain_vs_constant,
                    3,
                )
                if gain_vs_constant
                is not None
                else None
            ),

        "audit_reference_mae_cent_kwh":
            audit_reference,

        "beats_audit_reference":
            beats_audit_reference,

        "champion_action":
            champion_action,

        "champion_file":
            str(
                CHAMPION_FILE
            ),

        "challenger_file":
            str(
                CHALLENGER_FILE
            ),

        "notes": [
            "Modelselectie gebeurt uitsluitend op de chronologische validatieset.",
            "De laatste 15 procent blijft onaangeroerde holdout-testdata.",
            "Na acceptatie wordt hetzelfde modeltype opnieuw op alle beschikbare historische data getraind voor toekomstig gebruik.",
            "Een bestaand champion-model wordt nog niet automatisch vervangen op data die het mogelijk al heeft gezien; daarvoor volgt forward validation.",
            "Werkelijk gemeten toekomstweer en Solcast worden niet als features gebruikt.",
        ],
    }

    write_json_atomic(
        REPORT_FILE,
        report,
    )

    return {
        "version":
            LEARNER_VERSION,

        "status":
            "ok",

        "rows":
            len(rows),

        "train_rows":
            len(train),

        "validation_rows":
            len(validation),

        "test_rows":
            len(test),

        "selected_model":
            best[
                "model_type"
            ],

        "selected_strength":
            best[
                "strength"
            ],

        "validation_mae_cent_kwh":
            best[
                "validation"
            ].get(
                "mae_cent_kwh"
            ),

        "test_mae_cent_kwh":
            selected_test.get(
                "mae_cent_kwh"
            ),

        "test_rmse_cent_kwh":
            selected_test.get(
                "rmse_cent_kwh"
            ),

        "test_bias_cent_kwh":
            selected_test.get(
                "bias_cent_kwh"
            ),

        "constant_test_mae_cent_kwh":
            constant_test.get(
                "mae_cent_kwh"
            ),

        "gain_vs_constant_pct":
            (
                round(
                    gain_vs_constant,
                    3,
                )
                if gain_vs_constant
                is not None
                else None
            ),

        "audit_reference_mae_cent_kwh":
            audit_reference,

        "beats_audit_reference":
            beats_audit_reference,

        "champion_action":
            champion_action,

        "model_summary":
            _model_summary(
                selected_model
            ),

        "source_counts":
            loaded[
                "source_counts"
            ],

        "champion_file":
            str(
                CHAMPION_FILE
            ),

        "challenger_file":
            str(
                CHALLENGER_FILE
            ),

        "report_file":
            str(
                REPORT_FILE
            ),
    }


def retail_learner_self_test():
    rows = []

    for index in range(
        2016
    ):
        hour_of_week = (
            index % 168
        )

        hour = (
            hour_of_week % 24
        )

        weekday = int(
            hour_of_week / 24
        )

        market = (
            -0.02
            + (
                (
                    index * 37
                )
                % 220
            )
            * 0.001
        )

        hour_effect = (
            (
                hour - 12
            )
            * 0.00025
        )

        weekend_effect = 0.0

        if weekday >= 5:
            weekend_effect = (
                0.0015
            )

        actual = (
            0.136
            + 1.158
            * market
            + hour_effect
            + weekend_effect
        )

        rows.append(
            {
                "timestamp":
                    str(index),

                "hour":
                    hour,

                "weekday":
                    weekday,

                "hour_of_week":
                    hour_of_week,

                "market":
                    market,

                "actual":
                    actual,

                "margin":
                    (
                        actual
                        - market
                    ),
            }
        )

    train = rows[
        :1344
    ]

    test = rows[
        1344:
    ]

    linear = fit_model(
        train,
        "linear_market",
        0,
    )

    residual = fit_model(
        train,
        "linear_hour_residual",
        8,
    )

    linear_metrics = (
        evaluate_model(
            linear,
            test,
        )
    )

    residual_metrics = (
        evaluate_model(
            residual,
            test,
        )
    )

    linear_mae = safe_float(
        linear_metrics.get(
            "mae_eur_kwh"
        )
    )

    residual_mae = safe_float(
        residual_metrics.get(
            "mae_eur_kwh"
        )
    )

    ok = (
        linear_mae is not None
        and residual_mae
        is not None
        and residual_mae
        < linear_mae
    )

    return {
        "status":
            (
                "ok"
                if ok
                else "error"
            ),

        "version":
            LEARNER_VERSION,

        "linear_mae_cent_kwh":
            linear_metrics.get(
                "mae_cent_kwh"
            ),

        "residual_mae_cent_kwh":
            residual_metrics.get(
                "mae_cent_kwh"
            ),

        "improved":
            ok,
    }
