from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import math
import statistics

from .config import (
    ACCURACY_DIR,
    LEGACY_NORMALIZED_DIR,
)

from .storage import (
    read_json,
    write_json_atomic,
)


MARGIN_AUDIT_VERSION = "11.4.1-margin-audit"

UNIFIED_DIR = (
    LEGACY_NORMALIZED_DIR
    / "unified"
)

AUDIT_DIR = (
    ACCURACY_DIR
    / "margin"
)

AUDIT_FILE = (
    AUDIT_DIR
    / "margin_audit_latest.json"
)


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


def percentile(
    values,
    percentage,
):
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

    clean.sort()

    if len(clean) == 1:
        return clean[0]

    p = float(
        percentage
    )

    if p <= 0:
        return clean[0]

    if p >= 100:
        return clean[-1]

    position = (
        (
            len(clean)
            - 1
        )
        * p
        / 100
    )

    lower_index = int(
        math.floor(
            position
        )
    )

    upper_index = int(
        math.ceil(
            position
        )
    )

    if lower_index == upper_index:
        return clean[
            lower_index
        ]

    fraction = (
        position
        - lower_index
    )

    lower_value = clean[
        lower_index
    ]

    upper_value = clean[
        upper_index
    ]

    return (
        lower_value
        + (
            upper_value
            - lower_value
        )
        * fraction
    )


def _distribution(
    values
):
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
        return {
            "count": 0,
        }

    mean_value = (
        sum(clean)
        / len(clean)
    )

    median_value = (
        statistics.median(
            clean
        )
    )

    std_value = 0.0

    if len(clean) > 1:
        std_value = (
            statistics.pstdev(
                clean
            )
        )

    return {
        "count":
            len(clean),

        "mean":
            round(
                mean_value,
                7,
            ),

        "median":
            round(
                median_value,
                7,
            ),

        "std":
            round(
                std_value,
                7,
            ),

        "min":
            round(
                min(clean),
                7,
            ),

        "p01":
            round(
                percentile(
                    clean,
                    1,
                ),
                7,
            ),

        "p05":
            round(
                percentile(
                    clean,
                    5,
                ),
                7,
            ),

        "p10":
            round(
                percentile(
                    clean,
                    10,
                ),
                7,
            ),

        "p25":
            round(
                percentile(
                    clean,
                    25,
                ),
                7,
            ),

        "p50":
            round(
                percentile(
                    clean,
                    50,
                ),
                7,
            ),

        "p75":
            round(
                percentile(
                    clean,
                    75,
                ),
                7,
            ),

        "p90":
            round(
                percentile(
                    clean,
                    90,
                ),
                7,
            ),

        "p95":
            round(
                percentile(
                    clean,
                    95,
                ),
                7,
            ),

        "p99":
            round(
                percentile(
                    clean,
                    99,
                ),
                7,
            ),

        "max":
            round(
                max(clean),
                7,
            ),
    }


