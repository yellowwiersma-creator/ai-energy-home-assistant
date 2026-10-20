from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    ACCURACY_DIR,
    MODEL_DIR,
)

from .storage import (
    read_json,
    write_json_atomic,
)

from .retail_learner import (
    load_training_rows,
    fit_model,
    dataset_signature,
)

from .forward_validator import (
    run_forward_validation,
)


GOVERNOR_VERSION = "11.5.6a-strength-selection-fix"

RETAIL_MODEL_DIR = (
    MODEL_DIR
    / "retail"
)

CHAMPION_FILE = (
    RETAIL_MODEL_DIR
    / "retail_champion.json"
)

GOVERNOR_CHALLENGER_FILE = (
    RETAIL_MODEL_DIR
    / "governor_challenger.json"
)

CHAMPION_ARCHIVE_DIR = (
    RETAIL_MODEL_DIR
    / "archive"
)

GOVERNOR_REPORT_FILE = (
    ACCURACY_DIR
    / "retail"
    / "governor_latest.json"
)

MIN_NEW_ROWS_FOR_REFRESH = 96


def safe_float(value):
    try:
        if value is None:
            return None

        return float(value)

    except Exception:
        return None


def safe_int(value):
    try:
        if value is None:
            return None

        return int(value)

    except Exception:
        return None


def _aggregate_mode_strength(
    aggregate,
):
    """
    Fallback only.

    Selecteer de meest voorkomende strength uit alle folds.
    Dit wordt NIET meer als primaire productiekeuze gebruikt.
    """

    if not isinstance(
        aggregate,
        dict,
    ):
        return None

    values = aggregate.get(
        "selected_strengths",
        [],
    )

    if not isinstance(
        values,
        list,
    ):
        return None

    counts = defaultdict(
        int
    )

    last_seen_index = {}

    for index, value in enumerate(
        values
    ):
        try:
            number = int(
                value
            )

        except Exception:
            continue

        counts[
            number
        ] += 1

        last_seen_index[
            number
        ] = index

    if not counts:
        return None

    ranked = []

    for (
        strength,
        count,
    ) in counts.items():
        ranked.append(
            {
                "strength":
                    strength,

                "count":
                    count,

                "last_seen":
                    last_seen_index.get(
                        strength,
                        -1,
                    ),
            }
        )

    # Eerst meeste voorkomens.
    # Bij gelijke stand krijgt de meest recente fold voorrang.
    ranked.sort(
        key=lambda item: (
            -item[
                "count"
            ],
            -item[
                "last_seen"
            ],
        )
    )

    return ranked[0][
        "strength"
    ]


def _latest_fold_strength(
    validation,
    model_type,
):
    """
    Gebruik bij voorkeur de strength uit de meest recente
    expanding-window fold.

    Die fold:
    - gebruikt de grootste historische trainingsset;
    - ligt temporeel het dichtst bij productie;
    - heeft de hyperparameter zonder toekomstige leakage gekozen.
    """

    if not isinstance(
        validation,
        dict,
    ):
        return None

    folds = validation.get(
        "fold_results",
        [],
    )

    if not isinstance(
        folds,
        list,
    ):
        return None

    valid = []

    for fold in folds:
        if not isinstance(
            fold,
            dict,
        ):
            continue

        fold_number = safe_int(
            fold.get(
                "fold"
            )
        )

        models = fold.get(
            "models",
            {},
        )

        if not isinstance(
            models,
            dict,
        ):
            continue

        model = models.get(
            model_type,
            {},
        )

        if not isinstance(
            model,
            dict,
        ):
            continue

        strength = safe_int(
            model.get(
                "strength"
            )
        )

        if strength is None:
            continue

        valid.append(
            {
                "fold":
                    (
                        fold_number
                        if fold_number
                        is not None
                        else 0
                    ),

                "strength":
                    strength,
            }
        )

    if not valid:
        return None

    valid.sort(
        key=lambda item:
            item[
                "fold"
            ]
    )

    return valid[-1][
        "strength"
    ]


