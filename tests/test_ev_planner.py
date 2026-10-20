"""Controlled examples exercise the published recipe; no Home Assistant access."""
from __future__ import annotations

import ast
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest

from jinja2 import Environment, StrictUndefined
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("render_ev_planner", ROOT / "tools" / "render_ev_planner.py")
renderer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(renderer)
PACKAGE = renderer.load_yaml(renderer.RECIPE_PATH)
BASE = datetime(2030, 1, 10, 0, 0, tzinfo=timezone.utc)


def entity(unique_id):
    return next(item for block in PACKAGE["template"] for domain in ("sensor", "binary_sensor")
                for item in block.get(domain, []) if item.get("unique_id") == unique_id)


def as_timestamp(value, default=0):
    if isinstance(value, (int, float)):
        return value
    try:
        when = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if when.tzinfo is None:
            return default
        return when.timestamp()
    except (ValueError, TypeError, AttributeError):
        return default


def utc(value):
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat().replace("+00:00", "Z")


def is_number(value):
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def render(template, *, states=None, attrs=None, now=BASE):
    states, attrs = states or {}, attrs or {}
    env = Environment(undefined=StrictUndefined)
    env.globals.update(states=lambda key: states.get(key, "unknown"), state_attr=lambda key, attr: attrs.get((key, attr)),
                       is_state=lambda key, value: states.get(key) == value, now=lambda: now,
                       as_timestamp=as_timestamp, is_number=is_number)
    env.filters["timestamp_utc"] = utc
    return env.from_string(template).render().strip()


def slots(prices, starts=None):
    starts = starts or list(range(len(prices)))
    return [{"start": utc((BASE + timedelta(minutes=15 * start)).timestamp()),
             "end": utc((BASE + timedelta(minutes=15 * (start + 1))).timestamp()), "price": price}
            for price, start in zip(prices, starts)]


def forecast_attrs(rows, unit="ct/kWh", interval=15):
    source = "sensor.ai_energy_v11_dashboard_data"
    return {(source, "forecast"): rows, (source, "retail_unit"): unit, (source, "interval_minutes"): interval}


class DisabledRecipeTests(unittest.TestCase):
    def test_complete_recipe_is_inactive_and_all_calls_are_immediately_guarded(self):
        self.assertEqual(renderer.verify_inactive_recipe(PACKAGE), 238)
        self.assertEqual(len(PACKAGE["automation"]), 33)
        self.assertFalse(PACKAGE["input_boolean"]["ai_kia_automatisch_laden_toestaan"]["initial"])

    def test_mutated_recipe_cannot_be_enabled_or_hide_call_below_an_old_gate(self):
        enabled = copy.deepcopy(PACKAGE)
        enabled["automation"][0]["initial_state"] = True
        with self.assertRaisesRegex(ValueError, "disabled"):
            renderer.verify_inactive_recipe(enabled)
        mutated = copy.deepcopy(PACKAGE)
        # A start-time gate followed by a delay is not enough for the later call.
        mutated["script"]["ai_kia_kosten_en_energie_bijwerken"]["sequence"].append({
            "if": [{"condition": "template", "value_template": renderer.GATE}],
            "then": [{"delay": "00:00:01"}, {"choose": [], "default": [{"action": "switch.turn_on", "target": {"entity_id": "switch.example"}}]}],
        })
        with self.assertRaisesRegex(ValueError, "immediate"):
            renderer.verify_inactive_recipe(mutated)

    def test_renderer_retargets_known_roles_without_enabling_or_changing_guards(self):
        settings = json.loads((ROOT / "examples" / "ev-settings.example.json").read_text(encoding="utf-8"))
        settings["entities"]["vehicle_soc"] = "sensor.example_car_battery"
        settings["device_ids"]["vehicle_cloud"] = "a" * 32
        settings["calendar_keywords"] = ["Example's route", "EV"]
        output = renderer.render(settings)
        package = yaml.safe_load(output)
        self.assertEqual(renderer.verify_inactive_recipe(package), 238)
        self.assertIn("sensor.example_car_battery", output)
        self.assertNotIn("sensor.ev_cloud_soc", output)
        self.assertNotIn("__EV_CALENDAR_KEYWORD_", output)
        agenda = next(item for item in package["automation"] if item["id"] == "ai_kia_laadplanner_agenda_update")
        variables = agenda["actions"][1]["variables"]
        env = Environment()
        env.parse(variables["rit_titel"])
        env.parse(variables["rit_start"])

    def test_renderer_rejects_activation_and_domain_mistakes(self):
        for settings in [{"enabled": True}, {"enable_outputs": True}, {"schema_version": 2},
                         {"entities": {"vehicle_soc": "switch.example"}},
                         {"entities": {"unknown_role": "sensor.example"}},
                         {"expected_charging_power_kw": float("nan")},
                         {"device_ids": {"vehicle_cloud": "not-a-device-id"}}]:
            with self.subTest(settings=list(settings)):
                with self.assertRaises(ValueError):
                    renderer.render(settings)

    def test_public_defaults_contain_no_historical_financial_seeds(self):
        for name, helper in PACKAGE["input_number"].items():
            if "initial" in helper and any(part in name for part in ("kosten", "besparing", "prijs", "net_kwh", "zon_kwh")):
                self.assertEqual(helper["initial"], 0)


