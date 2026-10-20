import sys
from datetime import datetime, timedelta


VERSION = "11.2.1-bridge"


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


def _today_local():
    return (
        datetime.now()
        .astimezone()
        .date()
    )


def _get_all_attrs(
    entity_id
):
    try:
        attrs = state.getattr(
            entity_id
        )

        if isinstance(
            attrs,
            dict,
        ):
            return attrs

        return {}

    except Exception:
        return {}


def _fetch_nordpool_date(
    requested
):
    public_config.require_nordpool_config()

    response = service.call(
        "nordpool",
        "get_prices_for_date",

        blocking=True,
        return_response=True,

        config_entry=
            ai_energy_v11.NORDPOOL_CONFIG_ENTRY,

        date=
            requested,

        areas=[
            ai_energy_v11.NORDPOOL_AREA
        ],

        currency=
            ai_energy_v11.NORDPOOL_CURRENCY,
    )

    return task.executor(
        ai_energy_v11.store_nordpool_day,
        response,
        requested,
        ai_energy_v11.NORDPOOL_AREA,
    )


@service
def ai_energy_v11_self_test():
    if not _public_ready():
        return {"status": "configuration_required"}

    try:
        result = task.executor(
            ai_energy_v11.self_test
        )

        state.set(
            "sensor.ai_energy_v11_engine_test",
            "ok",
            {
                "friendly_name":
                    "AI Energy V11 Engine Test",

                "bridge_version":
                    VERSION,

                "engine_version":
                    result.get(
                        "version"
                    ),

                "native_python":
                    result.get(
                        "native_python"
                    ),

                "lambda_test":
                    result.get(
                        "lambda_test"
                    ),

                "generator_test":
                    result.get(
                        "generator_test"
                    ),

                "file_io_test":
                    result.get(
                        "file_io_test"
                    ),

                "test_file":
                    result.get(
                        "test_file"
                    ),

                "timestamp_utc":
                    result.get(
                        "timestamp_utc"
                    ),

                "icon":
                    "mdi:brain",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_engine_test",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Engine Test",

                "bridge_version":
                    VERSION,

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )

        raise


@service
def ai_energy_v11_market_test():
    if not _public_ready():
        return {"status": "configuration_required"}

    input_data = {
        "entsoe_current":
            state.get(
                public_config.ENTITIES['entsoe_current']
            ),

        "nordpool_current":
            state.get(
                public_config.ENTITIES['nordpool_current']
            ),
    }

    try:
        result = task.executor(
            ai_energy_v11.build_market_status,
            input_data,
        )

        market_price = (
            result.get(
                "market_price_eur_kwh"
            )
        )

        if market_price is None:
            market_price = "unknown"

        state.set(
            "sensor.ai_energy_v11_market_source",
            result.get(
                "source"
            ),
            {
                "friendly_name":
                    "AI Energy V11 Marktbron",

                "quality":
                    result.get(
                        "quality"
                    ),

                "agreement":
                    result.get(
                        "agreement"
                    ),

                "difference_cent_kwh":
                    result.get(
                        "difference_cent_kwh"
                    ),

                "entsoe_price_eur_kwh":
                    result.get(
                        "entsoe_price_eur_kwh"
                    ),

                "nordpool_price_eur_kwh":
                    result.get(
                        "nordpool_price_eur_kwh"
                    ),

                "learning_allowed":
                    result.get(
                        "learning_allowed"
                    ),

                "engine_version":
                    result.get(
                        "version"
                    ),

                "timestamp_utc":
                    result.get(
                        "timestamp_utc"
                    ),

                "icon":
                    "mdi:source-branch",
            },
        )

        state.set(
            "sensor.ai_energy_v11_market_price",
            market_price,
            {
                "friendly_name":
                    "AI Energy V11 Marktprijs",

                "unit_of_measurement":
                    "€/kWh",

                "source":
                    result.get(
                        "source"
                    ),

                "quality":
                    result.get(
                        "quality"
                    ),

                "icon":
                    "mdi:transmission-tower",
            },
        )

        state.set(
            "sensor.ai_energy_v11_market_quality",
            result.get(
                "quality"
            ),
            {
                "friendly_name":
                    "AI Energy V11 Marktkwaliteit",

                "unit_of_measurement":
                    "%",

                "agreement":
                    result.get(
                        "agreement"
                    ),

                "learning_allowed":
                    result.get(
                        "learning_allowed"
                    ),

                "icon":
                    "mdi:shield-check",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_market_source",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Marktbron",

                "bridge_version":
                    VERSION,

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )

        raise


@service
def ai_energy_v11_nordpool_fetch(
    date=None
):
    if not _public_ready():
        return {"status": "configuration_required"}

    if date is None:
        requested = (
            _today_local()
            .isoformat()
        )

    else:
        requested = str(
            date
        ).strip()

    if not service.has_service(
        "nordpool",
        "get_prices_for_date",
    ):
        state.set(
            "sensor.ai_energy_v11_nordpool",
            "service_missing",
            {
                "friendly_name":
                    "AI Energy V11 Nord Pool",

                "bridge_version":
                    VERSION,

                "requested_date":
                    requested,

                "message":
                    "Nord Pool get_prices_for_date action ontbreekt.",

                "icon":
                    "mdi:alert-circle",
            },
        )

        return

    try:
        result = (
            _fetch_nordpool_date(
                requested
            )
        )

        state.set(
            "sensor.ai_energy_v11_nordpool",
            result.get(
                "status"
            ),
            {
                "friendly_name":
                    "AI Energy V11 Nord Pool",

                "bridge_version":
                    VERSION,

                "market_version":
                    result.get(
                        "version"
                    ),

                "requested_date":
                    result.get(
                        "requested_date"
                    ),

                "area":
                    result.get(
                        "area"
                    ),

                "currency":
                    result.get(
                        "currency"
                    ),

                "raw_rows":
                    result.get(
                        "raw_rows"
                    ),

                "valid_slots":
                    result.get(
                        "valid_slots"
                    ),

                "invalid_rows":
                    result.get(
                        "invalid_rows"
                    ),

                "expected_slots":
                    result.get(
                        "expected_slots"
                    ),

                "complete_day":
                    result.get(
                        "complete_day"
                    ),

                "interval_minutes":
                    result.get(
                        "detected_interval_minutes"
                    ),

                "min_price_eur_kwh":
                    result.get(
                        "min_price_eur_kwh"
                    ),

                "max_price_eur_kwh":
                    result.get(
                        "max_price_eur_kwh"
                    ),

                "avg_price_eur_kwh":
                    result.get(
                        "avg_price_eur_kwh"
                    ),

                "payload_hash":
                    result.get(
                        "payload_hash"
                    ),

                "file":
                    result.get(
                        "file"
                    ),

                "icon":
                    "mdi:transmission-tower",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_nordpool",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 Nord Pool",

                "bridge_version":
                    VERSION,

                "requested_date":
                    requested,

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )

        raise


@service
def ai_energy_v11_nordpool_refresh():
    if not _public_ready():
        return {"status": "configuration_required"}

    if not service.has_service(
        "nordpool",
        "get_prices_for_date",
    ):
        state.set(
            "sensor.ai_energy_v11_nordpool_refresh",
            "service_missing",
            {
                "friendly_name":
                    "AI Energy V11 Nord Pool Refresh",

                "bridge_version":
                    VERSION,

                "icon":
                    "mdi:alert-circle",
            },
        )

        return

    today = _today_local()

    today_text = (
        today.isoformat()
    )

    tomorrow = (
        today
        + timedelta(days=1)
    )

    tomorrow_text = (
        tomorrow.isoformat()
    )

    tomorrow_state = state.get(
        public_config.ENTITIES['nordpool_tomorrow_available']
    )

    tomorrow_available = False

    if tomorrow_state is not None:
        text = str(
            tomorrow_state
        ).strip().lower()

        if text in (
            "on",
            "true",
            "1",
            "yes",
        ):
            tomorrow_available = True

    today_result = None
    tomorrow_result = None

    errors = []

    try:
        today_result = (
            _fetch_nordpool_date(
                today_text
            )
        )

    except Exception as err:
        errors.append(
            "today: "
            + str(err)
        )

    if tomorrow_available:
        try:
            tomorrow_result = (
                _fetch_nordpool_date(
                    tomorrow_text
                )
            )

        except Exception as err:
            errors.append(
                "tomorrow: "
                + str(err)
            )

    today_ok = False

    if isinstance(
        today_result,
        dict,
    ):
        today_ok = (
            today_result.get(
                "complete_day"
            )
            is True
        )

    tomorrow_ok = False

    if isinstance(
        tomorrow_result,
        dict,
    ):
        tomorrow_ok = (
            tomorrow_result.get(
                "complete_day"
            )
            is True
        )

    status = "ok"

    if not today_ok:
        status = "partial"

    if errors:
        status = "error"

    state.set(
        "sensor.ai_energy_v11_nordpool_refresh",
        status,
        {
            "friendly_name":
                "AI Energy V11 Nord Pool Refresh",

            "bridge_version":
                VERSION,

            "today":
                today_text,

            "today_ok":
                today_ok,

            "today_slots":
                (
                    today_result.get(
                        "valid_slots"
                    )
                    if isinstance(
                        today_result,
                        dict,
                    )
                    else 0
                ),

            "today_file":
                (
                    today_result.get(
                        "file"
                    )
                    if isinstance(
                        today_result,
                        dict,
                    )
                    else None
                ),

            "tomorrow":
                tomorrow_text,

            "tomorrow_available":
                tomorrow_available,

            "tomorrow_ok":
                tomorrow_ok,

            "tomorrow_slots":
                (
                    tomorrow_result.get(
                        "valid_slots"
                    )
                    if isinstance(
                        tomorrow_result,
                        dict,
                    )
                    else 0
                ),

            "tomorrow_file":
                (
                    tomorrow_result.get(
                        "file"
                    )
                    if isinstance(
                        tomorrow_result,
                        dict,
                    )
                    else None
                ),

            "errors":
                errors,

            "icon":
                "mdi:calendar-sync",
        },
    )


@service
def ai_energy_v11_entsoe_refresh():
    if not _public_ready():
        return {"status": "configuration_required"}

    entity_id = (
        ai_energy_v11.ENTITIES[
            "entsoe_average"
        ]
    )

    attrs = _get_all_attrs(
        entity_id
    )

    prices = attrs.get(
        "prices"
    )

    unit = attrs.get(
        "unit_of_measurement"
    )

    payload = {
        "entity_id":
            entity_id,

        "state":
            state.get(
                entity_id
            ),

        "unit_of_measurement":
            unit,

        "prices":
            prices,
    }

    try:
        result = task.executor(
            ai_energy_v11.store_entsoe_prices,
            payload,
        )

        state.set(
            "sensor.ai_energy_v11_entsoe",
            result.get(
                "status"
            ),
            {
                "friendly_name":
                    "AI Energy V11 ENTSO-E",

                "bridge_version":
                    VERSION,

                "entsoe_version":
                    result.get(
                        "version"
                    ),

                "entity_id":
                    entity_id,

                "source_unit":
                    result.get(
                        "source_unit"
                    ),

                "total_items":
                    result.get(
                        "total_items"
                    ),

                "valid_slots":
                    result.get(
                        "valid_slots"
                    ),

                "invalid_items":
                    result.get(
                        "invalid_items"
                    ),

                "interval_minutes":
                    result.get(
                        "detected_interval_minutes"
                    ),

                "source_resolution":
                    result.get(
                        "source_resolution"
                    ),

                "conversion_modes":
                    result.get(
                        "conversion_modes"
                    ),

                "dates":
                    result.get(
                        "dates"
                    ),

                "files":
                    result.get(
                        "files"
                    ),

                "icon":
                    "mdi:transmission-tower-import",
            },
        )

    except Exception as err:
        state.set(
            "sensor.ai_energy_v11_entsoe",
            "error",
            {
                "friendly_name":
                    "AI Energy V11 ENTSO-E",

                "bridge_version":
                    VERSION,

                "entity_id":
                    entity_id,

                "error":
                    str(err),

                "icon":
                    "mdi:alert-circle",
            },
        )

        raise


@service
def ai_energy_v11_nordpool_backfill(
    start_date=None,
    end_date=None,
    max_days=14,
):
    if not _public_ready():
        return {"status": "configuration_required"}

    if not service.has_service(
        "nordpool",
        "get_prices_for_date",
    ):
        state.set(
            "sensor.ai_energy_v11_nordpool_backfill",
            "service_missing",
            {
                "friendly_name":
                    "AI Energy V11 Nord Pool Backfill",

                "bridge_version":
                    VERSION,

                "icon":
                    "mdi:alert-circle",
            },
        )

        return

    plan = task.executor(
        ai_energy_v11.build_nordpool_backfill_plan,
        start_date,
        end_date,
        max_days,
    )

    planned_dates = (
        plan.get(
            "planned_dates",
            [],
        )
    )

    fetch_results = []

    for requested in planned_dates:
        try:
            result = (
                _fetch_nordpool_date(
                    requested
                )
            )

            fetch_results.append(
                {
                    "date":
                        requested,

                    "status":
                        result.get(
                            "status"
                        ),

                    "complete_day":
                        result.get(
                            "complete_day"
                        ),

                    "valid_slots":
                        result.get(
                            "valid_slots"
                        ),

                    "expected_slots":
                        result.get(
                            "expected_slots"
                        ),

                    "file":
                        result.get(
                            "file"
                        ),
                }
            )

        except Exception as err:
            fetch_results.append(
                {
                    "date":
                        requested,

                    "status":
                        "error",

                    "complete_day":
                        False,

                    "error":
                        str(err),
                }
            )

    summary = task.executor(
        ai_energy_v11.finalize_nordpool_backfill,
        plan,
        fetch_results,
    )

    state.set(
        "sensor.ai_energy_v11_nordpool_backfill",
        summary.get(
            "status"
        ),
        {
            "friendly_name":
                "AI Energy V11 Nord Pool Backfill",

            "bridge_version":
                VERSION,

            "backfill_version":
                summary.get(
                    "version"
                ),

            "start_date":
                summary.get(
                    "start_date"
                ),

            "end_date":
                summary.get(
                    "end_date"
                ),

            "total_days":
                summary.get(
                    "total_days"
                ),

            "existing_complete_before":
                summary.get(
                    "existing_complete_before"
                ),

            "planned":
                summary.get(
                    "planned"
                ),

            "successful":
                summary.get(
                    "successful"
                ),

            "failed":
                summary.get(
                    "failed"
                ),

            "slots_stored":
                summary.get(
                    "slots_stored"
                ),

            "remaining":
                summary.get(
                    "remaining"
                ),

            "next_dates":
                summary.get(
                    "next_dates"
                ),

            "report_file":
                summary.get(
                    "report_file"
                ),

            "icon":
                "mdi:database-sync",
        },
    )
