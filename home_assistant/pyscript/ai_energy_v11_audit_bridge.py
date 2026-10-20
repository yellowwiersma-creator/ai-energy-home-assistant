import sys


BRIDGE_VERSION = "11.4.1-audit-bridge"


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
def ai_energy_v11_margin_audit():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            ai_energy_v11.run_margin_audit
        )

        state.set(
            "sensor.ai_energy_v11_margin_audit",
            result.get(
                "status",
                "unknown",
            ),
            {
                "friendly_name":
                    "AI Energy V11 Margin Audit",

                "bridge_version":
                    BRIDGE_VERSION,

                "audit_version":
                    result.get(
                        "version"
                    ),

                "unified_rows":
                    result.get(
                        "unified_rows"
                    ),

                "eligible_rows":
                    result.get(
                        "eligible_rows"
                    ),

                "excluded_rows":
                    result.get(
                        "excluded_rows"
                    ),

                "first_timestamp":
                    result.get(
                        "first_timestamp"
                    ),

                "last_timestamp":
                    result.get(
                        "last_timestamp"
                    ),

                "median_margin_cent_kwh":
                    result.get(
                        "median_margin_cent_kwh"
                    ),

                "mean_margin_cent_kwh":
                    result.get(
                        "mean_margin_cent_kwh"
                    ),

                "p05_margin_cent_kwh":
                    result.get(
                        "p05_margin_cent_kwh"
                    ),

                "p95_margin_cent_kwh":
                    result.get(
                        "p95_margin_cent_kwh"
                    ),

                "linear_slope":
                    result.get(
                        "linear_slope"
                    ),

                "linear_intercept_cent_kwh":
                    result.get(
                        "linear_intercept_cent_kwh"
                    ),

                "linear_r_squared":
                    result.get(
                        "linear_r_squared"
                    ),

                "outlier_candidates":
                    result.get(
                        "outlier_candidates"
                    ),

                "best_baseline":
                    result.get(
                        "baseline"
                    ),

                "baseline_mae_cent_kwh":
                    result.get(
                        "baseline_mae_cent_kwh"
                    ),

                "baseline_improvement_pct":
                    result.get(
                        "baseline_improvement_pct"
                    ),

                "report_file":
                    result.get(
                        "report_file"
                    ),

                "interpretation":
                    result.get(
                        "interpretation"
                    ),

                "icon":
                    "mdi:chart-bell-curve-cumulative",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_margin_audit",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Margin Audit",

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
def ai_energy_v11_margin_audit_test():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            ai_energy_v11.margin_audit_self_test
        )

        state.set(
            "sensor.ai_energy_v11_margin_audit_test",
            result.get(
                "status"
            ),
            {
                "friendly_name":
                    "AI Energy V11 Margin Audit Test",

                "bridge_version":
                    BRIDGE_VERSION,

                "audit_version":
                    result.get(
                        "version"
                    ),

                "slope":
                    result.get(
                        "slope"
                    ),

                "intercept":
                    result.get(
                        "intercept"
                    ),

                "r_squared":
                    result.get(
                        "r_squared"
                    ),

                "icon":
                    "mdi:test-tube",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_margin_audit_test",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Margin Audit Test",

                "bridge_version":
                    BRIDGE_VERSION,

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )

        raise
