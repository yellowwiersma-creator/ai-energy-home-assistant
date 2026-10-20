import sys
from importlib import reload as reload_module


BRIDGE_VERSION = "11.5.8-reviewed-production-bridge"


if "/config/pyscript_modules" not in sys.path:
    sys.path.append(
        "/config/pyscript_modules"
    )


import ai_energy_v11
import ai_energy_v11.decision_confidence as decision_engine
import ai_energy_v11.retail_learner as learner_engine
import ai_energy_v11.forecast_evaluator as evaluation_engine
import ai_energy_v11.market_review as review_engine
import ai_energy_v11.market_forecaster as market_engine
from ai_energy_v11 import config as public_config


def _public_ready():
    """Fresh installs are inert until local settings explicitly enable the suite."""
    if public_config.ENABLED:
        return True
    state.set("sensor.ai_energy_v11_setup", "configuration_required", {
        "friendly_name": "AI Energy setup",
        "message": "Fill local settings.json and explicitly set enabled to true, then restart Pyscript.",
    })
    return False


def _publish_decision(
    result,
):
    state.set(
        "sensor.ai_energy_v11_decision",
        result.get(
            "status",
            "unknown",
        ),
        {
            "friendly_name":
                "AI Energy V11 Decision",

            "bridge_version":
                BRIDGE_VERSION,

            "empirical_calibration": result.get("empirical_calibration", {}),
            "discarded_expired_slots": result.get("discarded_expired_slots", 0),
            "decision_version":
                result.get(
                    "version"
                ),

            "slots":
                result.get(
                    "slots"
                ),

            "confidence_counts":
                result.get(
                    "confidence_counts"
                ),

            "decision":
                result.get(
                    "decision"
                ),

            "decision_reason":
                result.get(
                    "decision_reason"
                ),

            "selected_timestamp":
                result.get(
                    "selected_timestamp"
                ),

            "selected_price_cent_kwh":
                result.get(
                    "selected_price_cent_kwh"
                ),

            "selected_market_source":
                result.get(
                    "selected_market_source"
                ),

            "selected_confidence":
                result.get(
                    "selected_confidence"
                ),

            "best_expected_timestamp":
                result.get(
                    "best_expected_timestamp"
                ),

            "best_expected_price_cent_kwh":
                result.get(
                    "best_expected_price_cent_kwh"
                ),

            "best_expected_source":
                result.get(
                    "best_expected_source"
                ),

            "best_known_timestamp":
                result.get(
                    "best_known_timestamp"
                ),

            "best_known_price_cent_kwh":
                result.get(
                    "best_known_price_cent_kwh"
                ),

            "expected_saving_vs_known_cent_kwh":
                result.get(
                    "expected_saving_vs_known_cent_kwh"
                ),

            "safety_gap_cent_kwh":
                result.get(
                    "safety_gap_cent_kwh"
                ),

            "required_extra_advantage_cent_kwh":
                result.get(
                    "required_extra_advantage_cent_kwh"
                ),

            "blocks":
                result.get(
                    "blocks"
                ),

            "output_file":
                result.get(
                    "output_file"
                ),

            "icon":
                "mdi:shield-check",
        },
    )


def _publish_evaluation(
    result,
):
    state.set(
        "sensor.ai_energy_v11_forecast_accuracy",
        result.get(
            "status",
            "unknown",
        ),
        {
            "friendly_name":
                "AI Energy V11 Forecast Accuracy",

            "forward_quality": result.get("forward_quality", {}),

            "bridge_version":
                BRIDGE_VERSION,

            "quarter_hour": result.get("quarter_hour", {}),
            "evaluator_version":
                result.get(
                    "version"
                ),

            "archives_scanned":
                result.get(
                    "archives_scanned"
                ),

            "snapshots_with_actuals":
                result.get(
                    "snapshots_with_actuals"
                ),

            "evaluated_points":
                result.get(
                    "evaluated_points"
                ),

            "unique_actual_slots":
                result.get(
                    "unique_actual_slots"
                ),

            "retail_mae_cent_kwh":
                result.get(
                    "retail_mae_cent_kwh"
                ),

            "known_retail_mae_cent_kwh":
                result.get(
                    "known_retail_mae_cent_kwh"
                ),

            "ai_retail_mae_cent_kwh":
                result.get(
                    "ai_retail_mae_cent_kwh"
                ),

            "ai_market_mae_cent_kwh":
                result.get(
                    "ai_market_mae_cent_kwh"
                ),

            "retail_horizons":
                result.get(
                    "retail_horizons"
                ),

            "market_horizons":
                result.get(
                    "market_horizons"
                ),

            "report_file":
                result.get(
                    "report_file"
                ),

            "icon":
                "mdi:target",
        },
    )


