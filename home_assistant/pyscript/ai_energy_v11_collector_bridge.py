import sys
from importlib import reload as reload_module
from datetime import datetime


BRIDGE_VERSION = "11.4.1-quarter-hour-collector-bridge"


if "/config/pyscript_modules" not in sys.path:
    sys.path.append(
        "/config/pyscript_modules"
    )


import ai_energy_v11
import ai_energy_v11.collector as collector_engine
from ai_energy_v11 import config as public_config


ZONNEPLAN_PRICE = (
    public_config.ENTITIES['zonneplan_quarter_hourly']
)

NORDPOOL_PRICE = (
    public_config.ENTITIES['nordpool_current']
)

ENTSOE_PRICE = (
    public_config.ENTITIES['entsoe_current']
)

TEMPERATURE = (
    public_config.ENTITIES['temperature']
)

WIND_SPEED = (
    public_config.ENTITIES['wind_speed']
)

WIND_DIRECTION = (
    public_config.ENTITIES['wind_direction']
)

CLOUD_COVER = (
    public_config.ENTITIES['cloud_cover']
)

HUMIDITY = (
    public_config.ENTITIES['humidity']
)

PRESSURE = (
    public_config.ENTITIES['pressure']
)

PV_ACTUAL = (
    public_config.ENTITIES['pv_actual']
)

P1_POWER = (
    public_config.ENTITIES['p1_power']
)

GOLF_STATE = (
    public_config.ENTITIES['golf_active']
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


def _get_state(
    entity_id
):
    try:
        return state.get(
            entity_id
        )

    except Exception:
        return None


def _build_payload(
    reason
):
    return {
        "captured_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "collection_reason":
            reason,

        "actual_price_resolution": "quarter_hour",
        "actual_price_source": ZONNEPLAN_PRICE,
        "zonneplan_price":
            _get_state(
                ZONNEPLAN_PRICE
            ),

        "nordpool_price":
            _get_state(
                NORDPOOL_PRICE
            ),

        "entsoe_price":
            _get_state(
                ENTSOE_PRICE
            ),

        "temperature":
            _get_state(
                TEMPERATURE
            ),

        "wind_speed":
            _get_state(
                WIND_SPEED
            ),

        "wind_direction":
            _get_state(
                WIND_DIRECTION
            ),

        "cloud_cover":
            _get_state(
                CLOUD_COVER
            ),

        "humidity":
            _get_state(
                HUMIDITY
            ),

        "pressure":
            _get_state(
                PRESSURE
            ),

        "pv_actual":
            _get_state(
                PV_ACTUAL
            ),

        "p1_power":
            _get_state(
                P1_POWER
            ),

        "golf_state":
            _get_state(
                GOLF_STATE
            ),
    }


def _publish_result(
    result
):
    state.set(
        "sensor.ai_energy_v11_collector",
        result.get(
            "status",
            "unknown",
        ),
        {
            "friendly_name":
                "AI Energy V11 Collector",

            "bridge_version":
                BRIDGE_VERSION,
            "actual_price_resolution": "quarter_hour",
            "actual_price_source": ZONNEPLAN_PRICE,

            "collector_version":
                result.get(
                    "version"
                ),

            "captured_at":
                result.get(
                    "captured_at"
                ),

            "slot_start_local":
                result.get(
                    "slot_start_local"
                ),

            "slot_start_utc":
                result.get(
                    "slot_start_utc"
                ),

            "delivery_date":
                result.get(
                    "delivery_date"
                ),

            "collection_reason":
                result.get(
                    "collection_reason"
                ),

            "replaced_existing":
                result.get(
                    "replaced_existing"
                ),

            "rows_today":
                result.get(
                    "rows_today"
                ),

            "collection_quality_pct":
                result.get(
                    "collection_quality_pct"
                ),

            "market_quality_pct":
                result.get(
                    "market_quality_pct"
                ),

            "price_learning_eligible":
                result.get(
                    "price_learning_eligible"
                ),

            "weather_learning_eligible":
                result.get(
                    "weather_learning_eligible"
                ),

            "energy_learning_eligible":
                result.get(
                    "energy_learning_eligible"
                ),

            "zonneplan_price_eur_kwh":
                result.get(
                    "zonneplan_price_eur_kwh"
                ),

            "market_price_eur_kwh":
                result.get(
                    "market_price_eur_kwh"
                ),

            "market_source":
                result.get(
                    "market_source"
                ),

            "retail_margin_eur_kwh":
                result.get(
                    "retail_margin_eur_kwh"
                ),

            "pv_actual_w":
                result.get(
                    "pv_actual_w"
                ),

            "p1_power_w":
                result.get(
                    "p1_power_w"
                ),

            "file":
                result.get(
                    "file"
                ),

            "icon":
                "mdi:database-clock",
        },
    )


def _run_collection(
    reason
):
    try:
        payload = (
            _build_payload(
                reason
            )
        )

        result = task.executor(
            collector_engine.store_live_snapshot,
            payload,
        )

        _publish_result(
            result
        )

        return result

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_collector",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Collector",

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
def ai_energy_v11_collect_now():
    if not _public_ready():
        return {"status": "configuration_required"}

    _run_collection(
        "manual"
    )


@service
def ai_energy_v11_collector_test():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            collector_engine.collector_self_test
        )

        state.set(
            "sensor.ai_energy_v11_collector_test",
            result.get(
                "status"
            ),
            {
                "friendly_name":
                    "AI Energy V11 Collector Test",

                "bridge_version":
                    BRIDGE_VERSION,

                "collector_version":
                    result.get(
                        "version"
                    ),

                "slot_start_local":
                    result.get(
                        "slot_start_local"
                    ),

                "market_source":
                    result.get(
                        "market_source"
                    ),

                "quality":
                    result.get(
                        "quality"
                    ),

                "icon":
                    "mdi:test-tube",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_collector_test",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Collector Test",

                "bridge_version":
                    BRIDGE_VERSION,

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )

        raise


@time_trigger("startup")
def ai_energy_v11_collector_startup():
    if not _public_ready():
        return {"status": "configuration_required"}

    task.executor(reload_module, collector_engine)
    # The normal :02/:17/:32/:47 schedule continues. Preserve the last sensor
    # until a real quarter-hour observation is collected.


@time_trigger(
    "cron(2,17,32,47 * * * *)"
)
def ai_energy_v11_collect_scheduled():
    if not _public_ready():
        return {"status": "configuration_required"}

    _run_collection(
        "scheduled_15min"
    )
