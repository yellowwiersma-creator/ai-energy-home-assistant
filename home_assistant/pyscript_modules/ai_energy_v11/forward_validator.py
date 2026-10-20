from collections import defaultdict
from datetime import datetime, timezone
import math
import statistics

from .config import (
    ACCURACY_DIR,
    MODEL_DIR,
)

from .storage import (
    read_json,
    write_json_atomic,
)

from .retail_learner import (
    SHRINKAGE_STRENGTHS,
    load_training_rows,
    fit_model,
    evaluate_model,
)


FORWARD_VALIDATOR_VERSION = "11.4.3-forward-validator"

REPORT_FILE = (
    ACCURACY_DIR
    / "retail"
    / "forward_validation_latest.json"
)

CHAMPION_FILE = (
    MODEL_DIR
    / "retail"
    / "retail_champion.json"
)

MODEL_FAMILIES = (
    "constant_margin",
    "linear_market",
    "hour_of_week_margin",
    "linear_hour_residual",
)

DEFAULT_FOLDS = 6

MIN_INITIAL_TRAIN_ROWS = 1800

MIN_TEST_ROWS = 192

TUNING_FRACTION = 0.15


def safe_float(value):
    try:
        if value is None:
            return None

        number = float(value)

        if math.isnan(number):
            return None

        if math.isinf(number):
            return None

        return number

    except Exception:
        return None


def _mean(values):
    clean = [
        value
        for value in values
        if safe_float(value)
        is not None
    ]

    if not clean:
        return None

    return (
        sum(clean)
        / len(clean)
    )


def _median(values):
    clean = [
        value
        for value in values
        if safe_float(value)
        is not None
    ]

    if not clean:
        return None

    return statistics.median(
        clean
    )


def _std(values):
    clean = [
        value
        for value in values
        if safe_float(value)
        is not None
    ]

    if len(clean) < 2:
        return 0.0

    return statistics.pstdev(
        clean
    )


def _strengths_for_family(
    family
):
    if family in (
        "constant_margin",
        "linear_market",
    ):
        return [0]

    return list(
        SHRINKAGE_STRENGTHS
    )


def _tune_family(
    rows,
    family,
):
    total = len(rows)

    if total < 500:
        return {
            "strength": 0,
            "tuning_mae_cent_kwh": None,
        }

    tuning_rows = max(
        192,
        int(
            total
            * TUNING_FRACTION
        ),
    )

    if tuning_rows >= total:
        tuning_rows = max(
            1,
            int(
                total
                * 0.15
            ),
        )

    calibration_end = (
        total
        - tuning_rows
    )

    calibration = rows[
        :calibration_end
    ]

    tuning = rows[
        calibration_end:
    ]

    best_strength = None
    best_mae = None

    for strength in (
        _strengths_for_family(
            family
        )
    ):
        model = fit_model(
            calibration,
            family,
            strength,
        )

        metrics = evaluate_model(
            model,
            tuning,
        )

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
            best_strength = (
                strength
            )

    if best_strength is None:
        best_strength = 0

    return {
        "strength":
            best_strength,

        "tuning_rows":
            len(tuning),

        "tuning_mae_cent_kwh":
            (
                round(
                    best_mae
                    * 100,
                    5,
                )
                if best_mae
                is not None
                else None
            ),
    }


def _build_folds(
    rows,
    requested_folds,
):
    total = len(rows)

    try:
        fold_count = int(
            requested_folds
        )

    except Exception:
        fold_count = (
            DEFAULT_FOLDS
        )

    if fold_count < 3:
        fold_count = 3

    if fold_count > 10:
        fold_count = 10

    initial_train = max(
        MIN_INITIAL_TRAIN_ROWS,
        int(
            total
            * 0.45
        ),
    )

    remaining = (
        total
        - initial_train
    )

    max_possible_folds = int(
        remaining
        / MIN_TEST_ROWS
    )

    if max_possible_folds < 3:
        return []

    if fold_count > (
        max_possible_folds
    ):
        fold_count = (
            max_possible_folds
        )

    test_size = int(
        remaining
        / fold_count
    )

    folds = []

    for index in range(
        fold_count
    ):
        train_end = (
            initial_train
            + index
            * test_size
        )

        test_start = train_end

        if index == (
            fold_count - 1
        ):
            test_end = total

        else:
            test_end = (
                test_start
                + test_size
            )

        train = rows[
            :train_end
        ]

        test = rows[
            test_start:
            test_end
        ]

        if len(test) < (
            MIN_TEST_ROWS
        ):
            continue

        folds.append(
            {
                "fold":
                    index + 1,

                "train":
                    train,

                "test":
                    test,
            }
        )

    return folds


