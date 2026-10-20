import sys


BRIDGE_VERSION = "11.4.2-learning-bridge"


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


@service
def ai_energy_v11_retail_learn():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            ai_energy_v11.run_retail_learning
        )

        state.set(
            "sensor.ai_energy_v11_retail_learner",
            result.get(
                "status",
                "unknown",
            ),
            {
                "friendly_name":
                    "AI Energy V11 Retail Learner",

                "bridge_version":
                    BRIDGE_VERSION,

                "learner_version":
                    result.get(
                        "version"
                    ),

                "rows":
                    result.get(
                        "rows"
                    ),

                "train_rows":
                    result.get(
                        "train_rows"
                    ),

                "validation_rows":
                    result.get(
                        "validation_rows"
                    ),

                "test_rows":
                    result.get(
                        "test_rows"
                    ),

                "selected_model":
                    result.get(
                        "selected_model"
                    ),

                "selected_strength":
                    result.get(
                        "selected_strength"
                    ),

                "validation_mae_cent_kwh":
                    result.get(
                        "validation_mae_cent_kwh"
                    ),

                "test_mae_cent_kwh":
                    result.get(
                        "test_mae_cent_kwh"
                    ),

                "test_rmse_cent_kwh":
                    result.get(
                        "test_rmse_cent_kwh"
                    ),

                "test_bias_cent_kwh":
                    result.get(
                        "test_bias_cent_kwh"
                    ),

                "constant_test_mae_cent_kwh":
                    result.get(
                        "constant_test_mae_cent_kwh"
                    ),

                "gain_vs_constant_pct":
                    result.get(
                        "gain_vs_constant_pct"
                    ),

                "audit_reference_mae_cent_kwh":
                    result.get(
                        "audit_reference_mae_cent_kwh"
                    ),

                "beats_audit_reference":
                    result.get(
                        "beats_audit_reference"
                    ),

                "champion_action":
                    result.get(
                        "champion_action"
                    ),

                "model_summary":
                    result.get(
                        "model_summary"
                    ),

                "source_counts":
                    result.get(
                        "source_counts"
                    ),

                "champion_file":
                    result.get(
                        "champion_file"
                    ),

                "challenger_file":
                    result.get(
                        "challenger_file"
                    ),

                "report_file":
                    result.get(
                        "report_file"
                    ),

                "icon":
                    "mdi:brain",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_retail_learner",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Retail Learner",

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
def ai_energy_v11_retail_learner_test():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            ai_energy_v11.retail_learner_self_test
        )

        state.set(
            "sensor.ai_energy_v11_retail_learner_test",
            result.get(
                "status"
            ),
            {
                "friendly_name":
                    "AI Energy V11 Retail Learner Test",

                "bridge_version":
                    BRIDGE_VERSION,

                "learner_version":
                    result.get(
                        "version"
                    ),

                "linear_mae_cent_kwh":
                    result.get(
                        "linear_mae_cent_kwh"
                    ),

                "residual_mae_cent_kwh":
                    result.get(
                        "residual_mae_cent_kwh"
                    ),

                "improved":
                    result.get(
                        "improved"
                    ),

                "icon":
                    "mdi:test-tube",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_retail_learner_test",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Retail Learner Test",

                "bridge_version":
                    BRIDGE_VERSION,

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )

        raise