class ForecastContractTests(unittest.TestCase):
    def test_missing_bad_and_boolean_prices_are_not_free_slots(self):
        rows = [{"timestamp": utc((BASE + timedelta(minutes=15 * i)).timestamp()), **price}
                for i, price in enumerate([{}, {"retail_cent": "bad"}, {"retail_cent": True}, {"retail_cent": 0}, {"retail_cent": -5.5}, {"retail_cent": "20"}])]
        predictions = ast.literal_eval(render(entity("ai_kia_volledige_prijsvoorspelling_uren")["attributes"]["predictions"], attrs=forecast_attrs(rows)))
        self.assertEqual([row["price"] for row in predictions], [0.0, -0.055, 0.2])
        self.assertEqual(len(predictions), 3)
        self.assertEqual(as_timestamp(predictions[0]["start"]), (BASE + timedelta(minutes=45)).timestamp())

    def test_wrong_units_or_interval_cannot_be_used_as_prices(self):
        item = entity("ai_kia_volledige_prijsvoorspelling_uren")
        rows = [{"timestamp": utc(BASE.timestamp()), "retail_cent": 20}]
        for unit, interval in [("EUR/kWh", 15), (None, 15), ("ct/kWh", 60), ("ct/kWh", None)]:
            attrs = forecast_attrs(rows, unit, interval)
            self.assertEqual(render(item["availability"], attrs=attrs), "False")
            self.assertEqual(ast.literal_eval(render(item["attributes"]["predictions"], attrs=attrs)), [])

    def test_duplicate_or_backwards_time_rows_are_not_repeated(self):
        rows = [{"timestamp": utc((BASE + timedelta(minutes=15 * i)).timestamp()), "retail_cent": 20} for i in [0, 0, 2, 1, 3]]
        predictions = ast.literal_eval(render(entity("ai_kia_volledige_prijsvoorspelling_uren")["attributes"]["predictions"], attrs=forecast_attrs(rows)))
        self.assertEqual([as_timestamp(row["start"]) - BASE.timestamp() for row in predictions], [0, 1800, 2700])


class DeadlinePlannerTests(unittest.TestCase):
    def plan(self, prices, duration, departure_hours, *, starts=None, now=BASE):
        item = entity("ai_kia_goedkoopste_laadblok")
        attrs = {("sensor.ai_kia_volledige_prijsvoorspelling_uren", "predictions"): slots(prices, starts)}
        states = {"input_text.ai_kia_werkrit_start": utc((BASE + timedelta(hours=departure_hours)).timestamp()),
                  "sensor.ai_kia_laaduren_nodig_verwacht": str(duration)}
        return render(item["state"], states=states, attrs=attrs, now=now), render(item["attributes"]["gemiddelde_prijs"], states=states, attrs=attrs, now=now)

    def test_final_partial_interval_is_weighted(self):
        start, price = self.plan([0.1, 0.9, 0.4, 0.4], 0.375, 2)
        self.assertEqual(as_timestamp(start), BASE.timestamp())
        self.assertAlmostEqual(float(price), (0.1 * 0.25 + 0.9 * 0.125) / 0.375, places=5)

    def test_cheaper_late_slots_cannot_violate_the_original_hard_margin(self):
        start, _ = self.plan([1, 1, 0.01, 0.01], 0.5, 1)
        self.assertEqual(as_timestamp(start), BASE.timestamp())
        deadline_template = entity("ai_kia_goedkoopste_laadblok")["attributes"]["deadline"]
        deadline = render(deadline_template, states={"input_text.ai_kia_werkrit_start": utc((BASE + timedelta(hours=1)).timestamp())})
        self.assertEqual(as_timestamp(deadline), (BASE + timedelta(minutes=30)).timestamp())

    def test_gap_cannot_be_bridged_to_create_a_fake_cheap_contiguous_plan(self):
        start, _ = self.plan([0.01, 0.01], 0.5, 2, starts=[0, 2])
        self.assertEqual(as_timestamp(start), (BASE + timedelta(hours=1)).timestamp())

    def test_missing_forecast_preserves_deadline_emergency_fallback(self):
        future_start, _ = self.plan([], 1, 3)
        self.assertEqual(as_timestamp(future_start), (BASE + timedelta(hours=1.5)).timestamp())
        immediate_start, _ = self.plan([], 2, 1)
        self.assertEqual(as_timestamp(immediate_start), BASE.timestamp())

    def test_no_charging_needed_and_negative_prices(self):
        self.assertEqual(self.plan([0.1], 0, 2)[0], "Geen laden nodig")
        self.assertEqual(as_timestamp(self.plan([0.1, -0.1, -0.2, 0.1], 0.5, 2)[0]), (BASE + timedelta(minutes=15)).timestamp())

    def test_aware_timestamps_across_both_dst_transitions(self):
        scenarios = [
            (["2030-03-31T01:30:00+01:00", "2030-03-31T01:45:00+01:00", "2030-03-31T03:00:00+02:00", "2030-03-31T03:15:00+02:00", "2030-03-31T03:30:00+02:00"], "2030-03-31T05:00:00+02:00"),
            (["2030-10-27T02:30:00+02:00", "2030-10-27T02:45:00+02:00", "2030-10-27T02:00:00+01:00", "2030-10-27T02:15:00+01:00", "2030-10-27T02:30:00+01:00"], "2030-10-27T04:00:00+01:00"),
        ]
        for points, departure in scenarios:
            rows = [{"start": points[i], "end": points[i + 1], "price": price} for i, price in enumerate([1, 0.05, 0.05, 1])]
            states = {"input_text.ai_kia_werkrit_start": departure, "sensor.ai_kia_laaduren_nodig_verwacht": "0.5"}
            attrs = {("sensor.ai_kia_volledige_prijsvoorspelling_uren", "predictions"): rows}
            result = render(entity("ai_kia_goedkoopste_laadblok")["state"], states=states, attrs=attrs, now=datetime.fromisoformat(points[0]))
            self.assertEqual(as_timestamp(result), as_timestamp(points[1]))
            self.assertEqual(as_timestamp(points[3]) - as_timestamp(points[1]), 1800)