def _aggregate_family(
    family,
    fold_results,
):
    maes = []

    rmses = []

    biases = []

    strengths = []

    wins = 0

    beats_constant = 0

    valid_folds = 0

    for fold in fold_results:
        family_result = (
            fold[
                "models"
            ].get(
                family
            )
        )

        if not isinstance(
            family_result,
            dict,
        ):
            continue

        metrics = (
            family_result.get(
                "test",
                {},
            )
        )

        mae = safe_float(
            metrics.get(
                "mae_cent_kwh"
            )
        )

        rmse = safe_float(
            metrics.get(
                "rmse_cent_kwh"
            )
        )

        bias = safe_float(
            metrics.get(
                "bias_cent_kwh"
            )
        )

        if mae is None:
            continue

        valid_folds += 1

        maes.append(
            mae
        )

        if rmse is not None:
            rmses.append(
                rmse
            )

        if bias is not None:
            biases.append(
                bias
            )

        strength = (
            family_result.get(
                "strength"
            )
        )

        if strength is not None:
            strengths.append(
                strength
            )

        if (
            fold.get(
                "winner"
            )
            == family
        ):
            wins += 1

        constant_result = (
            fold[
                "models"
            ].get(
                "constant_margin",
                {},
            )
        )

        constant_mae = safe_float(
            constant_result.get(
                "test",
                {},
            ).get(
                "mae_cent_kwh"
            )
        )

        if (
            constant_mae is not None
            and mae < constant_mae
        ):
            beats_constant += 1

    if not maes:
        return {
            "model":
                family,

            "valid_folds":
                0,
        }

    return {
        "model":
            family,

        "valid_folds":
            valid_folds,

        "wins":
            wins,

        "beats_constant_folds":
            beats_constant,

        "mean_mae_cent_kwh":
            round(
                _mean(
                    maes
                ),
                5,
            ),

        "median_mae_cent_kwh":
            round(
                _median(
                    maes
                ),
                5,
            ),

        "best_mae_cent_kwh":
            round(
                min(maes),
                5,
            ),

        "worst_mae_cent_kwh":
            round(
                max(maes),
                5,
            ),

        "std_mae_cent_kwh":
            round(
                _std(
                    maes
                ),
                5,
            ),

        "mean_rmse_cent_kwh":
            (
                round(
                    _mean(
                        rmses
                    ),
                    5,
                )
                if rmses
                else None
            ),

        "mean_bias_cent_kwh":
            (
                round(
                    _mean(
                        biases
                    ),
                    5,
                )
                if biases
                else None
            ),

        "selected_strengths":
            strengths,
    }


