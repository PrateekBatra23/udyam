"""Churn & NPS analysis (section O6). Aggregates at SEGMENT and CONTRACT-LENGTH
level only — n=368 activated / 56 churned is too small per exact bundle."""
import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "smb_leads.csv")


def main():
    df = pd.read_csv(DATA)
    act = df[df["outcome"] == "Activated"].copy()
    act["churned"] = (act["churned_within_6_months"] == "Y").astype(int)
    print(f"Activated: {len(act)}, churned: {act['churned'].sum()}\n")

    print("== Churn & NPS by segment ==")
    print(act.groupby("segment").agg(
        n=("churned", "size"), churn_pct=("churned", lambda s: round(s.mean() * 100, 1)),
        mean_nps=("nps_score", lambda s: round(s.mean(), 1))).to_string())

    print("\n== Churn & NPS by contract length ==")
    print(act.groupby("contract_months").agg(
        n=("churned", "size"), churn_pct=("churned", lambda s: round(s.mean() * 100, 1)),
        mean_nps=("nps_score", lambda s: round(s.mean(), 1))).to_string())

    print("\nNote: per-exact-bundle churn is NOT reported (insufficient n).")


if __name__ == "__main__":
    main()
