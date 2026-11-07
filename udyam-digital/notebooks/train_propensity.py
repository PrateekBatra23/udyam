"""Train the activation-propensity model (spec O5) and export models/propensity.pkl.

Run:  python notebooks/train_propensity.py

* Predicts outcome == 'Activated' from LEAD-CREATION-TIME features only. The
  post-outcome columns (drop_reason, stage_reached, *_date, days_lead_to_activation,
  customer_follow_up_calls, bundle_*, one_time_setup_inr, contract_months,
  churned_within_6_months, nps_score, acquisition_cost_inr, outcome itself) are
  banned: they are only populated for leads that already progressed, so a model
  using them scores ~perfectly in testing and is useless on a brand-new lead.
* Plain logistic regression (interpretable coefficients). NO class re-weighting:
  the High/Med/Low bands (>=0.15 / 0.07-0.15 / <0.07) are anchored to the 7.4%
  base rate, so the probabilities must stay calibrated.
* Reports held-out AUC, the band table on the held-out split, and the top
  coefficients, and stores them next to the model for the dashboard.
"""
import os
import pickle
import sys

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import config                                    # noqa: E402  (bands live in one place)

DATA = os.path.join(config.DATA_DIR, "smb_leads.csv")
OUT = os.path.join(ROOT, "models", "propensity.pkl")

NUMERIC = ["employee_count", "num_sites", "monthly_telecom_spend_inr", "products_of_interest_count"]
CATEGORICAL = ["has_gstin", "has_udyam", "segment", "lead_source", "city_tier", "annual_turnover_band"]

BANNED = {"outcome", "drop_reason", "stage_reached", "days_lead_to_activation",
          "customer_follow_up_calls", "bundle_products", "monthly_bundle_value_inr",
          "one_time_setup_inr", "contract_months", "churned_within_6_months", "nps_score",
          "acquisition_cost_inr", "contacted_date", "needs_assessed_date",
          "quote_accepted_date", "kyc_complete_date", "activated_date"}
assert not (BANNED & set(NUMERIC + CATEGORICAL)), "leakage: banned column used as a feature"


def band(p: float) -> str:
    return "High" if p >= config.PROPENSITY_HIGH else "Med" if p >= config.PROPENSITY_MED else "Low"


def main():
    df = pd.read_csv(DATA)
    df["products_of_interest_count"] = (df["products_of_interest"].fillna("")
                                        .apply(lambda s: len([x for x in s.split(";") if x])))
    df["city_tier"] = df["city_tier"].astype(str)
    y = (df["outcome"] == "Activated").astype(int)
    X = df[NUMERIC + CATEGORICAL].copy()

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    pre = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL)])
    pipe = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000, C=1.0))])
    pipe.fit(Xtr, ytr)

    proba = pipe.predict_proba(Xte)[:, 1]
    auc = roc_auc_score(yte, proba)
    print(f"Held-out AUC: {auc:.3f}   Brier: {brier_score_loss(yte, proba):.4f}   "
          f"base rate: {y.mean():.3%}   mean predicted: {proba.mean():.3%}")

    te = pd.DataFrame({"p": proba, "y": yte.values})
    te["band"] = te["p"].map(band)
    bands = []
    print("\nHeld-out band table:")
    for b in ("High", "Med", "Low"):
        g = te[te["band"] == b]
        row = {"band": b, "leads": int(len(g)),
               "share_pct": round(len(g) / len(te) * 100, 1),
               "actual_activation_pct": round(float(g["y"].mean()) * 100, 1) if len(g) else None,
               "lift_vs_base": round(float(g["y"].mean() / y.mean()), 2) if len(g) else None}
        bands.append(row)
        print("  ", row)

    names = pipe.named_steps["pre"].get_feature_names_out()
    coefs = pipe.named_steps["clf"].coef_[0]
    top = sorted(zip(names, coefs), key=lambda t: -abs(t[1]))[:12]
    print("\nTop coefficients (standardised / one-hot):")
    for n, c in top:
        print(f"   {n:<55s} {c:+.3f}")

    meta = {"auc": round(float(auc), 4), "base_rate": round(float(y.mean()), 4),
            "n_train": int(len(Xtr)), "n_test": int(len(Xte)), "bands_held_out": bands,
            "top_coefficients": [{"feature": n, "coef": round(float(c), 3)} for n, c in top],
            "features": NUMERIC + CATEGORICAL,
            "thresholds": {"high": config.PROPENSITY_HIGH, "med": config.PROPENSITY_MED}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        pickle.dump({"pipeline": pipe, "features": NUMERIC + CATEGORICAL, "meta": meta}, f)
    print("\nSaved", OUT)


if __name__ == "__main__":
    main()
