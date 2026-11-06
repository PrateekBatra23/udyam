"""Propensity scoring (section O5). Loads the model trained by
notebooks/propensity_model (or scripts/train_propensity.py). Bands per 14C.
Degrades gracefully to a heuristic if no model file is present yet."""
import os
import pickle
import config

_MODEL = None
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "models", "propensity.pkl")

# lead-creation-time features ONLY (no leakage — section O5)
FEATURES = ["has_gstin", "has_udyam", "segment", "lead_source", "city_tier",
            "employee_count", "num_sites", "annual_turnover_band", "monthly_telecom_spend_inr",
            "products_of_interest_count"]


def _load():
    global _MODEL
    if _MODEL is None and os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            _MODEL = pickle.load(f)   # expected: {"pipeline": sklearn_pipeline}
    return _MODEL


def _band(p: float) -> str:
    if p >= config.PROPENSITY_HIGH:
        return "High"
    if p >= config.PROPENSITY_MED:
        return "Med"
    return "Low"


_ACTION = {"High": "Full self-serve, zero human touch",
           "Med": "Assisted WhatsApp / async nudge",
           "Low": "Low-cost nurture drip, no field visit"}


def _heuristic(lead: dict) -> float:
    """Fallback until the model is trained: anchored to observed rates."""
    p = 0.02
    if lead.get("has_gstin") in ("Y", True, 1):
        p = 0.096
    seg = lead.get("segment", "")
    p *= {"Small manufacturers": 1.3, "Professional offices": 1.15,
          "Small multi-site businesses": 1.15}.get(seg, 1.0)
    if lead.get("lead_source") in ("Referral", "Inbound call"):
        p *= 1.4
    return min(p, 0.95)


def score(lead: dict) -> dict:
    model = _load()
    if model:
        import pandas as pd
        X = pd.DataFrame([{k: lead.get(k) for k in FEATURES}])
        prob = float(model["pipeline"].predict_proba(X)[0, 1])
        src = "model"
    else:
        prob = _heuristic(lead)
        src = "heuristic"
    band = _band(prob)
    return {"probability": round(prob, 4), "band": band,
            "recommended_action": _ACTION[band], "source": src}
