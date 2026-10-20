import sys


BRIDGE_VERSION = "11.5.3-hourly-forecast-publisher"


if "/config/pyscript_modules" not in sys.path:
    sys.path.append(
        "/config/pyscript_modules"
    )


import ai_energy_v11
from ai_energy_v11 import config as public_config


WEATHER_CANDIDATES = public_config.WEATHER_ENTITIES


def _public_ready():
    """Fresh installs are inert until local settings explicitly enable the suite."""
    if public_config.ENABLED:
        return True
    state.set("sensor.ai_energy_v11_setup", "configuration_required", {
        "friendly_name": "AI Energy setup",
        "message": "Fill local settings.json and explicitly set enabled to true, then restart Pyscript.",
    })
    return False


def _entity_exists(
    entity_id,
):
    try:
        value = state.get(
            entity_id
        )

        return value is not None

    except Exception:
        return False


def _find_weather_entity(
    requested=None,
):
    if requested:
        if _entity_exists(
            requested
        ):
            return requested

    for entity_id in (
        WEATHER_CANDIDATES
    ):
        if _entity_exists(
            entity_id
        ):
            return entity_id

    return None


def _get_weather_attributes(
    entity_id,
):
    if not entity_id:
        return {}

    try:
        attributes = state.getattr(
            entity_id
        )

        if isinstance(
            attributes,
            dict,
        ):
            return attributes

    except Exception:
        pass

    return {}


def _get_weather_state(
    entity_id,
):
    if not entity_id:
        return None

    try:
        return state.get(
            entity_id
        )

    except Exception:
        return None


def _get_forecast(
    entity_id,
    forecast_type,
):
    if not entity_id:
        return (
            None,
            "weather entity not found",
        )

    try:
        response = service.call(
            "weather",
            "get_forecasts",
            blocking=True,
            return_response=True,
            entity_id=entity_id,
            type=forecast_type,
        )

        return (
            response,
            None,
        )

    except Exception as err:
        return (
            None,
            str(err),
        )


def _publish_ledger(
    result,
    reason,
):
    state.set(
        "sensor.ai_energy_v11_forecast_ledger",
        result.get(
            "status",
            "unknown",
        ),
        {
            "friendly_name":
                "AI Energy V11 Forecast Ledger",

            "bridge_version":
                BRIDGE_VERSION,

            "ledger_version":
                result.get(
                    "version"
                ),

            "reason":
                reason,

            "capture_mode":
                result.get(
                    "capture_mode"
                ),

            "issue_time_local":
                result.get(
                    "issue_time_local"
                ),

            "market_model":
                result.get(
                    "market_model"
                ),

            "market_baseline_slots":
                result.get(
                    "market_baseline_slots"
                ),

            "known_market_slots":
                result.get(
                    "known_market_slots"
                ),

            "weather_entity":
                result.get(
                    "weather_entity"
                ),

            "weather_hourly_slots":
                result.get(
                    "weather_hourly_slots"
                ),

            "weather_hourly_horizon_hours":
                result.get(
                    "weather_hourly_horizon_hours"
                ),

            "weather_daily_slots":
                result.get(
                    "weather_daily_slots"
                ),

            "weather_daily_horizon_hours":
                result.get(
                    "weather_daily_horizon_hours"
                ),

            "weather_hourly_error":
                result.get(
                    "weather_hourly_error"
                ),

            "weather_daily_error":
                result.get(
                    "weather_daily_error"
                ),

            "archive_file":
                result.get(
                    "archive_file"
                ),

            "latest_file":
                result.get(
                    "latest_file"
                ),

            "icon":
                "mdi:database-eye",
        },
    )


def _publish_forecast(
    result,
):
    cheapest = result.get(
        "cheapest_12_quarters",
        [],
    )

    cheapest_first = None

    if (
        isinstance(
            cheapest,
            list,
        )
        and cheapest
    ):
        cheapest_first = cheapest[0]

    if not isinstance(
        cheapest_first,
        dict,
    ):
        cheapest_first = {}

    known_slots = (
        result.get(
            "known_market_slots"
        )
        or 0
    )

    ai_slots = (
        result.get(
            "ai_market_slots"
        )
        or 0
    )

    total_slots = (
        known_slots
        + ai_slots
    )

    known_pct = 0.0

    if total_slots > 0:
        known_pct = (
            known_slots
            / total_slots
            * 100
        )

    state.set(
        "sensor.ai_energy_v11_forecast_96h",
        result.get(
            "status",
            "unknown",
        ),
        {
            "friendly_name":
                "AI Energy V11 Forecast 96h",

            "bridge_version":
                BRIDGE_VERSION,

            "composer_version":
                result.get(
                    "version"
                ),

            "slots":
                result.get(
                    "slots"
                ),

            "known_market_slots":
                known_slots,

            "ai_market_slots":
                ai_slots,

            "known_market_pct":
                round(
                    known_pct,
                    1,
                ),

            "market_model":
                result.get(
                    "market_baseline_model"
                ),

            "retail_model":
                result.get(
                    "retail_model"
                ),

            "market_min_cent_kwh":
                result.get(
                    "market_min_cent_kwh"
                ),

            "market_avg_cent_kwh":
                result.get(
                    "market_avg_cent_kwh"
                ),

            "market_max_cent_kwh":
                result.get(
                    "market_max_cent_kwh"
                ),

            "retail_min_cent_kwh":
                result.get(
                    "retail_min_cent_kwh"
                ),

            "retail_avg_cent_kwh":
                result.get(
                    "retail_avg_cent_kwh"
                ),

            "retail_max_cent_kwh":
                result.get(
                    "retail_max_cent_kwh"
                ),

            "retail_model_mae_cent_kwh":
                result.get(
                    "retail_expected_mae_cent_kwh"
                ),

            "cheapest_timestamp":
                cheapest_first.get(
                    "timestamp_local"
                ),

            "cheapest_price_cent_kwh":
                cheapest_first.get(
                    "retail_price_cent_kwh"
                ),

            "cheapest_market_source":
                cheapest_first.get(
                    "market_source"
                ),

            "cheapest_12_quarters":
                cheapest,

            "output_file":
                result.get(
                    "output_file"
                ),

            "icon":
                "mdi:chart-timeline-variant-shimmer",
        },
    )