class ManualPrecedenceTests(unittest.TestCase):
    def advice(self, **updates):
        states = {"sensor.ev_charger_status": "suspended", "binary_sensor.ai_kia_soc_is_betrouwbaar": "on",
                  "sensor.ai_kia_effectief_doelpercentage": "80", "sensor.ai_kia_soc_betrouwbaar": "40",
                  "input_boolean.ai_kia_direct_laden_actief": "off", "input_select.ai_kia_laadmodus": "Automatisch",
                  "input_text.ai_kia_werkrit_titel": "Example departure", "input_text.ai_kia_werkrit_start": utc((BASE + timedelta(hours=10)).timestamp()),
                  "input_text.ai_kia_vast_plan_start": utc((BASE + timedelta(hours=3)).timestamp()),
                  "sensor.ai_kia_uren_tot_vertrek": "10", "sensor.ai_kia_laaduren_nodig_verwacht": "2"}
        states.update(updates)
        return render(entity("ai_kia_werk_laadadvies")["state"], states=states)

    def test_direct_and_manual_deadline_modes_take_precedence_over_auto(self):
        self.assertEqual(self.advice(**{"input_boolean.ai_kia_direct_laden_actief": "on", "input_select.ai_kia_laadmodus": "Klaar om"}), "Nu laden")
        self.assertEqual(self.advice(**{"input_select.ai_kia_laadmodus": "Klaar om"}), "Wachten handmatig")
        self.assertEqual(self.advice(**{"input_select.ai_kia_laadmodus": "Klaar om", "input_text.ai_kia_vast_plan_start": utc(BASE.timestamp())}), "Laden handmatig")
        self.assertEqual(self.advice(**{"input_select.ai_kia_laadmodus": "Klaar om", "input_text.ai_kia_vast_plan_start": ""}), "Handmatig plannen")

    def test_goal_freshness_connection_and_emergency_precedence_remain(self):
        self.assertEqual(self.advice(**{"sensor.ai_kia_soc_betrouwbaar": "80", "input_boolean.ai_kia_direct_laden_actief": "on"}), "Klaar")
        self.assertEqual(self.advice(**{"binary_sensor.ai_kia_soc_is_betrouwbaar": "off", "input_boolean.ai_kia_direct_laden_actief": "on"}), "SOC verversen")
        self.assertEqual(self.advice(**{"sensor.ev_charger_status": "no_ev_connected"}), "Auto aansluiten")
        self.assertEqual(self.advice(**{"sensor.ai_kia_uren_tot_vertrek": "2.5"}), "Laden verplicht")

    def test_original_start_command_snapshot_rechecks_still_exist(self):
        controller = next(item for item in PACKAGE["automation"] if item["id"] == "ai_kia_peblar_automatisch_laden_veilig")
        source = yaml.safe_dump(controller)
        for variable in ["kia_start_mode", "kia_start_session", "kia_start_goal", "kia_start_plan", "kia_start_plan_rit",
                         "kia_start_now_button", "kia_start_stop_button", "kia_start_direct", "kia_start_allowed"]:
            self.assertGreaterEqual(source.count(variable), 2)
        self.assertIn("nieuw handmatig ingrijpen heeft voorrang", source)
        self.assertIn("- laatste >= 600", source)


if __name__ == "__main__":
    unittest.main()