def _run_validation_rows(
    rows,
    requested_folds=DEFAULT_FOLDS,
):
    folds = _build_folds(
        rows,
        requested_folds,
    )

    if not folds:
        return {
            "status":
                "not_enough_data",

            "rows":
                len(rows),

            "folds":
                0,
        }

    fold_results = []

    for fold in folds:
        train = fold[
            "train"
        ]

        test = fold[
            "test"
        ]

        models = {}

        best_family = None
        best_mae = None

        for family in (
            MODEL_FAMILIES
        ):
            tuning = (
                _tune_family(
                    train,
                    family,
                )
            )

            strength = (
                tuning.get(
                    "strength",
                    0,
                )
            )

            model = fit_model(
                train,
                family,
                strength,
            )

            metrics = (
                evaluate_model(
                    model,
                    test,
                )
            )

            mae = safe_float(
                metrics.get(
                    "mae_eur_kwh"
                )
            )

            models[
                family
            ] = {
                "strength":
                    strength,

                "tuning_mae_cent_kwh":
                    tuning.get(
                        "tuning_mae_cent_kwh"
                    ),

                "test":
                    metrics,
            }

            if mae is None:
                continue

            if (
                best_mae is None
                or mae < best_mae
            ):
                best_mae = mae
                best_family = family

        fold_results.append(
            {
                "fold":
                    fold[
                        "fold"
                    ],

                "train_rows":
                    len(train),

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

                "test_first":
                    test[0][
                        "timestamp"
                    ],

                "test_last":
                    test[-1][
                        "timestamp"
                    ],

                "winner":
                    best_family,

                "winner_mae_cent_kwh":
                    (
                        round(
                            best_mae
                            * 100,
                            5,
                        )
                        if best_mae
                        is not None
                        else None
                    ),

                "models":
                    models,
            }
        )

    aggregates = {}

    for family in (
        MODEL_FAMILIES
    ):
        aggregates[
            family
        ] = (
            _aggregate_family(
                family,
                fold_results,
            )
        )

    ranked = []

    for family, stats in (
        aggregates.items()
    ):
        mae = safe_float(
            stats.get(
                "mean_mae_cent_kwh"
            )
        )

        if mae is None:
            continue

        ranked.append(
            {
                "model":
                    family,

                "mean_mae":
                    mae,
            }
        )

    ranked.sort(
        key=lambda item:
            item[
                "mean_mae"
            ]
    )

    recommended = None
    runner_up = None

    if ranked:
        recommended = (
            ranked[0][
                "model"
            ]
        )

    if len(ranked) >= 2:
        runner_up = (
            ranked[1][
                "model"
            ]
        )

    constant_stats = (
        aggregates.get(
            "constant_margin",
            {},
        )
    )

    recommended_stats = (
        aggregates.get(
            recommended,
            {},
        )
        if recommended
        is not None
        else {}
    )

    constant_mean = safe_float(
        constant_stats.get(
            "mean_mae_cent_kwh"
        )
    )

    recommended_mean = (
        safe_float(
            recommended_stats.get(
                "mean_mae_cent_kwh"
            )
        )
    )

    gain_vs_constant = None

    if (
        constant_mean is not None
        and constant_mean > 0
        and recommended_mean
        is not None
    ):
        gain_vs_constant = (
            (
                constant_mean
                - recommended_mean
            )
            / constant_mean
            * 100
        )

    runner_mean = None

    if runner_up is not None:
        runner_mean = safe_float(
            aggregates[
                runner_up
            ].get(
                "mean_mae_cent_kwh"
            )
        )

    gain_vs_runner = None

    if (
        runner_mean is not None
        and runner_mean > 0
        and recommended_mean
        is not None
    ):
        gain_vs_runner = (
            (
                runner_mean
                - recommended_mean
            )
            / runner_mean
            * 100
        )

    validated = False

    if (
        recommended is not None
        and recommended
        != "constant_margin"
        and gain_vs_constant
        is not None
        and gain_vs_constant > 0
        and recommended_stats.get(
            "beats_constant_folds",
            0,
        )
        >= max(
            1,
            len(fold_results)
            - 1,
        )
    ):
        validated = True

    return {
        "status":
            "ok",

        "rows":
            len(rows),

        "folds":
            len(
                fold_results
            ),

        "fold_results":
            fold_results,

        "aggregates":
            aggregates,

        "recommended_model":
            recommended,

        "runner_up_model":
            runner_up,

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

        "gain_vs_runner_up_pct":
            (
                round(
                    gain_vs_runner,
                    3,
                )
                if gain_vs_runner
                is not None
                else None
            ),

        "forward_validated":
            validated,
    }


