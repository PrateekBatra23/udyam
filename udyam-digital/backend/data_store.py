"""Loads the four CSVs into memory on startup and indexes the registries.

Registries are dict-indexed by identifier for O(1) lookup. Everything else in
the backend reads from the singletons exposed here. Lookup tables that the
registries do not carry (city -> tier, business type -> segment, employee
priors, churn by segment) are DERIVED from smb_leads.csv, not hard-coded.
"""
import os
import re
import pandas as pd
from functools import lru_cache
import config


def _path(name: str) -> str:
    return os.path.normpath(os.path.join(config.DATA_DIR, name))


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def city_of(principal_place: str | None) -> str | None:
    """'Shop/Unit 1, Tech Park Road, Visakhapatnam, Andhra Pradesh - 118383' -> city."""
    if not principal_place:
        return None
    body = re.sub(r"\s*-\s*\d+\s*$", "", str(principal_place))
    parts = [p.strip() for p in body.split(",") if p.strip()]
    return parts[-2] if len(parts) >= 2 else None


class DataStore:
    def __init__(self):
        self.catalogue = pd.DataFrame()
        self.leads = pd.DataFrame()
        self.gstin = {}          # gstin -> row dict
        self.udyam = {}          # udyam_number -> row dict
        self.products = {}       # product_id -> row dict
        self.udyam_index = {}    # (norm name, state) -> [rows]
        self.city_tier_map = {}  # city -> tier (derived from leads)
        self.type_segment = {}   # business_type / nic_description -> segment code
        self.employee_prior = {} # segment -> median employees
        self.sites_prior = {}    # segment -> median sites
        self.churn_by_segment = {}   # segment -> {n, churn, nps}
        self.loaded = False

    def load(self):
        self.catalogue = pd.read_csv(_path("product_catalogue.csv"))
        self.products = {r["product_id"]: r for r in self.catalogue.to_dict("records")}

        greg = pd.read_csv(_path("mock_gstin_registry.csv"))
        self.gstin = {r["gstin"]: r for r in greg.to_dict("records")}

        ureg = pd.read_csv(_path("mock_udyam_registry.csv"))
        self.udyam = {r["udyam_number"]: r for r in ureg.to_dict("records")}
        for r in self.udyam.values():
            self.udyam_index.setdefault((_norm(r["enterprise_name"]), r["state"]), []).append(r)

        # leads are only needed for analytics/propensity/priors; tolerate absence
        try:
            self.leads = pd.read_csv(_path("smb_leads.csv"))
        except FileNotFoundError:
            self.leads = pd.DataFrame()
        if not self.leads.empty:
            self._derive()

        self.loaded = True
        return self

    def _derive(self):
        L = self.leads.copy()
        L["seg"] = L["segment"].map(config.SEGMENT_CODE)
        self.city_tier_map = {c: int(g.mode().iloc[0]) for c, g in L.groupby("city")["city_tier"]}
        self.type_segment = {_norm(t): g.mode().iloc[0] for t, g in L.groupby("business_type")["seg"]}
        self.employee_prior = {s: int(g.median()) for s, g in L.groupby("seg")["employee_count"]}
        self.sites_prior = {s: int(g.median()) for s, g in L.groupby("seg")["num_sites"]}
        act = L[L["outcome"] == "Activated"]
        self.churn_by_segment = {
            s: {"n": int(len(g)),
                "churn": round(float((g["churned_within_6_months"] == "Y").mean()), 4),
                "nps": round(float(g["nps_score"].mean()), 2)}
            for s, g in act.groupby("seg")}

    # --- helpers ---
    def product(self, pid: str) -> dict | None:
        return self.products.get(pid)

    def gstin_lookup(self, g: str) -> dict | None:
        return self.gstin.get(g)

    def udyam_lookup(self, u: str) -> dict | None:
        return self.udyam.get(u)

    def city_tier(self, city: str | None, default: int = 2) -> tuple[int, bool]:
        """(tier, known). Unknown cities default to Tier 2 and are flagged."""
        if city in self.city_tier_map:
            return self.city_tier_map[city], True
        return default, False

    def udyam_for_gstin(self, grow: dict) -> dict | None:
        """Match a GSTIN registry row to its Udyam record (name + state + city).
        Returns the row only if the match is unambiguous."""
        from kyc import names  # local import: avoid cycle at module load
        city = city_of(grow.get("principal_place_of_business"))
        biz = names.split_proprietor(grow.get("legal_name"))[1]
        cands = []
        for n in {grow.get("trade_name"), biz}:
            cands += self.udyam_index.get((_norm(n), grow.get("state")), [])
        cands = {c["udyam_number"]: c for c in cands}.values()
        same_city = [c for c in cands if c.get("city") == city]
        pool = same_city or []
        return pool[0] if len(pool) == 1 else None


STORE = DataStore()


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    if not STORE.loaded:
        STORE.load()
    return STORE
