from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

from tools.demo import build_demo

REPO = Path(__file__).resolve().parents[1]


class DemoTests(unittest.TestCase):
    def test_real_cli_serializes_synthetic_forecast_and_plan(self):
        result = subprocess.run([sys.executable, str(REPO / "tools/demo.py")],
                                capture_output=True, text=True, encoding="utf-8", check=True)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["synthetic"])
        self.assertTrue(payload["advisory_only"])
        self.assertTrue(payload["not_performance_evidence"])
        self.assertEqual(len(payload["scenario"]["slots"]), 384)
        self.assertEqual({r["source"] for r in payload["scenario"]["slots"]}, {"forecast"})
        self.assertEqual(len(payload["plan"]["loads"]), 3)
        self.assertFalse(payload["plan"]["emergency_required"])
        self.assertIsInstance(payload["pv_example"], dict)

    def test_callable_keeps_existing_environment_and_cached_configuration(self):
        import ai_energy_v11.config as config
        before_env = os.environ.copy()
        before_root = config.ROOT_DIR
        result = build_demo()
        self.assertEqual(os.environ.copy(), before_env)
        self.assertEqual(config.ROOT_DIR, before_root)
        self.assertEqual(len(result["scenario"]["slots"]), 384)

    def test_cli_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "demo.json"
            path.write_text("original")
            result = subprocess.run([sys.executable, str(REPO / "tools/demo.py"), "--output", str(path)],
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_text(), "original")