def run_forward_validation(
    folds=DEFAULT_FOLDS,
):
    loaded = (
        load_training_rows()
    )

    rows = loaded.get(
        "rows",
        [],
    )

    result = (
        _run_validation_rows(
            rows,
            folds,
        )
    )

    result[
        "version"
    ] = (
        FORWARD_VALIDATOR_VERSION
    )

    result[
        "created_utc"
    ] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    result[
        "source_counts"
    ] = loaded.get(
        "source_counts",
        {},
    )

    current_champion = (
        read_json(
            CHAMPION_FILE,
            default={},
        )
    )

    current_model = None

    if isinstance(
        current_champion,
        dict,
    ):
        current_model = (
            current_champion.get(
                "model_type"
            )
        )

    recommended = (
        result.get(
            "recommended_model"
        )
    )

    decision = (
        "no_recommendation"
    )

    if recommended is not None:
        if current_model is None:
            decision = (
                "recommend_initial_champion"
            )

        elif (
            recommended
            == current_model
        ):
            decision = (
                "keep_current_champion"
            )

        else:
            recommended_stats = (
                result.get(
                    "aggregates",
                    {},
                ).get(
                    recommended,
                    {},
                )
            )

            current_stats = (
                result.get(
                    "aggregates",
                    {},
                ).get(
                    current_model,
                    {},
                )
            )

            recommended_mae = (
                safe_float(
                    recommended_stats.get(
                        "mean_mae_cent_kwh"
                    )
                )
            )

            current_mae = (
                safe_float(
                    current_stats.get(
                        "mean_mae_cent_kwh"
                    )
                )
            )

            relative_gain = None

            if (
                recommended_mae
                is not None
                and current_mae
                is not None
                and current_mae > 0
            ):
                relative_gain = (
                    (
                        current_mae
                        - recommended_mae
                    )
                    / current_mae
                    * 100
                )

            if (
                relative_gain
                is not None
                and relative_gain
                >= 2.0
            ):
                decision = (
                    "recommend_champion_switch"
                )

            else:
                decision = (
                    "keep_current_champion"
                )

    result[
        "current_champion_model"
    ] = current_model

    result[
        "champion_decision"
    ] = decision

    REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json_atomic(
        REPORT_FILE,
        result,
    )

    return {
        "version":
            FORWARD_VALIDATOR_VERSION,

        "status":
            result.get(
                "status"
            ),

        "rows":
            result.get(
                "rows"
            ),

        "folds":
            result.get(
                "folds"
            ),

        "recommended_model":
            recommended,

        "runner_up_model":
            result.get(
                "runner_up_model"
            ),

        "gain_vs_constant_pct":
            result.get(
                "gain_vs_constant_pct"
            ),

        "gain_vs_runner_up_pct":
            result.get(
                "gain_vs_runner_up_pct"
            ),

        "forward_validated":
            result.get(
                "forward_validated"
            ),

        "current_champion_model":
            current_model,

        "champion_decision":
            decision,

        "aggregates":
            result.get(
                "aggregates"
            ),

        "report_file":
            str(
                REPORT_FILE
            ),
    }


def forward_validator_self_test():
    rows = []

    for index in range(
        5000
    ):
        how = (
            index % 168
        )

        hour = (
            how % 24
        )

        weekday = int(
            how / 24
        )

        market = (
            -0.02
            + (
                (
                    index * 31
                )
                % 250
            )
            * 0.001
        )

        hour_effect = (
            (
                hour - 12
            )
            * 0.00035
        )

        weekend = 0.0

        if weekday >= 5:
            weekend = 0.0015

        actual = (
            0.136
            + 1.16
            * market
            + hour_effect
            + weekend
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
                    how,

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

    result = (
        _run_validation_rows(
            rows,
            5,
        )
    )

    winner = result.get(
        "recommended_model"
    )

    ok = (
        result.get(
            "status"
        )
        == "ok"
        and winner
        == "linear_hour_residual"
    )

    return {
        "status":
            (
                "ok"
                if ok
                else "error"
            ),

        "version":
            FORWARD_VALIDATOR_VERSION,

        "folds":
            result.get(
                "folds"
            ),

        "recommended_model":
            winner,

        "gain_vs_constant_pct":
            result.get(
                "gain_vs_constant_pct"
            ),
    }
