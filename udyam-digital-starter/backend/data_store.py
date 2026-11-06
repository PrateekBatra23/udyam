"""Loads the four CSVs into memory on startup and indexes the registries.

Registries are dict-indexed by identifier for O(1) lookup. Everything else in
the backend reads from the singletons exposed here.
"""
import os
import pandas as pd
from functools import lru_cache
import config


def _path(name: str) -> str:
    return os.path.normpath(os.path.join(config.DATA_DIR, name))


class DataStore:
    def __init__(self):
        self.catalogue = pd.DataFrame()
        self.leads = pd.DataFrame()
        self.gstin = {}          # gstin -> row dict
        self.udyam = {}          # udyam_number -> row dict
        self.products = {}       # product_id -> row dict
        self.loaded = False

    def load(self):
        self.catalogue = pd.read_csv(_path("product_catalogue.csv"))
        self.products = {r["product_id"]: r for r in self.catalogue.to_dict("records")}

        greg = pd.read_csv(_path("mock_gstin_registry.csv"))
        self.gstin = {r["gstin"]: r for r in greg.to_dict("records")}

        ureg = pd.read_csv(_path("mock_udyam_registry.csv"))
        self.udyam = {r["udyam_number"]: r for r in ureg.to_dict("records")}

        # leads are only needed for analytics/propensity; load lazily-tolerant
        try:
            self.leads = pd.read_csv(_path("smb_leads.csv"))
        except FileNotFoundError:
            self.leads = pd.DataFrame()

        self.loaded = True
        return self

    # --- helpers ---
    def product(self, pid: str) -> dict | None:
        return self.products.get(pid)

    def gstin_lookup(self, g: str) -> dict | None:
        return self.gstin.get(g)

    def udyam_lookup(self, u: str) -> dict | None:
        return self.udyam.get(u)


STORE = DataStore()


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    if not STORE.loaded:
        STORE.load()
    return STORE
