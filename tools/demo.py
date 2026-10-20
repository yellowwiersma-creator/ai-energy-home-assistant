"""Synthetic 96h forecast -> comparable retail prices -> bounded load planning."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "home_assistant/pyscript_modules")]


def _build_demo_worker():
    if os.environ.get("AI_ENERGY_DEMO_WORKER") != "1":
        raise ValueError("Use build_demo() or the command line to create an isolated worker")
    # The launcher sets the disposable root before this fresh process imports code.
    from ai_energy_v11 import market_forecaster as model
    from planner import Load, PriceSlot, plan_loads, pv_opportunity_cost

    issue = datetime(2025, 3, 1, tzinfo=timezone.utc)
    history = []
    for i in range(28 * 96):
        dt = issue - timedelta(days=28) + timedelta(minutes=15 * i)
        # Entirely invented history, not a market feed or household measurement.
        quarter = (dt.hour * 4 + dt.minute // 15)
        price = 0.065 + 0.035 * math.cos((quarter - 72) * math.tau / 96)
        price += 0.006 * (dt.weekday() < 5)
        history.append(model._normalize_unified_row({
            "timestamp": dt.isoformat(), "market_price_eur_kwh": price}))
    history_map = model._history_map(history)
    rows = []
    for i in range(384):
        dt = issue + timedelta(minutes=15 * i)
        predicted = model.predict_market_slot(history, history_map, issue, dt, "recent_grouped_daily")
        if predicted is None or not math.isfinite(predicted):
            raise ValueError("Synthetic forecast did not produce a valid market price")
        # A declared fictitious affine tariff, NOT the trained retail learner.
        retail = 0.12 + 1.20 * predicted
        rows.append({"start": dt.isoformat(), "retail_eur_kwh": round(retail, 6),
                     "source": "forecast", "uncertainty_eur_kwh": 0.04})
    jobs = [
        {"name": "Warm water (demo)", "energy_kwh": 2.0, "power_kw": 1.0,
         "earliest": issue.isoformat(), "deadline": (issue + timedelta(hours=7)).isoformat()},
        {"name": "EV (demo)", "energy_kwh": 12.0, "power_kw": 3.6,
         "earliest": issue.isoformat(), "deadline": (issue + timedelta(hours=10)).isoformat()},
        {"name": "Verwarmen (demo)", "energy_kwh": 1.5, "power_kw": 1.5,
         "earliest": (issue + timedelta(hours=5)).isoformat(),
         "deadline": (issue + timedelta(hours=9)).isoformat()},
    ]
    scenario = {"synthetic": True, "price_unit": "EUR/kWh", "site_power_kw": 4.6,
                "uncertainty_weight": 1.0, "slots": rows, "loads": jobs}
    result = plan_loads([PriceSlot.from_dict(row) for row in rows],
                        [Load.from_dict(row) for row in jobs], site_power_kw=4.6,
                        uncertainty_weight=1.0)
    return {"synthetic": True, "advisory_only": True,
            "method": "Actual recent_grouped_daily predictor on artificial 28-day history",
            "retail_conversion": "Fictitious 0.12 + 1.20 * market; not a learned household model",
            "not_performance_evidence": True, "scenario": scenario, "plan": result.to_dict(),
            "pv_example": pv_opportunity_cost(energy_kwh=3.0, export_eur_kwh_now=0.20,
                                               future_import_eur_kwh=0.15,
                                               future_price_source="forecast").to_dict()}


def build_demo():
    """A fresh process keeps cached imports and the caller's environment intact."""
    with tempfile.TemporaryDirectory(prefix="ai-energy-demo-") as root:
        env = os.environ.copy()
        env["AI_ENERGY_ROOT"] = root
        env["AI_ENERGY_DEMO_WORKER"] = "1"
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker"],
                                env=env, capture_output=True, text=True, encoding="utf-8", check=True)
        return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional new JSON file; no existing file is overwritten")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(_build_demo_worker(), ensure_ascii=True, allow_nan=False))
        return
    result = build_demo()
    text = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as target:
            target.write(text)
        print(f"Synthetic demonstration written: {args.output}")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
