"""Read normalized retail price slots and loads; print an advisory plan as JSON."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from planner import Load, PriceSlot, plan_loads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.scenario.read_text(encoding="utf-8"))
        if data.get("price_unit") != "EUR/kWh":
            raise ValueError("price_unit must be EUR/kWh with comparable final retail tariffs")
        result = plan_loads([PriceSlot.from_dict(row) for row in data["slots"]],
                            [Load.from_dict(row) for row in data["loads"]],
                            site_power_kw=data["site_power_kw"],
                            uncertainty_weight=data.get("uncertainty_weight", 0.0))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"No plan generated: {exc}\n")
    print(json.dumps(result.to_dict(), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
