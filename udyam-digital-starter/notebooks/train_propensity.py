"""Train the activation-propensity model (section O5) and export models/propensity.pkl.

Runnable as a script (`python notebooks/train_propensity.py`) or paste into the
pinned .ipynb. CRITICAL: uses ONLY lead-creation-time features — the post-outcome
columns listed in the spec (O5) are excluded to avoid data leakage.
"""
import os
import pickle
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "smb_leads.csv")
OUT = os.path.join(ROOT, "models", "propensity.pkl")

# Allowed (known at lead creation). Everything else is BANNED (leakage).
NUMERIC = ["employee_count", "num_sites", "monthly_telecom_spend_inr",
           "products_of_interest_count"]
CATEGORICAL = ["has_gstin", "has_udyam", "segment", "lead_source", "city_tier",
               "annual_turnover_band"]


def main():
    df = pd.read_csv(DATA)
    df["products_of_interest_count"] = (df["products_of_interest"].fillna("")
                                        .apply(lambda s: len([x for x in s.split(";") if x])))
    df["y"] = (df["outcome"] == "Activated").astype(int)

    X = df[NUMERIC + CATEGORICAL].copy()
    y = df["y"]
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    pre = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])
    pipe = Pipeline([("pre", pre),
                     ("clf", LogisticRegression(max_iter=1000, class_weight="balanced"))])
    pipe.fit(Xtr, ytr)

    proba = pipe.predict_proba(Xte)[:, 1]
    print("Test AUC:", round(roc_auc_score(yte, proba), 3))
    print(classification_report(yte, (proba >= 0.15).astype(int), digits=3))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        pickle.dump({"pipeline": pipe, "features": NUMERIC + CATEGORICAL}, f)
    print("Saved", OUT)


if __name__ == "__main__":
    main()
