"""Public-config and actual-model checks. All IO uses a disposable private root.

Embedded engine self-tests build synthetic inputs. Their error metrics are test
assertions, not evidence of forecasting accuracy or monetary savings.
"""
from pathlib import Path
import ast
import importlib
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
MODULES = REPO / "home_assistant" / "pyscript_modules"
BRIDGES = REPO / "home_assistant" / "pyscript"


class FakeState:
    def __init__(self):
        self.written = []
    def set(self, *args, **kwargs):
        self.written.append((args, kwargs))
    def get(self, entity):
        return None
    def getattr(self, entity):
        return {}


class FakeService:
    def __init__(self):
        self.calls = []
    def __call__(self, function):
        return function
    def call(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("A test must not call Home Assistant services")
    def has_service(self, *args):
        return True


def fake_time_trigger(*args, **kwargs):
    return lambda function: function


class ForecastPublicTests(unittest.TestCase):
    def test_preview_requires_eur_to_match_internal_price_basis(self):
        with self.assertRaises(ValueError):
            self.config.validate_settings({"nordpool": {"currency": "USD"}})

    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory(prefix="ai-energy-public-tests-")
        cls.root = Path(cls._temp.name).resolve()
        cls._old_env = os.environ.get("AI_ENERGY_ROOT")
        os.environ["AI_ENERGY_ROOT"] = str(cls.root)
        sys.path.insert(0, str(MODULES))
        # Keep tests independent if discovery imported this package elsewhere.
        for name in list(sys.modules):
            if name == "ai_energy_v11" or name.startswith("ai_energy_v11."):
                del sys.modules[name]
        cls.core = importlib.import_module("ai_energy_v11")
        cls.config = importlib.import_module("ai_energy_v11.config")

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(MODULES))
        for name in list(sys.modules):
            if name == "ai_energy_v11" or name.startswith("ai_energy_v11."):
                del sys.modules[name]
        if cls._old_env is None:
            os.environ.pop("AI_ENERGY_ROOT", None)
        else:
            os.environ["AI_ENERGY_ROOT"] = cls._old_env
        cls._temp.cleanup()

    def bridge(self, name):
        state, service = FakeState(), FakeService()
        values = runpy.run_path(str(BRIDGES / name), init_globals={
            "state": state, "service": service, "time_trigger": fake_time_trigger,
        })
        return values, state, service

    def test_fresh_install_has_no_personal_sources_and_requires_opt_in(self):
        self.assertFalse(self.config.ENABLED)
        self.assertEqual(self.config.NORDPOOL_CONFIG_ENTRY, "")
        self.assertEqual(self.config.WEATHER_ENTITIES, ())
        self.assertTrue(all(".example_" in entity for entity in self.config.ENTITIES.values()))
        self.assertEqual(self.config.ROOT_DIR, self.root)
        self.assertEqual(self.config.LEGACY_BASE_DIR, self.root / "legacy_input")
        example = json.loads((REPO / "examples/settings.example.json").read_text())
        self.assertEqual(self.config.validate_settings(example), self.config.SETTINGS)

    def test_local_overrides_are_validated_and_do_not_mutate_defaults(self):
        settings = self.config.validate_settings({
            "enabled": True,
            "entities": {"zonneplan_quarter_hourly": "sensor.test_retail", "entsoe_average": "sensor.test_market"},
            "weather_entities": ["weather.test_home", "weather.test_home"],
        })
        self.assertEqual(settings["entities"]["zonneplan_quarter_hourly"], "sensor.test_retail")
        self.assertEqual(settings["weather_entities"], ["weather.test_home"])
        self.assertFalse(self.config.DEFAULT_SETTINGS["enabled"])
        self.assertIn("example_", self.config.DEFAULT_SETTINGS["entities"]["zonneplan_quarter_hourly"])
        for invalid in [[], {"enabled": "true"}, {"enabled": True}, {"entities": {"typo": "sensor.test"}}, {"timezone": "Invalid/Zone"}, {"weather_entities": ["sensor.test"]}]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.config.validate_settings(invalid)

    def test_malformed_local_settings_fail_closed(self):
        path = self.root / "invalid-settings.json"
        path.write_text('{"enabled": tru', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "valid UTF-8 JSON"):
            self.config.load_settings(path)

    def test_all_bridge_entrypoints_are_inert_before_setup(self):
        count = 0
        for path in sorted(BRIDGES.glob("ai_energy_v11*.py")):
            tree = ast.parse(path.read_text())
            names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.decorator_list]
            values, state, service = self.bridge(path.name)
            for name in names:
                with self.subTest(bridge=path.name, action=name):
                    self.assertEqual(values[name](), {"status": "configuration_required"})
                    self.assertEqual(service.calls, [])
                    count += 1
            self.assertTrue(state.written)
        self.assertGreater(count, 30)

    def test_unconfigured_nordpool_never_calls_the_service(self):
        values, _, service = self.bridge("ai_energy_v11_bridge.py")
        with self.assertRaisesRegex(ValueError, "config_entry is not configured"):
            values["_fetch_nordpool_date"]("2030-01-01")
        self.assertEqual(service.calls, [])

    def test_all_native_storage_paths_follow_the_selected_private_root(self):
        for path in sorted((MODULES / "ai_energy_v11").glob("*.py")):
            module = importlib.import_module("ai_energy_v11." + path.stem) if path.stem != "__init__" else self.core
            for key, value in vars(module).items():
                if key.isupper() and isinstance(value, Path):
                    with self.subTest(module=path.name, constant=key):
                        self.assertTrue(value.resolve().is_relative_to(self.root), str(value))

    def test_actual_embedded_self_tests_pass_on_synthetic_or_empty_inputs(self):
        names = sorted(n for n in dir(self.core) if n == "self_test" or n.endswith("_self_test"))
        self.assertGreaterEqual(len(names), 14)
        for name in names:
            with self.subTest(test=name):
                result = getattr(self.core, name)()
                if name == "self_test":
                    self.assertTrue(result["native_python"])
                    self.assertTrue(result["file_io_test"])
                    self.assertEqual(result["generator_test"], 165)
                    self.assertTrue(Path(result["test_file"]).resolve().is_relative_to(self.root))
                else:
                    self.assertEqual(result["status"], "ok")
        adapter = importlib.import_module("ai_energy_v11.dashboard_adapter")
        cold = adapter.dashboard_adapter_self_test()
        self.assertEqual(cold["status"], "ok")
        self.assertFalse(cold["core_ready"])

    def test_private_review_is_not_shipped_or_silently_applied(self):
        review = importlib.import_module("ai_energy_v11.market_review")
        market = importlib.import_module("ai_energy_v11.market_forecaster")
        before = market.MODEL_FILE.read_bytes() if market.MODEL_FILE.exists() else None
        result = review.apply_review()
        after = market.MODEL_FILE.read_bytes() if market.MODEL_FILE.exists() else None
        self.assertEqual(result["status"], "no_local_review")
        self.assertFalse(result["automatic_promotion"])
        self.assertEqual(before, after)
        self.assertFalse(hasattr(review, "MODEL"))
        self.assertFalse(hasattr(review, "REVIEW_REPORT"))
        self.assertIn("recent_grouped_daily", market.MODEL_NAMES)

    def test_dashboard_contract_has_explicit_units_and_resolution(self):
        values, state, service = self.bridge("ai_energy_v11_dashboard_bridge.py")
        values["_publish"]({"status": "missing_forecast", "core_ready": False, "forecast": []}, "test")
        args, _ = state.written[-1]
        self.assertEqual(args[0], "sensor.ai_energy_v11_dashboard_data")
        self.assertEqual(args[2]["retail_price_unit"], "ct/kWh")
        self.assertEqual(args[2]["interval_minutes"], 15)
        self.assertEqual(args[2]["forecast"], [])
        self.assertEqual(service.calls, [])


if __name__ == "__main__":
    unittest.main()
