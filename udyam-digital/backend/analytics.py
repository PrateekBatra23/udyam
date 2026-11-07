"""Back-office analytics (spec O5-O7). Every number is computed from the CSVs at
request time - nothing is hard-coded except the targets (proposals) and the
mapping of drop reasons to the feature that addresses them."""
import pandas as pd

import config
from data_store import get_store
from propensity import score as propensity

# Drop reason -> (feature that addresses it, how fully)
RECOVERY = {
    "Quote took too long to arrive": ("Instant digital quote", "removed"),
    "Quote too complex to understand": ("Plain-language itemised quote + advisor", "removed"),
    "Owner had no time for a visit": ("Self-serve journey, no visit", "removed"),
    "Visit not scheduled by sales": ("Self-serve journey, no visit", "removed"),
    "Price too high": ("Savings line + one-tap Lite bundle", "eased"),
    "Competitor offered cheaper plan": ("Savings line + one-tap Lite bundle", "eased"),
    "Missing GST or Udyam document": ("GSTIN-first onboarding + document OCR", "removed"),
    "Document details did not match": ("Smart KYC cross-checks", "removed"),
    "Found paperwork too long": ("Registry autofill + straight-through KYC", "eased"),
    "Authorised signatory not available": ("Upload-based digital KYC", "eased"),
    "Unreachable after 3 attempts": ("Owner-initiated flow + order tracker", "eased"),
    "Installation delayed beyond 21 days": ("Order tracker transparency (install time unchanged)", "eased"),
}

# Proposed targets (assumptions to beat the baselines; shown as proposals)
TARGETS = {"activation_rate_pct": 12.0, "median_days_to_activation": 7,
           "blended_cac_inr": 9000, "churn_6m_pct": 12.0, "mean_nps": 7.5}

STAGE_COLS = [("Lead", None), ("Contacted", "contacted_date"), ("Needs assessed", "needs_assessed_date"),
              ("Quote accepted", "quote_accepted_date"), ("KYC complete", "kyc_complete_date"),
              ("Activated", "activated_date")]


def _leads() -> pd.DataFrame:
    df = get_store().leads
    return df


def _rate_by(df, col):
    out = {}
    for k, grp in df.groupby(col):
        a = int((grp["outcome"] == "Activated").sum())
        out[str(k)] = {"activated": a, "total": int(len(grp)),
                       "rate_pct": round(a / len(grp) * 100, 1)}
    return out


def summary() -> dict:
    df = _leads()
    if df.empty:
        return {"note": "smb_leads.csv not loaded"}
    n = len(df)
    act = df[df["outcome"] == "Activated"]
    na = len(act)

    funnel, prev = [], None
    for name, col in STAGE_COLS:
        cnt = n if col is None else int(df[col].notna().sum())
        funnel.append({"stage": name, "leads": cnt,
                       "pct_of_previous": None if prev is None else round(cnt / prev * 100, 1)})
        prev = cnt

    metrics = {
        "activation_rate_pct": round(na / n * 100, 1),
        "median_days_to_activation": float(act["days_lead_to_activation"].median()),
        "mean_days_to_activation": round(float(act["days_lead_to_activation"].mean()), 1),
        "blended_cac_inr": round(float(df["acquisition_cost_inr"].sum() / na)),
        "mean_cost_per_activated_lead_inr": round(float(act["acquisition_cost_inr"].mean())),
        "churn_6m_pct": round((act["churned_within_6_months"] == "Y").mean() * 100, 1),
        "mean_nps": round(float(act["nps_score"].mean()), 1),
        "median_monthly_bundle_inr": float(act["monthly_bundle_value_inr"].median()),
        "mean_follow_up_calls": round(float(act["customer_follow_up_calls"].mean()), 1),
    }

    drops = df[df["drop_reason"].notna()]["drop_reason"].value_counts()
    recovered = {"removed": 0, "eased": 0}
    reasons = []
    for reason, cnt in drops.items():
        feat, how = RECOVERY.get(reason, (None, None))
        if how:
            recovered[how] += int(cnt)
        reasons.append({"reason": reason, "leads": int(cnt), "addressed_by": feat, "effect": how})
    total_drops = int(drops.sum())

    return {
        "total_leads": n, "activated": na, "metrics": metrics, "targets": TARGETS,
        "funnel": funnel,
        "by_gstin": _rate_by(df, "has_gstin"),
        "by_segment": _rate_by(df, "segment"),
        "by_lead_source": _rate_by(df, "lead_source"),
        "by_city_tier": _rate_by(df, "city_tier"),
        "drop_reasons": reasons,
        "drop_reasons_recovered": {
            "total_dropped": total_drops,
            "removed_by_design": recovered["removed"], "eased_by_design": recovered["eased"],
            "note": "Upper bound: leads who dropped citing a reason the digital journey "
                    "removes or eases; not a forecast of how many would convert."},
        "thresholds": {
            "propensity_high": config.PROPENSITY_HIGH, "propensity_med": config.PROPENSITY_MED,
            "ocr_auto_approve_confidence": config.OCR_AUTO_APPROVE_CONFIDENCE,
            "name_match": config.NAME_MATCH, "name_review": config.NAME_REVIEW,
            "address_proof_max_age_days": config.ADDRESS_PROOF_MAX_AGE_DAYS,
            "retention_days": config.RETENTION_DAYS, "today": str(config.TODAY)},
        # back-compat keys used by the first dashboard
        "activation_rate_pct": metrics["activation_rate_pct"],
        "median_days_to_activation": metrics["median_days_to_activation"],
        "churn_rate_pct": metrics["churn_6m_pct"], "mean_nps": metrics["mean_nps"],
        "top_drop_reasons": {r["reason"]: r["leads"] for r in reasons[:8]},
    }