def _error_metrics(
    actual,
    predicted,
):
    errors = []

    absolute_errors = []

    squared_errors = []

    count = min(
        len(actual),
        len(predicted),
    )

    for index in range(
        count
    ):
        y = safe_float(
            actual[index]
        )

        y_hat = safe_float(
            predicted[index]
        )

        if (
            y is None
            or y_hat is None
        ):
            continue

        error = (
            y_hat
            - y
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

    if not errors:
        return {
            "count": 0,
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
            len(errors),

        "mae_eur_kwh":
            round(
                mae,
                7,
            ),

        "mae_cent_kwh":
            round(
                mae * 100,
                4,
            ),

        "rmse_eur_kwh":
            round(
                rmse,
                7,
            ),

        "rmse_cent_kwh":
            round(
                rmse * 100,
                4,
            ),

        "bias_eur_kwh":
            round(
                bias,
                7,
            ),

        "bias_cent_kwh":
            round(
                bias * 100,
                4,
            ),

        "max_abs_error_eur_kwh":
            round(
                max(
                    absolute_errors
                ),
                7,
            ),

        "max_abs_error_cent_kwh":
            round(
                max(
                    absolute_errors
                )
                * 100,
                4,
            ),
    }


def _linear_fit(
    rows
):
    x_values = []
    y_values = []

    for row in rows:
        x = safe_float(
            row.get(
                "market_price"
            )
        )

        y = safe_float(
            row.get(
                "zonneplan_price"
            )
        )

        if (
            x is None
            or y is None
        ):
            continue

        x_values.append(
            x
        )

        y_values.append(
            y
        )

    count = len(
        x_values
    )

    if count < 2:
        return {
            "count":
                count,

            "slope":
                None,

            "intercept":
                None,

            "r_squared":
                None,
        }

    mean_x = (
        sum(x_values)
        / count
    )

    mean_y = (
        sum(y_values)
        / count
    )

    numerator = 0.0
    denominator = 0.0

    for index in range(
        count
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
            "count":
                count,

            "slope":
                None,

            "intercept":
                round(
                    mean_y,
                    7,
                ),

            "r_squared":
                None,
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

    predictions = []

    for x in x_values:
        predictions.append(
            intercept
            + slope
            * x
        )

    total_sum_squares = 0.0
    residual_sum_squares = 0.0

    for index in range(
        count
    ):
        total_sum_squares += (
            y_values[index]
            - mean_y
        ) ** 2

        residual_sum_squares += (
            y_values[index]
            - predictions[index]
        ) ** 2

    r_squared = None

    if total_sum_squares > 0:
        r_squared = (
            1
            - (
                residual_sum_squares
                / total_sum_squares
            )
        )

    metrics = (
        _error_metrics(
            y_values,
            predictions,
        )
    )

    return {
        "count":
            count,

        "slope":
            round(
                slope,
                8,
            ),

        "intercept_eur_kwh":
            round(
                intercept,
                8,
            ),

        "intercept_cent_kwh":
            round(
                intercept * 100,
                5,
            ),

        "slope_minus_one":
            round(
                slope - 1,
                8,
            ),

        "r_squared":
            (
                round(
                    r_squared,
                    8,
                )
                if r_squared
                is not None
                else None
            ),

        "fit_error":
            metrics,
    }


def _group_distribution(
    rows,
    field,
):
    groups = defaultdict(
        list
    )

    for row in rows:
        key = row.get(
            field
        )

        margin = safe_float(
            row.get(
                "margin"
            )
        )

        if margin is None:
            continue

        groups[
            str(key)
        ].append(
            margin
        )

    result = {}

    for key in sorted(
        groups.keys()
    ):
        stats = _distribution(
            groups[key]
        )

        result[key] = {
            "count":
                stats.get(
                    "count"
                ),

            "mean_eur_kwh":
                stats.get(
                    "mean"
                ),

            "median_eur_kwh":
                stats.get(
                    "median"
                ),

            "median_cent_kwh":
                (
                    round(
                        stats.get(
                            "median"
                        )
                        * 100,
                        4,
                    )
                    if stats.get(
                        "median"
                    )
                    is not None
                    else None
                ),

            "p05_eur_kwh":
                stats.get(
                    "p05"
                ),

            "p95_eur_kwh":
                stats.get(
                    "p95"
                ),
        }

    return result


def _read_unified_rows():
    files = []

    if UNIFIED_DIR.exists():
        files = sorted(
            UNIFIED_DIR.rglob(
                "*.json"
            )
        )

    rows = []

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

        for row in payload:
            if isinstance(
                row,
                dict,
            ):
                rows.append(
                    row
                )

    rows.sort(
        key=lambda row:
            str(
                row.get(
                    "slot_start_utc",
                    row.get(
                        "timestamp",
                        "",
                    ),
                )
            )
    )

    return (
        files,
        rows,
    )


def _prepare_rows(
    unified_rows
):
    prepared = []

    excluded = {
        "missing_zonneplan":
            0,

        "missing_market":
            0,

        "learning_flag_false":
            0,

        "invalid_margin":
            0,
    }

    for row in unified_rows:
        zonneplan = safe_float(
            row.get(
                "zonneplan_actual_eur_kwh"
            )
        )

        market = safe_float(
            row.get(
                "market_price_eur_kwh"
            )
        )

        learning = row.get(
            "learning",
            {},
        )

        margin_allowed = False

        if isinstance(
            learning,
            dict,
        ):
            margin_allowed = (
                learning.get(
                    "margin"
                )
                is True
            )

        if zonneplan is None:
            excluded[
                "missing_zonneplan"
            ] += 1

            continue

        if market is None:
            excluded[
                "missing_market"
            ] += 1

            continue

        if not margin_allowed:
            excluded[
                "learning_flag_false"
            ] += 1

            continue

        margin = (
            zonneplan
            - market
        )

        if (
            math.isnan(margin)
            or math.isinf(margin)
        ):
            excluded[
                "invalid_margin"
            ] += 1

            continue

        timestamp = (
            row.get(
                "slot_start_utc"
            )
            or row.get(
                "timestamp"
            )
        )

        prepared.append(
            {
                "timestamp":
                    timestamp,

                "delivery_date":
                    row.get(
                        "delivery_date"
                    ),

                "month":
                    str(
                        row.get(
                            "delivery_date",
                            "",
                        )
                    )[0:7],

                "hour":
                    row.get(
                        "local_hour"
                    ),

                "weekday":
                    row.get(
                        "local_weekday"
                    ),

                "hour_of_week":
                    (
                        int(
                            row.get(
                                "local_weekday"
                            )
                        )
                        * 24
                        + int(
                            row.get(
                                "local_hour"
                            )
                        )
                        if (
                            row.get(
                                "local_weekday"
                            )
                            is not None
                            and row.get(
                                "local_hour"
                            )
                            is not None
                        )
                        else None
                    ),

                "market_source":
                    row.get(
                        "market_source"
                    ),

                "market_quality":
                    safe_float(
                        row.get(
                            "market_quality"
                        )
                    ),

                "market_price":
                    market,

                "zonneplan_price":
                    zonneplan,

                "margin":
                    margin,
            }
        )

    prepared.sort(
        key=lambda row:
            str(
                row.get(
                    "timestamp",
                    "",
                )
            )
    )

    return (
        prepared,
        excluded,
    )


def _outlier_audit(
    rows
):
    margins = []

    for row in rows:
        margin = safe_float(
            row.get(
                "margin"
            )
        )

        if margin is not None:
            margins.append(
                margin
            )

    if len(margins) < 4:
        return {
            "count": 0,
        }

    median_margin = (
        statistics.median(
            margins
        )
    )

    q1 = percentile(
        margins,
        25,
    )

    q3 = percentile(
        margins,
        75,
    )

    iqr = (
        q3
        - q1
    )

    iqr_low = (
        q1
        - 3
        * iqr
    )

    iqr_high = (
        q3
        + 3
        * iqr
    )

    absolute_deviations = []

    for value in margins:
        absolute_deviations.append(
            abs(
                value
                - median_margin
            )
        )

    mad = (
        statistics.median(
            absolute_deviations
        )
    )

    candidates = []

    for row in rows:
        margin = row[
            "margin"
        ]

        iqr_flag = (
            margin < iqr_low
            or margin > iqr_high
        )

        robust_z = None
        mad_flag = False

        if mad > 0:
            robust_z = (
                0.6745
                * (
                    margin
                    - median_margin
                )
                / mad
            )

            mad_flag = (
                abs(
                    robust_z
                )
                > 6
            )

        if (
            iqr_flag
            or mad_flag
        ):
            candidates.append(
                {
                    "timestamp":
                        row.get(
                            "timestamp"
                        ),

                    "market_price_eur_kwh":
                        round(
                            row[
                                "market_price"
                            ],
                            7,
                        ),

                    "zonneplan_price_eur_kwh":
                        round(
                            row[
                                "zonneplan_price"
                            ],
                            7,
                        ),

                    "margin_eur_kwh":
                        round(
                            margin,
                            7,
                        ),

                    "margin_cent_kwh":
                        round(
                            margin
                            * 100,
                            4,
                        ),

                    "market_source":
                        row.get(
                            "market_source"
                        ),

                    "iqr_flag":
                        iqr_flag,

                    "robust_z":
                        (
                            round(
                                robust_z,
                                3,
                            )
                            if robust_z
                            is not None
                            else None
                        ),
                }
            )

    candidates.sort(
        key=lambda row:
            abs(
                row[
                    "margin_eur_kwh"
                ]
                - median_margin
            ),
        reverse=True,
    )

    return {
        "count":
            len(
                candidates
            ),

        "median_eur_kwh":
            round(
                median_margin,
                7,
            ),

        "mad_eur_kwh":
            round(
                mad,
                7,
            ),

        "q1_eur_kwh":
            round(
                q1,
                7,
            ),

        "q3_eur_kwh":
            round(
                q3,
                7,
            ),

        "iqr_eur_kwh":
            round(
                iqr,
                7,
            ),

        "extreme_iqr_low_eur_kwh":
            round(
                iqr_low,
                7,
            ),

        "extreme_iqr_high_eur_kwh":
            round(
                iqr_high,
                7,
            ),

        "top_candidates":
            candidates[
                0:25
            ],
    }


def _median_map(
    rows,
    key_field,
):
    buckets = defaultdict(
        list
    )

    for row in rows:
        key = row.get(
            key_field
        )

        margin = row.get(
            "margin"
        )

        if (
            key is not None
            and margin is not None
        ):
            buckets[
                str(key)
            ].append(
                margin
            )

    medians = {}

    for key, values in (
        buckets.items()
    ):
        if values:
            medians[key] = (
                statistics.median(
                    values
                )
            )

    return medians


def _chronological_baselines(
    rows
):
    count = len(
        rows
    )

    if count < 100:
        return {
            "status":
                "not_enough_data",

            "rows":
                count,
        }

    split_index = int(
        count
        * 0.80
    )

    if split_index < 1:
        split_index = 1

    if split_index >= count:
        split_index = (
            count
            - 1
        )

    train = rows[
        :split_index
    ]

    test = rows[
        split_index:
    ]

    train_margins = [
        row["margin"]
        for row in train
    ]

    global_median_margin = (
        statistics.median(
            train_margins
        )
    )

    actual = []

    constant_predictions = []

    for row in test:
        actual.append(
            row[
                "zonneplan_price"
            ]
        )

        constant_predictions.append(
            row[
                "market_price"
            ]
            + global_median_margin
        )

    constant_metrics = (
        _error_metrics(
            actual,
            constant_predictions,
        )
    )

    linear_model = (
        _linear_fit(
            train
        )
    )

    linear_predictions = []

    slope = linear_model.get(
        "slope"
    )

    intercept = linear_model.get(
        "intercept_eur_kwh"
    )

    for row in test:
        if (
            slope is None
            or intercept is None
        ):
            linear_predictions.append(
                None
            )

        else:
            linear_predictions.append(
                intercept
                + slope
                * row[
                    "market_price"
                ]
            )

    linear_metrics = (
        _error_metrics(
            actual,
            linear_predictions,
        )
    )

    hour_medians = (
        _median_map(
            train,
            "hour",
        )
    )

    hour_predictions = []

    for row in test:
        key = str(
            row.get(
                "hour"
            )
        )

        margin = (
            hour_medians.get(
                key,
                global_median_margin,
            )
        )

        hour_predictions.append(
            row[
                "market_price"
            ]
            + margin
        )

    hour_metrics = (
        _error_metrics(
            actual,
            hour_predictions,
        )
    )

    hour_week_medians = (
        _median_map(
            train,
            "hour_of_week",
        )
    )

    hour_week_predictions = []

    for row in test:
        key = str(
            row.get(
                "hour_of_week"
            )
        )

        margin = (
            hour_week_medians.get(
                key
            )
        )

        if margin is None:
            hour_key = str(
                row.get(
                    "hour"
                )
            )

            margin = (
                hour_medians.get(
                    hour_key,
                    global_median_margin,
                )
            )

        hour_week_predictions.append(
            row[
                "market_price"
            ]
            + margin
        )

    hour_week_metrics = (
        _error_metrics(
            actual,
            hour_week_predictions,
        )
    )

    candidates = {
        "constant_margin":
            constant_metrics,

        "linear_market":
            linear_metrics,

        "hour_margin":
            hour_metrics,

        "hour_of_week_margin":
            hour_week_metrics,
    }

    best_name = None
    best_mae = None

    for name, metrics in (
        candidates.items()
    ):
        mae = safe_float(
            metrics.get(
                "mae_eur_kwh"
            )
        )

        if mae is None:
            continue

        if (
            best_mae is None
            or mae < best_mae
        ):
            best_mae = mae
            best_name = name

    improvement = None

    baseline_mae = (
        safe_float(
            constant_metrics.get(
                "mae_eur_kwh"
            )
        )
    )

    if (
        baseline_mae is not None
        and baseline_mae > 0
        and best_mae is not None
    ):
        improvement = (
            (
                baseline_mae
                - best_mae
            )
            / baseline_mae
            * 100
        )

    return {
        "status":
            "ok",

        "split":
            "chronological_80_20",

        "train_rows":
            len(train),

        "test_rows":
            len(test),

        "train_first":
            train[0].get(
                "timestamp"
            ),

        "train_last":
            train[-1].get(
                "timestamp"
            ),

        "test_first":
            test[0].get(
                "timestamp"
            ),

        "test_last":
            test[-1].get(
                "timestamp"
            ),

        "global_train_median_margin_eur_kwh":
            round(
                global_median_margin,
                7,
            ),

        "constant_margin":
            constant_metrics,

        "linear_market":
            {
                "model":
                    linear_model,

                "test_error":
                    linear_metrics,
            },

        "hour_margin":
            hour_metrics,

        "hour_of_week_margin":
            hour_week_metrics,

        "best_baseline":
            best_name,

        "best_mae_cent_kwh":
            (
                round(
                    best_mae
                    * 100,
                    4,
                )
                if best_mae
                is not None
                else None
            ),

        "improvement_vs_constant_pct":
            (
                round(
                    improvement,
                    2,
                )
                if improvement
                is not None
                else None
            ),
    }


def _price_band(
    price
):
    value = safe_float(
        price
    )

    if value is None:
        return "missing"

    if value < 0:
        return "negative"

    if value < 0.05:
        return "0_to_5ct"

    if value < 0.10:
        return "5_to_10ct"

    if value < 0.15:
        return "10_to_15ct"

    if value < 0.20:
        return "15_to_20ct"

    if value < 0.30:
        return "20_to_30ct"

    return "30ct_plus"


def _market_price_band_stats(
    rows
):
    groups = defaultdict(
        list
    )

    for row in rows:
        band = _price_band(
            row.get(
                "market_price"
            )
        )

        groups[
            band
        ].append(
            row.get(
                "margin"
            )
        )

    result = {}

    for band in (
        "negative",
        "0_to_5ct",
        "5_to_10ct",
        "10_to_15ct",
        "15_to_20ct",
        "20_to_30ct",
        "30ct_plus",
    ):
        values = groups.get(
            band,
            [],
        )

        stats = _distribution(
            values
        )

        result[
            band
        ] = {
            "count":
                stats.get(
                    "count",
                    0,
                ),

            "median_margin_eur_kwh":
                stats.get(
                    "median"
                ),

            "median_margin_cent_kwh":
                (
                    round(
                        stats.get(
                            "median"
                        )
                        * 100,
                        4,
                    )
                    if stats.get(
                        "median"
                    )
                    is not None
                    else None
                ),

            "mean_margin_eur_kwh":
                stats.get(
                    "mean"
                ),
        }

    return result


def _interpretation(
    distribution,
    linear_fit,
    baselines,
    by_month,
):
    observations = []

    slope = safe_float(
        linear_fit.get(
            "slope"
        )
    )

    r_squared = safe_float(
        linear_fit.get(
            "r_squared"
        )
    )

    if (
        slope is not None
        and r_squared is not None
    ):
        if (
            r_squared >= 0.98
            and abs(
                slope - 1
            ) <= 0.02
        ):
            observations.append(
                "Retailprijs volgt vrijwel één-op-één de marktprijs met hoofdzakelijk een vaste opslag."
            )

        elif r_squared >= 0.98:
            observations.append(
                "Retailprijs heeft een zeer sterke lineaire relatie met de marktprijs; de opslag is dus waarschijnlijk niet volledig constant."
            )

        elif r_squared >= 0.90:
            observations.append(
                "Retailprijs hangt sterk samen met de marktprijs, maar er zijn aanvullende tijd- of tariefcomponenten zichtbaar."
            )

        else:
            observations.append(
                "Een eenvoudige lineaire marktformule verklaart de retailprijs niet volledig."
            )

    month_medians = []

    for value in by_month.values():
        median_value = safe_float(
            value.get(
                "median_eur_kwh"
            )
        )

        if median_value is not None:
            month_medians.append(
                median_value
            )

    if len(month_medians) >= 2:
        month_range = (
            max(month_medians)
            - min(month_medians)
        )

        if month_range >= 0.01:
            observations.append(
                "De mediane retailopslag verschilt meer dan 1 cent/kWh tussen maanden; een tariefregime of tijdseffect verdient aparte modellering."
            )

        else:
            observations.append(
                "De mediane retailopslag is tussen maanden relatief stabiel."
            )

    baseline_name = (
        baselines.get(
            "best_baseline"
        )
    )

    if baseline_name is not None:
        observations.append(
            "Beste eenvoudige out-of-sample baseline: "
            + str(
                baseline_name
            )
            + "."
        )

    median_margin = safe_float(
        distribution.get(
            "median"
        )
    )

    if median_margin is not None:
        observations.append(
            "Historische mediane opslag: "
            + str(
                round(
                    median_margin
                    * 100,
                    4,
                )
            )
            + " cent/kWh."
        )

    return observations


def run_margin_audit():
    (
        unified_files,
        unified_rows,
    ) = _read_unified_rows()

    (
        rows,
        excluded,
    ) = _prepare_rows(
        unified_rows
    )

    margins = [
        row["margin"]
        for row in rows
    ]

    margin_distribution = (
        _distribution(
            margins
        )
    )

    full_linear_fit = (
        _linear_fit(
            rows
        )
    )

    by_month = (
        _group_distribution(
            rows,
            "month",
        )
    )

    by_hour = (
        _group_distribution(
            rows,
            "hour",
        )
    )

    by_weekday = (
        _group_distribution(
            rows,
            "weekday",
        )
    )

    by_market_source = (
        _group_distribution(
            rows,
            "market_source",
        )
    )

    price_bands = (
        _market_price_band_stats(
            rows
        )
    )

    outliers = (
        _outlier_audit(
            rows
        )
    )

    baselines = (
        _chronological_baselines(
            rows
        )
    )

    interpretation = (
        _interpretation(
            margin_distribution,
            full_linear_fit,
            baselines,
            by_month,
        )
    )

    source_counts = defaultdict(
        int
    )

    for row in rows:
        source_counts[
            str(
                row.get(
                    "market_source"
                )
            )
        ] += 1

    report = {
        "version":
            MARGIN_AUDIT_VERSION,

        "status":
            (
                "ok"
                if len(rows) > 0
                else "no_data"
            ),

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source":
            "V11 unified historical timeline",

        "unified_files":
            len(
                unified_files
            ),

        "unified_rows":
            len(
                unified_rows
            ),

        "eligible_rows":
            len(
                rows
            ),

        "excluded_rows":
            (
                len(
                    unified_rows
                )
                - len(rows)
            ),

        "excluded_reasons":
            excluded,

        "first_timestamp":
            (
                rows[0].get(
                    "timestamp"
                )
                if rows
                else None
            ),

        "last_timestamp":
            (
                rows[-1].get(
                    "timestamp"
                )
                if rows
                else None
            ),

        "market_sources":
            dict(
                sorted(
                    source_counts.items()
                )
            ),

        "margin_distribution_eur_kwh":
            margin_distribution,

        "margin_distribution_cent_kwh":
            {
                key:
                    (
                        round(
                            value
                            * 100,
                            4,
                        )
                        if (
                            key != "count"
                            and isinstance(
                                value,
                                (
                                    int,
                                    float,
                                ),
                            )
                        )
                        else value
                    )

                for key, value in (
                    margin_distribution
                    .items()
                )
            },

        "linear_retail_relationship":
            full_linear_fit,

        "by_month":
            by_month,

        "by_hour":
            by_hour,

        "by_weekday":
            by_weekday,

        "by_market_source":
            by_market_source,

        "by_market_price_band":
            price_bands,

        "outlier_audit":
            outliers,

        "chronological_baselines":
            baselines,

        "interpretation":
            interpretation,

        "notes": [
            "Outlier candidates worden alleen gerapporteerd en niet automatisch uit trainingsdata verwijderd.",
            "Chronologische baseline gebruikt de eerste 80 procent voor calibratie en de laatste 20 procent uitsluitend voor test.",
            "Werkelijk gemeten weer wordt in deze audit niet gebruikt als voorspellende feature.",
            "Dit rapport bouwt nog geen productiemodel en wijzigt geen historische brondata.",
        ],
    }

    AUDIT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json_atomic(
        AUDIT_FILE,
        report,
    )

    summary = {
        "version":
            MARGIN_AUDIT_VERSION,

        "status":
            report.get(
                "status"
            ),

        "unified_rows":
            report.get(
                "unified_rows"
            ),

        "eligible_rows":
            report.get(
                "eligible_rows"
            ),

        "excluded_rows":
            report.get(
                "excluded_rows"
            ),

        "first_timestamp":
            report.get(
                "first_timestamp"
            ),

        "last_timestamp":
            report.get(
                "last_timestamp"
            ),

        "median_margin_eur_kwh":
            margin_distribution.get(
                "median"
            ),

        "median_margin_cent_kwh":
            (
                round(
                    margin_distribution.get(
                        "median"
                    )
                    * 100,
                    4,
                )
                if margin_distribution.get(
                    "median"
                )
                is not None
                else None
            ),

        "mean_margin_cent_kwh":
            (
                round(
                    margin_distribution.get(
                        "mean"
                    )
                    * 100,
                    4,
                )
                if margin_distribution.get(
                    "mean"
                )
                is not None
                else None
            ),

        "p05_margin_cent_kwh":
            (
                round(
                    margin_distribution.get(
                        "p05"
                    )
                    * 100,
                    4,
                )
                if margin_distribution.get(
                    "p05"
                )
                is not None
                else None
            ),

        "p95_margin_cent_kwh":
            (
                round(
                    margin_distribution.get(
                        "p95"
                    )
                    * 100,
                    4,
                )
                if margin_distribution.get(
                    "p95"
                )
                is not None
                else None
            ),

        "linear_slope":
            full_linear_fit.get(
                "slope"
            ),

        "linear_intercept_cent_kwh":
            full_linear_fit.get(
                "intercept_cent_kwh"
            ),

        "linear_r_squared":
            full_linear_fit.get(
                "r_squared"
            ),

        "outlier_candidates":
            outliers.get(
                "count"
            ),

        "baseline":
            baselines.get(
                "best_baseline"
            ),

        "baseline_mae_cent_kwh":
            baselines.get(
                "best_mae_cent_kwh"
            ),

        "baseline_improvement_pct":
            baselines.get(
                "improvement_vs_constant_pct"
            ),

        "report_file":
            str(
                AUDIT_FILE
            ),

        "interpretation":
            interpretation,
    }

    return summary


def margin_audit_self_test():
    rows = []

    for index in range(
        100
    ):
        market = (
            -0.02
            + index
            * 0.002
        )

        zonneplan = (
            0.13
            + 1.20
            * market
        )

        rows.append(
            {
                "market_price":
                    market,

                "zonneplan_price":
                    zonneplan,

                "margin":
                    (
                        zonneplan
                        - market
                    ),

                "hour":
                    index % 24,

                "hour_of_week":
                    index % 168,

                "timestamp":
                    str(index),
            }
        )

    model = _linear_fit(
        rows
    )

    ok = (
        abs(
            model.get(
                "slope",
                0,
            )
            - 1.20
        )
        < 0.000001
        and abs(
            model.get(
                "intercept_eur_kwh",
                0,
            )
            - 0.13
        )
        < 0.000001
        and model.get(
            "r_squared",
            0,
        )
        > 0.999999
    )

    return {
        "status":
            (
                "ok"
                if ok
                else "error"
            ),

        "version":
            MARGIN_AUDIT_VERSION,

        "slope":
            model.get(
                "slope"
            ),

        "intercept":
            model.get(
                "intercept_eur_kwh"
            ),

        "r_squared":
            model.get(
                "r_squared"
            ),
    }
