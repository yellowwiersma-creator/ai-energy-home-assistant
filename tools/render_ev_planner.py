#!/usr/bin/env python3
"""Render local mappings for the inactive advanced EV recipe. Never enables it."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RECIPE_PATH = REPO_ROOT / "home_assistant" / "optional" / "ev_planner.yaml"
ROLES_PATH = RECIPE_PATH.with_name("ev_roles.json")
MASTER = "input_boolean.ai_energy_actuation_enabled"
GATE = "{{ is_state('input_boolean.ai_energy_actuation_enabled', 'on') }}"
ALLOWED_SETTINGS = {
    "schema_version", "entities", "device_ids", "calendar_keywords",
    "expected_charging_power_kw", "kwh_per_soc_percent",
}
ENTITY_PATTERN = re.compile(r"[a-z][a-z0-9_]*\.[a-z0-9_]+\Z")


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("The EV recipe must be a YAML mapping.")
    return value


def _gate_in_conditions(conditions: Any) -> bool:
    if isinstance(conditions, list):
        return any(_gate_in_conditions(value) for value in conditions)
    return isinstance(conditions, dict) and conditions.get("condition") == "template" and conditions.get("value_template") == GATE


def verify_inactive_recipe(package: dict[str, Any]) -> int:
    """Reject an enabled or unguarded recipe, including nested script call paths."""
    if package.get("input_boolean", {}).get("ai_energy_actuation_enabled", {}).get("initial") is not False:
        raise ValueError("The advanced recipe master must initialize OFF.")
    automations = package.get("automation", [])
    if len(automations) != 33 or any(item.get("initial_state") is not False for item in automations):
        raise ValueError("All 33 advanced recipe automations must remain disabled.")
    if any(not _gate_in_conditions(item.get("conditions")) for item in automations):
        raise ValueError("Every automation must retain its master condition.")
    for script in package.get("script", {}).values():
        if not script.get("sequence") or not _gate_in_conditions(script["sequence"][0]):
            raise ValueError("Every script must check the master before running.")
    calls = 0

    def walk(node: Any, authorized: bool = False) -> None:
        nonlocal calls
        if isinstance(node, list):
            for child in node:
                walk(child, authorized)
        elif isinstance(node, dict):
            if isinstance(node.get("action", node.get("service")), str):
                calls += 1
                if not authorized:
                    raise ValueError("A service call is missing its immediate master check.")
            guarded_then = _gate_in_conditions(node.get("if"))
            for key, value in node.items():
                # Authorization applies to a direct call in this then-list. It
                # must not leak through a wait/choose/sequence to a later call.
                walk(value, key == "then" and guarded_then)

    walk(package)
    if calls != 238:
        raise ValueError("The full advanced recipe must retain all 238 guarded service calls.")
    return calls


def _finite_number(value: Any, *, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be a finite number between {minimum} and {maximum}.")
    return float(value)


def render(settings: dict[str, Any], *, recipe_path: Path = RECIPE_PATH, roles_path: Path = ROLES_PATH) -> str:
    if not isinstance(settings, dict) or set(settings) - ALLOWED_SETTINGS:
        raise ValueError("Unknown EV settings. This renderer has no activation option.")
    if settings.get("schema_version", 1) != 1:
        raise ValueError("Unsupported EV settings schema_version.")
    manifest = json.loads(roles_path.read_text(encoding="utf-8"))
    mapping = settings.get("entities", {})
    if not isinstance(mapping, dict) or set(mapping) - set(manifest["entities"]):
        raise ValueError("entities must contain only roles from ev_roles.json.")
    replacements: dict[str, str] = {}
    for role, spec in manifest["entities"].items():
        entity = mapping.get(role, spec["placeholder"])
        if not isinstance(entity, str) or not ENTITY_PATTERN.fullmatch(entity) or entity.split(".", 1)[0] != spec["domain"]:
            raise ValueError(f"Invalid entity domain or identifier for role {role}.")
        replacements[spec["placeholder"]] = entity
    device_ids = settings.get("device_ids", {})
    if not isinstance(device_ids, dict) or set(device_ids) - {"vehicle_cloud"}:
        raise ValueError("Only the vehicle_cloud device mapping is supported.")
    device_id = device_ids.get("vehicle_cloud", "__EV_VEHICLE_DEVICE_ID__")
    if not isinstance(device_id, str) or not (device_id == "__EV_VEHICLE_DEVICE_ID__" or re.fullmatch(r"[a-fA-F0-9]{32}", device_id)):
        raise ValueError("vehicle_cloud must be a Home Assistant device ID or the inactive placeholder.")
    keywords = settings.get("calendar_keywords", ["charge", ""])
    if not isinstance(keywords, list) or len(keywords) != 2 or any(not isinstance(word, str) or len(word) > 80 or any(ord(c) < 32 for c in word) for word in keywords):
        raise ValueError("calendar_keywords must contain two short strings; both are AND-matched.")
    power = _finite_number(settings.get("expected_charging_power_kw", 7.2), name="expected_charging_power_kw", minimum=0.1, maximum=100)
    efficiency = _finite_number(settings.get("kwh_per_soc_percent", 0.7), name="kwh_per_soc_percent", minimum=0.01, maximum=10)
    package = copy.deepcopy(load_yaml(recipe_path))
    verify_inactive_recipe(package)
    pattern = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(value) for value in sorted(replacements, key=len, reverse=True)) + r")(?![A-Za-z0-9_])")

    def substitute(node: Any) -> Any:
        if isinstance(node, str):
            value = pattern.sub(lambda match: replacements[match.group(0)], node)
            value = value.replace("__EV_VEHICLE_DEVICE_ID__", device_id)
            for index, keyword in enumerate(keywords, 1):
                # Replace the whole Jinja string literal so quotes remain data.
                value = value.replace(f"'__EV_CALENDAR_KEYWORD_{index}__'", json.dumps(keyword.lower(), ensure_ascii=False))
            return value
        if isinstance(node, list):
            return [substitute(value) for value in node]
        if isinstance(node, dict):
            return {substitute(key): substitute(value) for key, value in node.items()}
        return node

    package = substitute(package)
    package["input_number"]["ai_kia_laadvermogen_verwacht"]["initial"] = power
    package["input_number"]["ai_kia_kwh_per_procent"]["initial"] = efficiency
    verify_inactive_recipe(package)
    return (
        "# Locally rendered advanced EV recipe. Contains local entity mappings.\n"
        "# All automations remain disabled; the master initializes OFF.\n"
        "# No renderer option enables charging, vehicle refreshes or notifications.\n"
        + yaml.safe_dump(package, allow_unicode=True, sort_keys=False, width=110)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=REPO_ROOT / "examples" / "ev-settings.example.json")
    parser.add_argument("--output", type=Path, required=True, help="A new local YAML file; keep real mappings outside the published repository")
    args = parser.parse_args()
    try:
        settings = json.loads(args.settings.read_text(encoding="utf-8"))
        result = render(settings)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as destination:
            destination.write(result)
    except (ValueError, OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        parser.exit(2, f"EV recipe not written: {exc}\n")
    print("Rendered inactive EV recipe: 33 disabled automations and 238 guarded calls. No Home Assistant changes were made.")


if __name__ == "__main__":
    main()
