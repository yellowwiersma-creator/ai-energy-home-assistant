"""Review status without distributing household training data or fitted reports.

The original deployment contained an approved, installation-specific model and
holdout report. Neither is included in this public package. The predictor
implementations remain available for locally trained/evaluated models.
"""
from datetime import datetime, timezone
from . import market_forecaster as market
from .storage import read_json


def apply_review():
    """Intentionally do not deploy a model without new local review evidence."""
    return get_review()


def get_review():
    current = read_json(market.MODEL_FILE, {})
    return {
        "status": "no_local_review",
        "friendly_name": "AI Energy model review",
        "active_model": current.get("model_type") if isinstance(current, dict) else None,
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "available_predictors": list(market.MODEL_NAMES),
        "message": "No reviewed model or accuracy claims are shipped. Train and evaluate with local data before making a model-selection claim.",
        "market_only": True,
        "automatic_promotion": False,
    }