def retention() -> dict:
    """O6: churn / NPS at SEGMENT and CONTRACT-LENGTH level only - n is too small
    for per-bundle cuts (368 activated / 56 churned). Cells with n < 30 are
    flagged directional."""
    df = _leads()
    if df.empty:
        return {"note": "smb_leads.csv not loaded"}
    act = df[df["outcome"] == "Activated"]

    def cut(col, label=lambda x: str(x)):
        rows = []
        for k, g in act.groupby(col):
            rows.append({"key": label(k), "n": int(len(g)),
                         "churned": int((g["churned_within_6_months"] == "Y").sum()),
                         "churn_pct": round((g["churned_within_6_months"] == "Y").mean() * 100, 1),
                         "mean_nps": round(float(g["nps_score"].mean()), 1),
                         "mean_monthly_inr": round(float(g["monthly_bundle_value_inr"].mean())),
                         "low_n": bool(len(g) < 30)})
        return rows

    by_segment = cut("segment")
    ltv = []
    for r in by_segment:
        seg = act[act["segment"] == r["key"]]
        m = float(seg["monthly_bundle_value_inr"].median())
        c = float(seg["contract_months"].median())
        ltv.append({"segment": r["key"], "median_monthly_inr": round(m),
                    "median_contract_months": int(c),
                    "projected_ltv_inr": round(m * c * (1 - r["churn_pct"] / 100))})
    return {
        "by_segment": by_segment,
        "by_contract_months": cut("contract_months", lambda k: f"{int(k)} months"),
        "projected_ltv": ltv,
        "caveat": "Activated n=368, churned n=56. Segment and contract-length cuts are "
                  "usable; anything finer (per bundle) would be noise. Cells with n<30 "
                  "(e.g. the 6-month contract) are directional only.",
    }


def scored_leads(limit: int = 50, band: str | None = None) -> dict:
    """O5: leads sorted by propensity with a routing action, plus the economics
    of routing effort by band."""
    df = _leads()
    if df.empty:
        return {"note": "smb_leads.csv not loaded"}
    probs, source = propensity.score_frame(df)
    d = df.copy()
    d["p"] = probs
    d["band"] = [propensity.band(p) for p in probs]

    seg_value = (d[d["outcome"] == "Activated"].groupby("segment")["monthly_bundle_value_inr"].median())
    d["exp_year_revenue"] = d["p"] * d["segment"].map(seg_value).fillna(seg_value.median()) * 12
    d["worth_effort"] = d["exp_year_revenue"] > d["acquisition_cost_inr"]

    bands = []
    for b in ("High", "Med", "Low"):
        g = d[d["band"] == b]
        if g.empty:
            bands.append({"band": b, "leads": 0})
            continue
        bands.append({
            "band": b, "leads": int(len(g)),
            "mean_probability": round(float(g["p"].mean()), 3),
            "actual_activation_pct": round((g["outcome"] == "Activated").mean() * 100, 1),
            "mean_cost_per_lead_inr": round(float(g["acquisition_cost_inr"].mean())),
            "action": propensity.ACTION[b]})

    low = d[d["band"] == "Low"]
    total_cost = float(d["acquisition_cost_inr"].sum())
    saved = float(low["acquisition_cost_inr"].sum())
    shown = d if not band else d[d["band"] == band]
    shown = shown.sort_values("p", ascending=False).head(limit)
    return {
        "model_source": source, "bands": bands, "model": propensity.meta(),
        "economics": {
            "total_acquisition_cost_inr": round(total_cost),
            "cost_on_low_band_inr": round(saved),
            "low_band_share_of_cost_pct": round(saved / total_cost * 100, 1) if total_cost else 0,
            "low_band_activations": int((low["outcome"] == "Activated").sum()),
            "note": "Low-band leads move to a nurture drip with no field visit; the cost shown is "
                    "what was spent on them in the quarter. Indicative - assumes nurture is far "
                    "cheaper than the sales cost recorded in the data."},
        "leads": [{"lead_id": r.lead_id, "business_type": r.business_type, "segment": r.segment,
                   "lead_source": r.lead_source, "has_gstin": r.has_gstin,
                   "probability": round(float(r.p), 3), "band": r.band,
                   "action": propensity.ACTION[r.band],
                   "expected_year_revenue_inr": round(float(r.exp_year_revenue)),
                   "cost_inr": int(r.acquisition_cost_inr)}
                  for r in shown.itertuples()],
    }
