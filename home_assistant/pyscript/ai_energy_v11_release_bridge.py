import sys
if "/config/pyscript_modules" not in sys.path:
    sys.path.append("/config/pyscript_modules")
from ai_energy_v11 import config as public_config

RELEASE_VERSION = "11.6.0-core-release"


def _public_ready():
    """Fresh installs are inert until local settings explicitly enable the suite."""
    if public_config.ENABLED:
        return True
    state.set("sensor.ai_energy_v11_setup", "configuration_required", {
        "friendly_name": "AI Energy setup",
        "message": "Fill local settings.json and explicitly set enabled to true, then restart Pyscript.",
    })
    return False


def _get_state(entity_id):
    try:
        return state.get(
            entity_id
        )
    except Exception:
        return None


def _get_attrs(entity_id):
    try:
        attrs = state.getattr(
            entity_id
        )

        if isinstance(
            attrs,
            dict,
        ):
            return attrs

    except Exception:
        pass

    return {}


def _call_pyscript_service(
    service_name
):
    try:
        service.call(
            "pyscript",
            service_name,
            blocking=True,
        )

        return {
            "status":
                "ok",

            "service":
                service_name,
        }

    except Exception as err:
        return {
            "status":
                "error",

            "service":
                service_name,

            "error":
                str(err),
        }


def _market_refresh(
    reason
):
    nordpool = (
        _call_pyscript_service(
            "ai_energy_v11_nordpool_refresh"
        )
    )

    entsoe = (
        _call_pyscript_service(
            "ai_energy_v11_entsoe_refresh"
        )
    )

    state.set(
        "sensor.ai_energy_v11_market_refresh",
        (
            "ok"
            if (
                nordpool.get(
                    "status"
                )
                == "ok"
                and entsoe.get(
                    "status"
                )
                == "ok"
            )
            else "degraded"
        ),
        {
            "friendly_name":
                "AI Energy V11 Market Refresh",

            "release_version":
                RELEASE_VERSION,

            "reason":
                reason,

            "nordpool_status":
                nordpool.get(
                    "status"
                ),

            "nordpool_error":
                nordpool.get(
                    "error"
                ),

            "entsoe_status":
                entsoe.get(
                    "status"
                ),

            "entsoe_error":
                entsoe.get(
                    "error"
                ),

            "icon":
                "mdi:transmission-tower-import",
        },
    )


