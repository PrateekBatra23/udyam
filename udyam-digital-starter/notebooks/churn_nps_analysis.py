"""Churn & NPS analysis (spec O6).

Run:  python notebooks/churn_nps_analysis.py

Aggregates at SEGMENT and CONTRACT-LENGTH level only. With 368 activated and 56
churned customers, any cut by exact bundle would be single-digit counts per
bundle, i.e. noise - so none is reported. Cells with n < 30 are flagged
directional. The same numbers feed the advisor's retention note and the
back-office dashboard.
"""
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "smb_leads.csv")
LOW_N = 30


def cut(act: pd.DataFrame, col: str) -> pd.DataFrame:
    g = act.groupby(col).agg(
        n=("churned", "size"), churned=("churned", "sum"),
        churn_pct=("churned", lambda s: round(s.mean() * 100, 1)),
        mean_nps=("nps_score", lambda s: round(s.mean(), 1)),
        median_monthly_inr=("monthly_bundle_value_inr", "median"),
    )
    g["note"] = g["n"].map(lambda n: "directional (n<%d)" % LOW_N if n < LOW_N else "")
    return g


def main():
    df = pd.read_csv(DATA)
    act = df[df["outcome"] == "Activated"].copy()
    act["churned"] = (act["churned_within_6_months"] == "Y").astype(int)
    print(f"Activated: {len(act)}, churned: {act['churned'].sum()} "
          f"({act['churned'].mean():.1%}), mean NPS {act['nps_score'].mean():.2f}\n")

    print("== Churn & NPS by segment ==")
    by_seg = cut(act, "segment")
    print(by_seg.to_string())

    print("\n== Churn & NPS by contract length ==")
    print(cut(act, "contract_months").to_string())

    print("\n== Projected LTV per segment: median monthly x median contract x (1 - churn) ==")
    for seg, g in act.groupby("segment"):
        churn = g["churned"].mean()
        m, c = g["monthly_bundle_value_inr"].median(), g["contract_months"].median()
        print(f"  {seg:<30s} Rs {m * c * (1 - churn):>10,.0f}   (Rs {m:,.0f} x {c:.0f} mo x {1 - churn:.3f})")

    print("\nReading: micro retail churns most (the leaky, price-sensitive 54% of the base); "
          "manufacturers retain best. 24-month contracts churn slightly less than 12-month "
          "ones, but n=61 vs 304 - treat as directional.")
    print("Note: per-exact-bundle churn is NOT reported (insufficient n).")


if __name__ == "__main__":
    main()