def _production_update(
    reason,
):
    archive = task.executor(
        evaluation_engine.archive_current_forecast
    )

    # Publish the independent 96-hour validation without changing model selection.
    try:
        review = task.executor(review_engine.get_review)
        state.set("sensor.ai_energy_v11_market_review", review.get("status", "unknown"), review)
    except Exception as err:
        state.set("sensor.ai_energy_v11_market_review", "error", {"error": str(err)})

    decision = task.executor(
        decision_engine.build_decision_confidence
    )

    _publish_decision(
        decision
    )

    state.set(
        "sensor.ai_energy_v11_production",
        "ok",
        {
            "friendly_name":
                "AI Energy V11 Production",

            "bridge_version":
                BRIDGE_VERSION,

            "reason":
                reason,

            "archive_action": archive.get("archive_action"),

            "archive_status":
                archive.get(
                    "status"
                ),

            "archive_slots":
                archive.get(
                    "slots"
                ),

            "archive_file":
                archive.get(
                    "archive_file"
                ),

            "decision_status":
                decision.get(
                    "status"
                ),

            "decision":
                decision.get(
                    "decision"
                ),

            "icon":
                "mdi:factory",
        },
    )


@service
def ai_energy_v11_production_update():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        _production_update(
            "manual"
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_production",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Production",

                "bridge_version":
                    BRIDGE_VERSION,

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )

        raise


@service
def ai_energy_v11_evaluate_forecasts():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            evaluation_engine.evaluate_forecasts
        )

        _publish_evaluation(
            result
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_forecast_accuracy",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Forecast Accuracy",

                "bridge_version":
                    BRIDGE_VERSION,

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )

        raise


@service
def ai_energy_v11_evaluator_test():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            evaluation_engine.forecast_evaluator_self_test
        )

        state.set(
            "sensor.ai_energy_v11_evaluator_test",
            result.get(
                "status",
                "unknown",
            ),
            {
                "friendly_name":
                    "AI Energy V11 Evaluator Test",

                "bridge_version":
                    BRIDGE_VERSION,

                "evaluator_version":
                    result.get(
                        "version"
                    ),

                "mae":
                    result.get(
                        "mae"
                    ),

                "bias":
                    result.get(
                        "bias"
                    ),

                "bucket_test":
                    result.get(
                        "bucket_test"
                    ),

                "icon":
                    "mdi:test-tube",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_evaluator_test",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Evaluator Test",

                "bridge_version":
                    BRIDGE_VERSION,

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )

        raise


@time_trigger(
    "cron(10 * * * *)"
)
def ai_energy_v11_production_schedule():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        _production_update(
            "scheduled_hourly"
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_production",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Production",

                "bridge_version":
                    BRIDGE_VERSION,

                "reason":
                    "scheduled_hourly",

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )


@time_trigger(
    "cron(20 0,6,12,18 * * *)"
)
def ai_energy_v11_evaluation_schedule():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            evaluation_engine.evaluate_forecasts
        )

        _publish_evaluation(
            result
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_forecast_accuracy",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Forecast Accuracy",

                "bridge_version":
                    BRIDGE_VERSION,

                "reason":
                    "scheduled_6h",

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )


@time_trigger("startup")
def ai_energy_v11_production_startup():
    # Native Python modules live outside Pyscript's automatic reload directory.
    # Reload only this price-advice module; keep the measured accuracy history.
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        task.executor(reload_module, learner_engine)
        task.executor(reload_module, evaluation_engine)
        task.executor(reload_module, market_engine)
        task.executor(reload_module, review_engine)
        task.executor(reload_module, decision_engine)
        _production_update("price_advice_calibration_loaded")
    except Exception as err:
        state.set("sensor.ai_energy_v11_production", "error", {
            "friendly_name": "AI Energy V11 Production",
            "bridge_version": BRIDGE_VERSION,
            "reason": "price_advice_calibration_loaded",
            "error": str(err),
            "icon": "mdi:alert-circle",
        })


@service
def ai_energy_v11_apply_96h_review():
    if not _public_ready():
        return {"status": "configuration_required"}

    result = task.executor(review_engine.apply_review)
    state.set("sensor.ai_energy_v11_market_review", result.get("status", "unknown"), result)