def _recommended_strength(
    validation,
    model_type,
    current_champion,
):
    """
    Productieselectie voor strength.

    Prioriteit:
    1. meest recente forward-validation fold;
    2. bestaande champion strength wanneer hetzelfde model draait;
    3. aggregate mode als fallback;
    4. uiteindelijk 0.
    """

    latest = (
        _latest_fold_strength(
            validation,
            model_type,
        )
    )

    if latest is not None:
        return {
            "strength":
                latest,

            "source":
                "latest_forward_fold",
        }

    if isinstance(
        current_champion,
        dict,
    ):
        current_model = (
            current_champion.get(
                "model_type"
            )
        )

        current_strength = safe_int(
            current_champion.get(
                "strength"
            )
        )

        if (
            current_model
            == model_type
            and current_strength
            is not None
        ):
            return {
                "strength":
                    current_strength,

                "source":
                    "current_champion",
            }

    aggregates = validation.get(
        "aggregates",
        {},
    )

    if isinstance(
        aggregates,
        dict,
    ):
        aggregate = aggregates.get(
            model_type,
            {},
        )

        fallback = (
            _aggregate_mode_strength(
                aggregate
            )
        )

        if fallback is not None:
            return {
                "strength":
                    fallback,

                "source":
                    "aggregate_mode_fallback",
            }

    return {
        "strength":
            0,

        "source":
            "default_zero",
    }


def _archive_champion(
    champion,
):
    if not isinstance(
        champion,
        dict,
    ):
        return None

    if not champion:
        return None

    CHAMPION_ARCHIVE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    now = datetime.now(
        timezone.utc
    )

    filename = (
        now.strftime(
            "%Y%m%d_%H%M%S"
        )
        + "_"
        + str(
            champion.get(
                "model_type",
                "unknown",
            )
        )
        + ".json"
    )

    path = (
        CHAMPION_ARCHIVE_DIR
        / filename
    )

    write_json_atomic(
        path,
        champion,
    )

    return str(
        path
    )


def _promotion_policy(
    current_model,
    recommended_model,
    forward_validated,
    validator_decision,
    new_rows,
):
    if recommended_model is None:
        return {
            "action":
                "keep",

            "reason":
                "no_recommended_model",
        }

    if not forward_validated:
        return {
            "action":
                "keep",

            "reason":
                "candidate_not_forward_validated",
        }

    if recommended_model == (
        "constant_margin"
    ):
        return {
            "action":
                "keep",

            "reason":
                "constant_margin_not_allowed_as_production_champion",
        }

    if current_model is None:
        return {
            "action":
                "promote",

            "reason":
                "initial_forward_validated_champion",
        }

    if (
        recommended_model
        == current_model
    ):
        if new_rows >= (
            MIN_NEW_ROWS_FOR_REFRESH
        ):
            return {
                "action":
                    "refresh",

                "reason":
                    "same_champion_with_new_training_data",
            }

        return {
            "action":
                "keep",

            "reason":
                "same_champion_waiting_for_more_new_data",
        }

    if validator_decision == (
        "recommend_champion_switch"
    ):
        return {
            "action":
                "switch",

            "reason":
                "forward_validation_supports_model_switch",
        }

    return {
        "action":
            "keep",

        "reason":
            "challenger_not_materially_better_than_current_champion",
    }


def _build_candidate(
    rows,
    model_type,
    strength,
    validation,
    strength_source,
):
    model = fit_model(
        rows,
        model_type,
        strength,
    )

    model[
        "version"
    ] = GOVERNOR_VERSION

    model[
        "created_utc"
    ] = datetime.now(
        timezone.utc
    ).isoformat()

    model[
        "governed"
    ] = True

    model[
        "dataset_signature"
    ] = dataset_signature(
        rows
    )

    model[
        "trained_rows"
    ] = len(
        rows
    )

    model[
        "trained_from"
    ] = (
        rows[0].get(
            "timestamp"
        )
        if rows
        else None
    )

    model[
        "trained_through"
    ] = (
        rows[-1].get(
            "timestamp"
        )
        if rows
        else None
    )

    model[
        "strength_selection"
    ] = {
        "strength":
            strength,

        "source":
            strength_source,
    }

    model[
        "forward_validation"
    ] = {
        "forward_validated":
            validation.get(
                "forward_validated"
            ),

        "recommended_model":
            validation.get(
                "recommended_model"
            ),

        "runner_up_model":
            validation.get(
                "runner_up_model"
            ),

        "gain_vs_constant_pct":
            validation.get(
                "gain_vs_constant_pct"
            ),

        "gain_vs_runner_up_pct":
            validation.get(
                "gain_vs_runner_up_pct"
            ),

        "folds":
            validation.get(
                "folds"
            ),
    }

    aggregate = (
        validation.get(
            "aggregates",
            {}
        ).get(
            model_type,
            {},
        )
    )

    model[
        "forward_metrics"
    ] = aggregate

    return model


