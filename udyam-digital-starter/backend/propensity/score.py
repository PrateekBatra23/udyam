"""Propensity scoring (spec O5). Loads models/propensity.pkl written by
notebooks/train_propensity.py. Bands per 14C; each band routes effort:
High -> full self-serve, Med -> assisted async nudge, Low -> nurture drip.
Falls back to a documented heuristic if no model file exists yet."""
import os
import pickle

import pandas as pd

import config

_MODEL = None
_MODEL_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "models", "propensity.pkl"))

# lead-creation-time features ONLY (no leakage - spec O5)
NUMERIC = ["employee_count", "num_sites", "monthly_telecom_spend_inr", "products_of_interest_count"]
CATEGORICAL = ["has_gstin", "has_udyam", "segment", "lead_source", "city_tier", "annual_turnover_band"]
FEATURES = NUMERIC + CATEGORICAL

ACTION = {"High": "Full self-serve, zero human touch",
          "Med": "Assisted WhatsApp / async nudge",
          "Low": "Low-cost nurture drip, no field visit"}

_DEFAULTS = {"employee_count": 5, "num_sites": 1, "monthly_telecom_spend_inr": 1350,
             "products_of_interest_count": 1, "has_gstin": "N", "has_udyam": "N",
             "segment": "Micro retail & services", "lead_source": "Website form",
             "city_tier": "2", "annual_turnover_band": "40 lakh - 1.5 cr"}


def _load():
    global _MODEL
    if _MODEL is None and os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            _MODEL = pickle.load(f)   # {"pipeline", "features", "meta"}
    return _MODEL


def meta() -> dict | None:
    m = _load()
    return m.get("meta") if m else None


def band(p: float) -> str:
    if p >= config.PROPENSITY_HIGH:
        return "High"
    if p >= config.PROPENSITY_MED:
        return "Med"
    return "Low"


def _yn(v) -> str:
    return "Y" if v in ("Y", "y", True, 1, "true", "True") else "N"


def _prepare(lead: dict) -> dict:
    """Normalise a partial lead dict into the model's feature schema."""
    d = {**_DEFAULTS, **{k: v for k, v in lead.items() if v is not None}}
    poi = lead.get("products_of_interest")
    if "products_of_interest_count" not in lead or lead.get("products_of_interest_count") is None:
        if isinstance(poi, (list, tuple)):
            d["products_of_interest_count"] = len(poi)
        elif isinstance(poi, str):
            d["products_of_interest_count"] = len([x for x in poi.split(";") if x])
    seg = d.get("segment")
    if seg in config.SEGMENT_LABEL:                       # accept 'micro' etc.
        d["segment"] = config.SEGMENT_LABEL[seg]
    d["has_gstin"] = _yn(d.get("has_gstin"))
    d["has_udyam"] = _yn(d.get("has_udyam"))
    d["city_tier"] = str(d.get("city_tier"))
    return {k: d[k] for k in FEATURES}


def _heuristic(row: dict) -> float:
    """Fallback until the model is trained: anchored to the observed rates."""
    p = 0.096 if row["has_gstin"] == "Y" else 0.02
    p *= {"Small manufacturers": 1.3, "Professional offices": 1.15,
          "Small multi-site businesses": 1.15}.get(row["segment"], 1.0)
    if row["lead_source"] in ("Referral", "Inbound call"):
        p *= 1.4
    return min(p, 0.95)


def score_frame(df: pd.DataFrame):
    """Vector scoring for the dashboard. Returns (probabilities, source)."""
    rows = [_prepare(r) for r in df.to_dict("records")]
    X = pd.DataFrame(rows)[FEATURES]
    m = _load()
    if m:
        return m["pipeline"].predict_proba(X)[:, 1], "model"
    return [_heuristic(r) for r in rows], "heuristic"


def _drivers(pipe, X: pd.DataFrame, k: int = 3) -> list:
    """Top contributions (coef x standardised value) for one lead."""
    try:
        pre, clf = pipe.named_steps["pre"], pipe.named_steps["clf"]
        x = pre.transform(X)
        x = x.toarray()[0] if hasattr(x, "toarray") else x[0]
        names = pre.get_feature_names_out()
        contrib = clf.coef_[0] * x
        order = sorted(range(len(contrib)), key=lambda i: -abs(contrib[i]))[:k]
        return [{"feature": names[i].split("__", 1)[-1], "effect": round(float(contrib[i]), 3)}
                for i in order if abs(contrib[i]) > 1e-6]
    except Exception:
        return []


def score(lead: dict) -> dict:
    row = _prepare(lead or {})
    m = _load()
    drivers = []
    if m:
        X = pd.DataFrame([row])[FEATURES]
        prob = float(m["pipeline"].predict_proba(X)[0, 1])
        src = "model"
        drivers = _drivers(m["pipeline"], X)
    else:
        prob, src = _heuristic(row), "heuristic"
    b = band(prob)
    return {"probability": round(prob, 4), "band": b, "recommended_action": ACTION[b],
            "source": src, "drivers": drivers,
            "thresholds": {"high": config.PROPENSITY_HIGH, "med": config.PROPENSITY_MED}}
