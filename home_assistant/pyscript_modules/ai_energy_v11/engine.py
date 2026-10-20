from .config import ROOT_DIR as CONFIG_ROOT_DIR
from datetime import datetime, timezone
from pathlib import Path
import json
import math


VERSION = "11.0.1-native-market"

BASE_DIR = CONFIG_ROOT_DIR
TEST_DIR = BASE_DIR / "data" / "v11_test"


def self_test():
    """
    Controleert of AI Energy V11 als normale native Python draait.
    """

    numbers = [5, 1, 9, 3, 7]

    # Bewust normale Python-functionaliteit gebruiken.
    numbers.sort(key=lambda value: value)

    square_sum = sum(value * value for value in numbers)

    TEST_DIR.mkdir(parents=True, exist_ok=True)

    result = {
        "version": VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "native_python": True,
        "lambda_test": numbers,
        "generator_test": square_sum,
        "file_io_test": True,
    }

    path = TEST_DIR / "engine_self_test.json"

    path.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result["test_file"] = str(path)

    return result


def _safe_float(value):
    """
    Zet Home Assistant-state veilig om naar float.
    """

    try:
        if value is None:
            return None

        if isinstance(value, str):
            text = value.strip().lower()

            if text in (
                "",
                "unknown",
                "unavailable",
                "none",
                "nan",
            ):
                return None

            value = value.replace(",", ".")

        number = float(value)

        if math.isnan(number):
            return None

        if math.isinf(number):
            return None

        return number

    except Exception:
        return None


def build_market_status(data):
    """
    Bouwt de eerste V11 marktstatus.

    Nord Pool:
        primaire actuele marktbron

    ENTSO-E:
        onafhankelijke controle en fallback

    Nog geen historische learning.
    """

    if not isinstance(data, dict):
        data = {}

    entsoe = _safe_float(
        data.get("entsoe_current")
    )

    nordpool = _safe_float(
        data.get("nordpool_current")
    )

    result = {
        "version": VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "entsoe_price_eur_kwh": entsoe,
        "nordpool_price_eur_kwh": nordpool,
        "market_price_eur_kwh": None,
        "source": "missing",
        "quality": 0,
        "difference_cent_kwh": None,
        "agreement": "geen_data",
        "learning_allowed": False,
    }

    # Beide marktbronnen beschikbaar.
    if nordpool is not None and entsoe is not None:
        difference_cent = abs(
            nordpool - entsoe
        ) * 100

        result["difference_cent_kwh"] = round(
            difference_cent,
            3,
        )

        result["market_price_eur_kwh"] = round(
            nordpool,
            7,
        )

        result["source"] = (
            "nordpool_verified_by_entsoe"
        )

        if difference_cent <= 3:
            result["quality"] = 100
            result["agreement"] = "sterk"
            result["learning_allowed"] = True

        elif difference_cent <= 8:
            result["quality"] = 85
            result["agreement"] = "redelijk"
            result["learning_allowed"] = True

        else:
            result["quality"] = 60
            result["agreement"] = "afwijking"
            result["learning_allowed"] = False

    # Alleen Nord Pool beschikbaar.
    elif nordpool is not None:
        result["market_price_eur_kwh"] = round(
            nordpool,
            7,
        )

        result["source"] = "nordpool"
        result["quality"] = 85
        result["agreement"] = "enkele_bron"
        result["learning_allowed"] = True

    # Alleen ENTSO-E beschikbaar.
    elif entsoe is not None:
        result["market_price_eur_kwh"] = round(
            entsoe,
            7,
        )

        result["source"] = "entsoe_fallback"
        result["quality"] = 75
        result["agreement"] = "fallback"
        result["learning_allowed"] = True

    return result
