"""Local configuration; no household identifiers or private trained data shipped.

Copy examples/settings.example.json to /config/ai_energy_v11/settings.json and
edit it locally. AI_ENERGY_ROOT selects a different private storage/settings root.
Settings are loaded when native Python imports this module; restart Pyscript
after changing them. Missing settings leave every HA bridge disabled.
"""
from copy import deepcopy
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
import os
import re

CONFIG_VERSION = "11.1.0-public-local-settings"
ROOT_DIR = Path(os.environ.get("AI_ENERGY_ROOT", "/config/ai_energy_v11")).expanduser().resolve()
SETTINGS_PATH = ROOT_DIR / "settings.json"

_ENTITY_KEYS = (
    "zonneplan_current", "zonneplan_quarter_hourly", "entsoe_current", "entsoe_average",
    "nordpool_current", "nordpool_previous", "nordpool_next", "nordpool_low",
    "nordpool_high", "nordpool_average", "nordpool_last_updated", "nordpool_tomorrow_available",
    "temperature", "wind_speed", "wind_direction", "wind_gust", "cloud_cover",
    "humidity", "pressure", "rain_intensity", "pv_actual", "pv_ai_actual",
    "solcast_now", "solcast_today", "solcast_tomorrow", "solcast_this_hour",
    "p1_power", "p1_import_total", "p1_export_total", "golf_active",
)
_DEFAULT_ENTITIES = {key: "sensor.example_" + key for key in _ENTITY_KEYS}
_DEFAULT_ENTITIES["nordpool_tomorrow_available"] = "binary_sensor.example_nordpool_tomorrow_available"
_DEFAULT_ENTITIES["golf_active"] = "binary_sensor.example_compute_busy"
DEFAULT_SETTINGS = {
    "enabled": False,
    "timezone": "Europe/Amsterdam",
    "nordpool": {"config_entry": "", "area": "NL", "currency": "EUR"},
    "entities": _DEFAULT_ENTITIES,
    "weather_entities": [],
    "legacy_base_dir": "",
}


def validate_settings(payload):
    """Validate JSON settings and return an independent, complete mapping.

    This checks syntax and required mappings, not HA entity availability.
    """
    if not isinstance(payload, dict):
        raise ValueError("settings.json must contain a JSON object")
    unknown = set(payload) - set(DEFAULT_SETTINGS)
    if unknown:
        raise ValueError("Unknown settings keys: " + ", ".join(sorted(unknown)))
    result = deepcopy(DEFAULT_SETTINGS)
    for key in ("enabled", "timezone", "weather_entities", "legacy_base_dir"):
        if key in payload:
            result[key] = deepcopy(payload[key])
    for key, allowed in (("entities", set(_ENTITY_KEYS)), ("nordpool", {"config_entry", "area", "currency"})):
        overrides = payload.get(key, {})
        if not isinstance(overrides, dict):
            raise ValueError(key + " must be an object")
        if set(overrides) - allowed:
            raise ValueError("Unknown " + key + " keys: " + ", ".join(sorted(set(overrides) - allowed)))
        result[key].update(overrides)
    if not isinstance(result["enabled"], bool):
        raise ValueError("enabled must be true or false")
    if not isinstance(result["timezone"], str):
        raise ValueError("timezone must be an IANA timezone string")
    try:
        ZoneInfo(result["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("timezone is not an available IANA timezone") from None
    for key, value in result["entities"].items():
        if not isinstance(value, str) or (value and not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", value)):
            raise ValueError("entities." + key + " must be an entity ID or an empty string")
    weather = result["weather_entities"]
    if not isinstance(weather, list) or any(not isinstance(x, str) or not re.fullmatch(r"weather\.[a-z0-9_]+", x) for x in weather):
        raise ValueError("weather_entities must be a list of weather entity IDs")
    result["weather_entities"] = list(dict.fromkeys(weather))
    for key, value in result["nordpool"].items():
        if not isinstance(value, str):
            raise ValueError("nordpool." + key + " must be a string")
        result["nordpool"][key] = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", result["nordpool"]["area"]):
        raise ValueError("nordpool.area must be a single market area")
    if not re.fullmatch(r"[A-Z]{3}", result["nordpool"]["currency"]):
        raise ValueError("nordpool.currency must be a three-letter uppercase currency code")
    if result["nordpool"]["currency"] != "EUR":
        raise ValueError("This preview uses EUR/kWh internally; currency must be EUR")
    legacy = result["legacy_base_dir"]
    if not isinstance(legacy, str) or (legacy and not Path(legacy).expanduser().is_absolute()):
        raise ValueError("legacy_base_dir must be empty or an absolute local path")
    if result["enabled"]:
        retail = result["entities"]["zonneplan_quarter_hourly"]
        entsoe = result["entities"]["entsoe_average"]
        if not retail or retail.startswith("sensor.example_"):
            raise ValueError("Map entities.zonneplan_quarter_hourly before enabling")
        if not result["nordpool"]["config_entry"] and (not entsoe or entsoe.startswith("sensor.example_")):
            raise ValueError("Configure Nord Pool config_entry or entities.entsoe_average before enabling")
    return result


def load_settings(path=SETTINGS_PATH):
    """Missing local settings are safe defaults; malformed settings fail closed."""
    path = Path(path)
    if not path.exists():
        return validate_settings({})
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Cannot read local settings.json as valid UTF-8 JSON") from None
    return validate_settings(payload)


SETTINGS = load_settings()
ENABLED = SETTINGS["enabled"]
TIMEZONE = SETTINGS["timezone"]
ENTITIES = SETTINGS["entities"]
WEATHER_ENTITIES = tuple(SETTINGS["weather_entities"])
NORDPOOL_AREA = SETTINGS["nordpool"]["area"]
NORDPOOL_CURRENCY = SETTINGS["nordpool"]["currency"]
NORDPOOL_CONFIG_ENTRY = SETTINGS["nordpool"]["config_entry"]


def require_nordpool_config():
    if not NORDPOOL_CONFIG_ENTRY:
        raise ValueError("Nord Pool config_entry is not configured in local settings.json; no request was sent")
    return NORDPOOL_CONFIG_ENTRY


DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
MARKET_DIR = DATA_DIR / "market"
FORECAST_INPUT_DIR = DATA_DIR / "forecast_inputs"
LEGACY_NORMALIZED_DIR = DATA_DIR / "legacy_normalized"
QUARANTINE_DIR = DATA_DIR / "quarantine"
MODEL_DIR = DATA_DIR / "models"
PREDICTION_DIR = DATA_DIR / "predictions"
ACCURACY_DIR = DATA_DIR / "accuracy"
LOG_DIR = DATA_DIR / "logs"
DATA_DIRECTORIES = [RAW_DIR, MARKET_DIR, FORECAST_INPUT_DIR, LEGACY_NORMALIZED_DIR, QUARANTINE_DIR, MODEL_DIR, PREDICTION_DIR, ACCURACY_DIR, LOG_DIR]
# Legacy input is opt-in and read-only; no existing household history is discovered.
LEGACY_BASE_DIR = Path(SETTINGS["legacy_base_dir"]).expanduser() if SETTINGS["legacy_base_dir"] else ROOT_DIR / "legacy_input"
LEGACY_RAW_DIR = LEGACY_BASE_DIR / "data" / "raw"
COLLECT_INTERVAL_MINUTES = 15