def _run_cycle(
    reason,
    weather_entity=None,
):
    selected_weather = (
        _find_weather_entity(
            weather_entity
        )
    )

    (
        hourly_response,
        hourly_error,
    ) = _get_forecast(
        selected_weather,
        "hourly",
    )

    (
        daily_response,
        daily_error,
    ) = _get_forecast(
        selected_weather,
        "daily",
    )

    payload = {
        "reason":
            reason,

        "weather_entity":
            selected_weather,

        "weather_state":
            _get_weather_state(
                selected_weather
            ),

        "weather_attributes":
            _get_weather_attributes(
                selected_weather
            ),

        "weather_hourly_response":
            hourly_response,

        "weather_daily_response":
            daily_response,

        "weather_hourly_error":
            hourly_error,

        "weather_daily_error":
            daily_error,
    }

    ledger_result = task.executor(
        ai_energy_v11.capture_forecast_inputs,
        payload,
    )

    _publish_ledger(
        ledger_result,
        reason,
    )

    forecast_result = task.executor(
        ai_energy_v11.build_end_to_end_forecast
    )

    _publish_forecast(
        forecast_result
    )

    return {
        "ledger":
            ledger_result,

        "forecast":
            forecast_result,
    }


@service
def ai_energy_v11_forecast_cycle(
    weather_entity=None,
):
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        _run_cycle(
            "manual",
            weather_entity,
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_forecast_96h",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Forecast 96h",

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
def ai_energy_v11_capture_forecast_inputs(
    weather_entity=None,
):
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        selected_weather = (
            _find_weather_entity(
                weather_entity
            )
        )

        (
            hourly_response,
            hourly_error,
        ) = _get_forecast(
            selected_weather,
            "hourly",
        )

        (
            daily_response,
            daily_error,
        ) = _get_forecast(
            selected_weather,
            "daily",
        )

        payload = {
            "reason":
                "manual_ledger_only",

            "weather_entity":
                selected_weather,

            "weather_state":
                _get_weather_state(
                    selected_weather
                ),

            "weather_attributes":
                _get_weather_attributes(
                    selected_weather
                ),

            "weather_hourly_response":
                hourly_response,

            "weather_daily_response":
                daily_response,

            "weather_hourly_error":
                hourly_error,

            "weather_daily_error":
                daily_error,
        }

        result = task.executor(
            ai_energy_v11.capture_forecast_inputs,
            payload,
        )

        _publish_ledger(
            result,
            "manual_ledger_only",
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_forecast_ledger",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Forecast Ledger",

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
def ai_energy_v11_forecast_ledger_test():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            ai_energy_v11.forecast_ledger_self_test
        )

        state.set(
            "sensor.ai_energy_v11_forecast_ledger_test",
            result.get(
                "status",
                "unknown",
            ),
            {
                "friendly_name":
                    "AI Energy V11 Forecast Ledger Test",

                "bridge_version":
                    BRIDGE_VERSION,

                "ledger_version":
                    result.get(
                        "version"
                    ),

                "weather_rows":
                    result.get(
                        "weather_rows"
                    ),

                "market_start_utc_parsed":
                    result.get(
                        "market_start_utc_parsed"
                    ),

                "market_price_eur_kwh":
                    result.get(
                        "market_price_eur_kwh"
                    ),

                "icon":
                    "mdi:test-tube",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_forecast_ledger_test",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Forecast Ledger Test",

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
    "cron(8 * * * *)"
)
def ai_energy_v11_forecast_schedule():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        _run_cycle(
            "scheduled_hourly"
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_forecast_96h",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Forecast 96h",

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
def ai_energy_v11_forecast_startup():
    if not _public_ready():
        return {"status": "configuration_required"}

    state.set(
        "sensor.ai_energy_v11_forecast_ledger",
        "idle",
        {
            "friendly_name":
                "AI Energy V11 Forecast Ledger",

            "bridge_version":
                BRIDGE_VERSION,

            "ledger_version":
                ai_energy_v11.FORECAST_LEDGER_VERSION,

            "schedule":
                "hourly at :08",

            "startup_collection":
                False,

            "icon":
                "mdi:database-eye",
        },
    )

    state.set(
        "sensor.ai_energy_v11_forecast_96h",
        "idle",
        {
            "friendly_name":
                "AI Energy V11 Forecast 96h",

            "bridge_version":
                BRIDGE_VERSION,

            "schedule":
                "hourly at :08",

            "startup_collection":
                False,

            "icon":
                "mdi:chart-timeline-variant-shimmer",
        },
    )
