import sys


BRIDGE_VERSION = "11.6.2-dashboard-stable-bridge"


if "/config/pyscript_modules" not in sys.path:
    sys.path.append(
        "/config/pyscript_modules"
    )


from ai_energy_v11 import config as public_config

from ai_energy_v11.dashboard_adapter import (
    DASHBOARD_ADAPTER_VERSION,
    load_dashboard_payload,
    dashboard_adapter_self_test,
)


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
        "sensor.ai_energy_v11_dashboard_data",
        result.get(
            "status",
            "unknown",
        ),
        {
            "friendly_name":
                "AI Energy V11 Dashboard Data",

            "retail_unit": "ct/kWh",
            "retail_price_unit": "ct/kWh",
            "market_unit": "ct/kWh",
            "interval_minutes": 15,

            "bridge_version":
                BRIDGE_VERSION,

            "adapter_version":
                result.get(
                    "version"
                ),

            "reason":
                reason,

            "core_ready":
                result.get(
                    "core_ready"
                ),

            "issue_time_local":
                result.get(
                    "issue_time_local"
                ),

            "forecast_points":
                result.get(
                    "forecast_points"
                ),

            "known_market_slots":
                result.get(
                    "known_market_slots"
                ),

            "ai_market_slots":
                result.get(
                    "ai_market_slots"
                ),

            "known_market_pct":
                result.get(
                    "known_market_pct"
                ),

            "market_model":
                result.get(
                    "market_model"
                ),

            "retail_model":
                result.get(
                    "retail_model"
                ),

            "retail_min_cent":
                result.get(
                    "retail_min_cent"
                ),

            "retail_avg_cent":
                result.get(
                    "retail_avg_cent"
                ),

            "retail_max_cent":
                result.get(
                    "retail_max_cent"
                ),

            "market_min_cent":
                result.get(
                    "market_min_cent"
                ),

            "market_avg_cent":
                result.get(
                    "market_avg_cent"
                ),

            "market_max_cent":
                result.get(
                    "market_max_cent"
                ),

            "decision":
                result.get(
                    "decision"
                ),

            "decision_reason":
                result.get(
                    "decision_reason"
                ),

            "selected":
                result.get(
                    "selected",
                    {},
                ),

            "best_expected":
                result.get(
                    "best_expected",
                    {},
                ),

            "best_known":
                result.get(
                    "best_known",
                    {},
                ),

            "expected_saving_cent":
                result.get(
                    "expected_saving_cent"
                ),

            "required_extra_advantage_cent":
                result.get(
                    "required_extra_advantage_cent"
                ),

            "safety_gap_cent":
                result.get(
                    "safety_gap_cent"
                ),

            "confidence_counts":
                result.get(
                    "confidence_counts",
                    {},
                ),

            "blocks":
                result.get(
                    "blocks",
                    {},
                ),

            "governor":
                result.get(
                    "governor",
                    {},
                ),

            "accuracy":
                result.get(
                    "accuracy",
                    {},
                ),

            "weather":
                result.get(
                    "weather",
                    {},
                ),

            "forecast_archive_count":
                result.get(
                    "forecast_archive_count"
                ),

            "forecast_input_snapshot_count":
                result.get(
                    "forecast_input_snapshot_count"
                ),

            "forecast":
                result.get(
                    "forecast",
                    [],
                ),

            "icon":
                "mdi:chart-timeline-variant",
        },
    )


def _run(
    reason,
):
    result = task.executor(
        load_dashboard_payload
    )

    _publish(
        result,
        reason,
    )

    return result


@service
def ai_energy_v11_dashboard_refresh():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        _run(
            "manual"
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_dashboard_data",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Dashboard Data",

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
def ai_energy_v11_dashboard_test():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            dashboard_adapter_self_test
        )

        state.set(
            "sensor.ai_energy_v11_dashboard_test",
            result.get(
                "status",
                "unknown",
            ),
            {
                "friendly_name":
                    "AI Energy V11 Dashboard Test",

                "bridge_version":
                    BRIDGE_VERSION,

                "adapter_version":
                    DASHBOARD_ADAPTER_VERSION,

                "core_ready":
                    result.get(
                        "core_ready"
                ),

                "forecast_points":
                    result.get(
                        "forecast_points"
                ),

                "known_market_slots":
                    result.get(
                        "known_market_slots"
                ),

                "ai_market_slots":
                    result.get(
                        "ai_market_slots"
                ),

                "icon":
                    "mdi:test-tube",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_dashboard_test",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Dashboard Test",

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
    "cron(11 * * * *)"
)
def ai_energy_v11_dashboard_schedule():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        _run(
            "scheduled_hourly"
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_dashboard_data",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Dashboard Data",

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


@time_trigger("startup")
def ai_energy_v11_dashboard_startup():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        _run(
            "startup"
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_dashboard_data",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Dashboard Data",

                "bridge_version":
                    BRIDGE_VERSION,

                "reason":
                    "startup",

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )
