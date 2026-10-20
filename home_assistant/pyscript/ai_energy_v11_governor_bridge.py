import sys


BRIDGE_VERSION = "11.5.6-governor-bridge"


if "/config/pyscript_modules" not in sys.path:
    sys.path.append(
        "/config/pyscript_modules"
    )


import ai_energy_v11
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


def _publish(
    result,
    reason,
):
    state.set(
        "sensor.ai_energy_v11_model_governor",
        result.get(
            "status",
            "unknown",
        ),
        {
            "friendly_name":
                "AI Energy V11 Model Governor",

            "bridge_version":
                BRIDGE_VERSION,

            "governor_version":
                result.get(
                    "version"
                ),

            "reason":
                reason,

            "rows":
                result.get(
                    "rows"
                ),

            "new_rows":
                result.get(
                    "new_rows"
                ),

            "current_champion_before":
                result.get(
                    "current_champion_before"
                ),

            "recommended_model":
                result.get(
                    "recommended_model"
                ),

            "recommended_strength":
                result.get(
                    "recommended_strength"
                ),

            "runner_up_model":
                result.get(
                    "runner_up_model"
                ),

            "forward_validated":
                result.get(
                    "forward_validated"
                ),

            "validator_decision":
                result.get(
                    "validator_decision"
                ),

            "gain_vs_constant_pct":
                result.get(
                    "gain_vs_constant_pct"
                ),

            "gain_vs_runner_up_pct":
                result.get(
                    "gain_vs_runner_up_pct"
                ),

            "recommended_mean_mae_cent_kwh":
                result.get(
                    "recommended_mean_mae_cent_kwh"
                ),

            "current_mean_mae_cent_kwh":
                result.get(
                    "current_mean_mae_cent_kwh"
                ),

            "relative_gain_vs_current_pct":
                result.get(
                    "relative_gain_vs_current_pct"
                ),

            "action":
                result.get(
                    "action"
                ),

            "action_reason":
                result.get(
                    "reason"
                ),

            "promoted":
                result.get(
                    "promoted"
                ),

            "champion_after":
                result.get(
                    "champion_after"
                ),

            "champion_strength_after":
                result.get(
                    "champion_strength_after"
                ),

            "champion_trained_rows_after":
                result.get(
                    "champion_trained_rows_after"
                ),

            "archived_champion":
                result.get(
                    "archived_champion"
                ),

            "report_file":
                result.get(
                    "report_file"
                ),

            "icon":
                "mdi:trophy-variant",
        },
    )


def _run(
    reason,
):
    result = task.executor(
        ai_energy_v11.run_model_governor
    )

    _publish(
        result,
        reason,
    )

    return result


@service
def ai_energy_v11_model_governor():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        _run(
            "manual"
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_model_governor",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Model Governor",

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
def ai_energy_v11_model_governor_test():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            ai_energy_v11.model_governor_self_test
        )

        state.set(
            "sensor.ai_energy_v11_model_governor_test",
            result.get(
                "status",
                "unknown",
            ),
            {
                "friendly_name":
                    "AI Energy V11 Model Governor Test",

                "bridge_version":
                    BRIDGE_VERSION,

                "governor_version":
                    result.get(
                        "version"
                ),

                "same_model_action":
                    result.get(
                        "same_model_action"
                ),

                "switch_action":
                    result.get(
                        "switch_action"
                ),

                "unvalidated_action":
                    result.get(
                        "unvalidated_action"
                ),

                "selected_strength":
                    result.get(
                        "selected_strength"
                ),

                "icon":
                    "mdi:test-tube",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_model_governor_test",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Model Governor Test",

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
    "cron(40 3 * * *)"
)
def ai_energy_v11_model_governor_schedule():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        _run(
            "scheduled_daily"
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_model_governor",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Model Governor",

                "bridge_version":
                    BRIDGE_VERSION,

                "reason":
                    "scheduled_daily",

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )


@time_trigger("startup")
def ai_energy_v11_model_governor_startup():
    if not _public_ready():
        return {"status": "configuration_required"}

    state.set(
        "sensor.ai_energy_v11_model_governor",
        "idle",
        {
            "friendly_name":
                "AI Energy V11 Model Governor",

            "bridge_version":
                BRIDGE_VERSION,

            "schedule":
                "daily at 03:40",

            "minimum_new_rows_for_refresh":
                96,

            "icon":
                "mdi:trophy-variant",
        },
    )