def _release_check(
    reason
):
    collector_state = (
        _get_state(
            "sensor.ai_energy_v11_collector"
        )
    )

    collector_attrs = (
        _get_attrs(
            "sensor.ai_energy_v11_collector"
        )
    )

    forecast_state = (
        _get_state(
            "sensor.ai_energy_v11_forecast_96h"
        )
    )

    forecast_attrs = (
        _get_attrs(
            "sensor.ai_energy_v11_forecast_96h"
        )
    )

    production_state = (
        _get_state(
            "sensor.ai_energy_v11_production"
        )
    )

    production_attrs = (
        _get_attrs(
            "sensor.ai_energy_v11_production"
        )
    )

    decision_state = (
        _get_state(
            "sensor.ai_energy_v11_decision"
        )
    )

    decision_attrs = (
        _get_attrs(
            "sensor.ai_energy_v11_decision"
        )
    )

    accuracy_state = (
        _get_state(
            "sensor.ai_energy_v11_forecast_accuracy"
        )
    )

    accuracy_attrs = (
        _get_attrs(
            "sensor.ai_energy_v11_forecast_accuracy"
        )
    )

    governor_state = (
        _get_state(
            "sensor.ai_energy_v11_model_governor"
        )
    )

    governor_attrs = (
        _get_attrs(
            "sensor.ai_energy_v11_model_governor"
        )
    )

    problems = []

    if collector_state == "error":
        problems.append(
            "collector_error"
        )

    if forecast_state == "error":
        problems.append(
            "forecast_error"
        )

    if production_state == "error":
        problems.append(
            "production_error"
        )

    if decision_state == "error":
        problems.append(
            "decision_error"
        )

    if governor_state == "error":
        problems.append(
            "governor_error"
        )

    forecast_slots = (
        forecast_attrs.get(
            "slots"
        )
    )

    try:
        forecast_slots_int = int(
            forecast_slots
        )
    except Exception:
        forecast_slots_int = 0

    if (
        forecast_state == "ok"
        and forecast_slots_int
        != 384
    ):
        problems.append(
            "forecast_not_384_slots"
        )

    known_market_slots = (
        forecast_attrs.get(
            "known_market_slots"
        )
    )

    ai_market_slots = (
        forecast_attrs.get(
            "ai_market_slots"
        )
    )

    total_market_slots = 0

    try:
        total_market_slots = (
            int(
                known_market_slots
                or 0
            )
            + int(
                ai_market_slots
                or 0
            )
        )
    except Exception:
        total_market_slots = 0

    if (
        forecast_state == "ok"
        and total_market_slots
        != 384
    ):
        problems.append(
            "market_slot_total_not_384"
        )

    ready_states = (
        "ok",
        "idle",
    )

    core_present = (
        collector_state
        is not None
        and forecast_state
        is not None
        and production_state
        is not None
        and decision_state
        is not None
    )

    if not core_present:
        release_state = (
            "warming_up"
        )

    elif problems:
        release_state = (
            "degraded"
        )

    elif (
        forecast_state == "ok"
        and decision_state == "ok"
        and production_state == "ok"
        and collector_state
        in ready_states
    ):
        release_state = (
            "ready"
        )

    else:
        release_state = (
            "warming_up"
        )

    state.set(
        "sensor.ai_energy_v11_release",
        release_state,
        {
            "friendly_name":
                "AI Energy V11 Release",

            "release_version":
                RELEASE_VERSION,

            "reason":
                reason,

            "core_ready":
                release_state
                == "ready",

            "problems":
                problems,

            "collector_state":
                collector_state,

            "collector_version":
                collector_attrs.get(
                    "collector_version"
                ),

            "collector_quality_pct":
                collector_attrs.get(
                    "collection_quality_pct"
                ),

            "forecast_state":
                forecast_state,

            "forecast_slots":
                forecast_slots_int,

            "known_market_slots":
                known_market_slots,

            "ai_market_slots":
                ai_market_slots,

            "market_model":
                forecast_attrs.get(
                    "market_model"
                ),

            "retail_model":
                forecast_attrs.get(
                    "retail_model"
                ),

            "forecast_retail_min_cent":
                forecast_attrs.get(
                    "retail_min_cent_kwh"
                ),

            "forecast_retail_avg_cent":
                forecast_attrs.get(
                    "retail_avg_cent_kwh"
                ),

            "forecast_retail_max_cent":
                forecast_attrs.get(
                    "retail_max_cent_kwh"
                ),

            "production_state":
                production_state,

            "archive_status":
                production_attrs.get(
                    "archive_status"
                ),

            "decision_state":
                decision_state,

            "decision":
                decision_attrs.get(
                    "decision"
                ),

            "selected_timestamp":
                decision_attrs.get(
                    "selected_timestamp"
                ),

            "selected_price_cent":
                decision_attrs.get(
                    "selected_price_cent_kwh"
                ),

            "selected_confidence":
                decision_attrs.get(
                    "selected_confidence"
                ),

            "accuracy_state":
                accuracy_state,

            "evaluated_points":
                accuracy_attrs.get(
                    "evaluated_points"
                ),

            "actual_retail_mae_cent":
                accuracy_attrs.get(
                    "retail_mae_cent_kwh"
                ),

            "actual_ai_market_mae_cent":
                accuracy_attrs.get(
                    "ai_market_mae_cent_kwh"
                ),

            "governor_state":
                governor_state,

            "champion":
                governor_attrs.get(
                    "champion_after"
                ),

            "governor_action":
                governor_attrs.get(
                    "action"
                ),

            "weather_learning":
                "collecting_training_data",

            "icon":
                (
                    "mdi:check-decagram"
                    if release_state
                    == "ready"
                    else
                    "mdi:alert-decagram"
                ),
        },
    )


@service
def ai_energy_v11_release_check():
    if not _public_ready():
        return {"status": "configuration_required"}

    _release_check(
        "manual"
    )


@service
def ai_energy_v11_refresh_market_now():
    if not _public_ready():
        return {"status": "configuration_required"}

    _market_refresh(
        "manual"
    )


# Begin van nieuwe dag.
@time_trigger(
    "cron(5 0 * * *)"
)
def ai_energy_v11_market_midnight():
    if not _public_ready():
        return {"status": "configuration_required"}

    _market_refresh(
        "scheduled_midnight"
    )


# Rond publicatie van nieuwe day-ahead marktdata.
# We proberen enkele keren zodat een iets late publicatie
# niet betekent dat V11 een hele dag zonder morgenprijzen zit.
@time_trigger(
    "cron(5 13,14,15 * * *)"
)
def ai_energy_v11_market_day_ahead():
    if not _public_ready():
        return {"status": "configuration_required"}

    _market_refresh(
        "scheduled_day_ahead"
    )


# Status iedere 30 minuten bijwerken.
@time_trigger(
    "cron(12,42 * * * *)"
)
def ai_energy_v11_release_monitor():
    if not _public_ready():
        return {"status": "configuration_required"}

    _release_check(
        "scheduled_health"
    )


@time_trigger("startup")
def ai_energy_v11_release_startup():
    if not _public_ready():
        return {"status": "configuration_required"}

    state.set(
        "sensor.ai_energy_v11_release",
        "warming_up",
        {
            "friendly_name":
                "AI Energy V11 Release",

            "release_version":
                RELEASE_VERSION,

            "core_ready":
                False,

            "market_refresh_schedule":
                "00:05 and 13:05/14:05/15:05",

            "health_schedule":
                "hourly at :12 and :42",

            "weather_learning":
                "collecting_training_data",

            "icon":
                "mdi:progress-wrench",
        },
    )

    state.set(
        "sensor.ai_energy_v11_market_refresh",
        "idle",
        {
            "friendly_name":
                "AI Energy V11 Market Refresh",

            "release_version":
                RELEASE_VERSION,

            "icon":
                "mdi:transmission-tower-import",
        },
    )