def run_model_governor():
    loaded = (
        load_training_rows()
    )

    rows = loaded.get(
        "rows",
        [],
    )

    if len(rows) < 500:
        return {
            "version":
                GOVERNOR_VERSION,

            "status":
                "not_enough_data",

            "rows":
                len(
                    rows
                ),
        }

    validation = (
        run_forward_validation()
    )

    if validation.get(
        "status"
    ) != "ok":
        return {
            "version":
                GOVERNOR_VERSION,

            "status":
                "validation_failed",

            "validation_status":
                validation.get(
                    "status"
                ),
        }

    recommended = (
        validation.get(
            "recommended_model"
        )
    )

    aggregates = validation.get(
        "aggregates",
        {},
    )

    if not isinstance(
        aggregates,
        dict,
    ):
        aggregates = {}

    recommended_aggregate = (
        aggregates.get(
            recommended,
            {},
        )
    )

    current_champion = read_json(
        CHAMPION_FILE,
        default={},
    )

    if not isinstance(
        current_champion,
        dict,
    ):
        current_champion = {}

    current_model = (
        current_champion.get(
            "model_type"
        )
    )

    strength_selection = (
        _recommended_strength(
            validation,
            recommended,
            current_champion,
        )
    )

    strength = (
        strength_selection.get(
            "strength",
            0,
        )
    )

    strength_source = (
        strength_selection.get(
            "source"
        )
    )

    previous_rows = safe_int(
        current_champion.get(
            "trained_rows"
        )
    )

    if previous_rows is None:
        previous_rows = 0

    new_rows = max(
        0,
        len(rows)
        - previous_rows,
    )

    policy = (
        _promotion_policy(
            current_model,
            recommended,
            validation.get(
                "forward_validated"
            )
            is True,
            validation.get(
                "champion_decision"
            ),
            new_rows,
        )
    )

    candidate = None

    if recommended is not None:
        candidate = (
            _build_candidate(
                rows,
                recommended,
                strength,
                validation,
                strength_source,
            )
        )

        RETAIL_MODEL_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        write_json_atomic(
            GOVERNOR_CHALLENGER_FILE,
            candidate,
        )

    action = policy.get(
        "action"
    )

    archived_champion = None

    promoted = False

    if (
        action
        in (
            "promote",
            "refresh",
            "switch",
        )
        and candidate
        is not None
    ):
        if current_champion:
            archived_champion = (
                _archive_champion(
                    current_champion
                )
            )

        write_json_atomic(
            CHAMPION_FILE,
            candidate,
        )

        promoted = True

    final_champion = read_json(
        CHAMPION_FILE,
        default={},
    )

    if not isinstance(
        final_champion,
        dict,
    ):
        final_champion = {}

    recommended_mean = safe_float(
        recommended_aggregate.get(
            "mean_mae_cent_kwh"
        )
    )

    current_aggregate = (
        aggregates.get(
            current_model,
            {},
        )
        if current_model
        is not None
        else {}
    )

    current_mean = safe_float(
        current_aggregate.get(
            "mean_mae_cent_kwh"
        )
    )

    relative_gain = None

    if (
        current_mean is not None
        and current_mean > 0
        and recommended_mean
        is not None
    ):
        relative_gain = (
            (
                current_mean
                - recommended_mean
            )
            / current_mean
            * 100
        )

    report = {
        "version":
            GOVERNOR_VERSION,

        "status":
            "ok",

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "rows":
            len(
                rows
            ),

        "source_counts":
            loaded.get(
                "source_counts",
                {},
            ),

        "previous_trained_rows":
            previous_rows,

        "new_rows":
            new_rows,

        "current_champion_before":
            current_model,

        "current_champion_strength_before":
            current_champion.get(
                "strength"
            ),

        "recommended_model":
            recommended,

        "recommended_strength":
            strength,

        "recommended_strength_source":
            strength_source,

        "runner_up_model":
            validation.get(
                "runner_up_model"
            ),

        "forward_validated":
            validation.get(
                "forward_validated"
            ),

        "validator_decision":
            validation.get(
                "champion_decision"
            ),

        "gain_vs_constant_pct":
            validation.get(
                "gain_vs_constant_pct"
            ),

        "gain_vs_runner_up_pct":
            validation.get(
                "gain_vs_runner_up_pct"
            ),

        "recommended_mean_mae_cent_kwh":
            recommended_mean,

        "current_mean_mae_cent_kwh":
            current_mean,

        "relative_gain_vs_current_pct":
            (
                round(
                    relative_gain,
                    3,
                )
                if relative_gain
                is not None
                else None
            ),

        "policy_action":
            action,

        "policy_reason":
            policy.get(
                "reason"
            ),

        "promoted":
            promoted,

        "champion_after":
            final_champion.get(
                "model_type"
            ),

        "champion_strength_after":
            final_champion.get(
                "strength"
            ),

        "champion_trained_rows_after":
            final_champion.get(
                "trained_rows"
            ),

        "archived_champion":
            archived_champion,

        "champion_file":
            str(
                CHAMPION_FILE
            ),

        "challenger_file":
            str(
                GOVERNOR_CHALLENGER_FILE
            ),
    }

    GOVERNOR_REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json_atomic(
        GOVERNOR_REPORT_FILE,
        report,
    )

    return {
        "version":
            GOVERNOR_VERSION,

        "status":
            "ok",

        "rows":
            len(
                rows
            ),

        "new_rows":
            new_rows,

        "current_champion_before":
            current_model,

        "current_champion_strength_before":
            current_champion.get(
                "strength"
            ),

        "recommended_model":
            recommended,

        "recommended_strength":
            strength,

        "recommended_strength_source":
            strength_source,

        "runner_up_model":
            validation.get(
                "runner_up_model"
            ),

        "forward_validated":
            validation.get(
                "forward_validated"
            ),

        "validator_decision":
            validation.get(
                "champion_decision"
            ),

        "gain_vs_constant_pct":
            validation.get(
                "gain_vs_constant_pct"
            ),

        "gain_vs_runner_up_pct":
            validation.get(
                "gain_vs_runner_up_pct"
            ),

        "recommended_mean_mae_cent_kwh":
            recommended_mean,

        "current_mean_mae_cent_kwh":
            current_mean,

        "relative_gain_vs_current_pct":
            (
                round(
                    relative_gain,
                    3,
                )
                if relative_gain
                is not None
                else None
            ),

        "action":
            action,

        "reason":
            policy.get(
                "reason"
            ),

        "promoted":
            promoted,

        "champion_after":
            final_champion.get(
                "model_type"
            ),

        "champion_strength_after":
            final_champion.get(
                "strength"
            ),

        "champion_trained_rows_after":
            final_champion.get(
                "trained_rows"
            ),

        "archived_champion":
            archived_champion,

        "report_file":
            str(
                GOVERNOR_REPORT_FILE
            ),
    }


def model_governor_self_test():
    test_1 = (
        _promotion_policy(
            "linear_hour_residual",
            "linear_hour_residual",
            True,
            "keep_current_champion",
            120,
        )
    )

    test_2 = (
        _promotion_policy(
            "linear_market",
            "linear_hour_residual",
            True,
            "recommend_champion_switch",
            200,
        )
    )

    test_3 = (
        _promotion_policy(
            "linear_hour_residual",
            "hour_of_week_margin",
            False,
            "recommend_champion_switch",
            500,
        )
    )

    validation_test = {
        "fold_results": [
            {
                "fold": 1,
                "models": {
                    "linear_hour_residual": {
                        "strength": 0,
                    }
                },
            },
            {
                "fold": 2,
                "models": {
                    "linear_hour_residual": {
                        "strength": 48,
                    }
                },
            },
            {
                "fold": 3,
                "models": {
                    "linear_hour_residual": {
                        "strength": 4,
                    }
                },
            },
        ],

        "aggregates": {
            "linear_hour_residual": {
                "selected_strengths": [
                    0,
                    48,
                    4,
                ]
            }
        },
    }

    strength_result = (
        _recommended_strength(
            validation_test,
            "linear_hour_residual",
            {
                "model_type":
                    "linear_hour_residual",

                "strength":
                    8,
            },
        )
    )

    ok = (
        test_1.get(
            "action"
        ) == "refresh"
        and test_2.get(
            "action"
        ) == "switch"
        and test_3.get(
            "action"
        ) == "keep"
        and strength_result.get(
            "strength"
        ) == 4
        and strength_result.get(
            "source"
        ) == "latest_forward_fold"
    )

    return {
        "version":
            GOVERNOR_VERSION,

        "status":
            (
                "ok"
                if ok
                else "error"
            ),

        "same_model_action":
            test_1.get(
                "action"
            ),

        "switch_action":
            test_2.get(
                "action"
            ),

        "unvalidated_action":
            test_3.get(
                "action"
            ),

        "selected_strength":
            strength_result.get(
                "strength"
            ),

        "strength_source":
            strength_result.get(
                "source"
            ),
    }
