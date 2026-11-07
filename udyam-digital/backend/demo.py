"""The five advisor test profiles pinned in spec 14D. Identifiers are pulled from
the registry CSVs (never invented): the first ACTIVE GSTIN in the right tier-1
city whose Udyam record says the right business type."""
from data_store import get_store, city_of


def _pick(nic_types: set, cities_tier: int, active=True):
    s = get_store()
    for g, row in s.gstin.items():
        if active and str(row["status"]).lower() != "active":
            continue
        city = city_of(row["principal_place_of_business"])
        if s.city_tier(city)[0] != cities_tier:
            continue
        u = s.udyam_for_gstin(row)
        if u and u["nic_description"] in nic_types:
            return g, row, u
    return None, None, None


def profiles() -> list[dict]:
    s = get_store()
    out = []

    def card(pid, title, expect, gstin, row, u, **profile):
        out.append({
            "id": pid, "title": title, "expect": expect, "gstin": gstin,
            "trade_name": (row or {}).get("trade_name"),
            "udyam_number": (u or {}).get("udyam_number"),
            "profile": profile,
        })

    # 1. Micro, no GSTIN - kirana, Tier 2
    out.append({"id": 1, "title": "Micro kirana, no GSTIN (Tier 2)",
                "expect": "Lite-leaning; GSTIN-gated products excluded",
                "gstin": None, "trade_name": "Kirana store", "udyam_number": None,
                "profile": {"segment": "micro", "city_tier": 2, "employee_count": 2,
                            "num_sites": 1}, "current_spend": 1200,
                "priority": "price"})

    g, row, u = _pick({"Dental clinic"}, 1)
    card(2, "Dental clinic, GSTIN (Tier 1)", "Full Value bundle incl. cloud telephony",
         g, row, u, segment="prof", city_tier=1, employee_count=12, num_sites=1)
    out[-1].update(current_spend=3500, priority="customers")

    g, row, u = _pick({"Electronics retail chain", "Apparel retail chain", "Pharmacy chain",
                       "Restaurant chain", "Bakery chain"}, 1)
    card(3, "4-store retailer, GSTIN (Tier 1)", "SD-WAN / failover / CCTV all eligible",
         g, row, u, segment="multi", city_tier=1, employee_count=30, num_sites=4)
    out[-1].update(current_spend=14000, priority="reliability")

    g, row, u = _pick({"Auto-parts unit"}, 1) if _pick({"Auto-parts unit"}, 1)[0] \
        else _pick({"Auto-parts unit"}, 2)
    card(4, "Auto-parts manufacturer, GSTIN", "Leased line + firewall + IoT",
         g, row, u, segment="mfg", city_tier=s.city_tier(city_of((row or {}).get("principal_place_of_business")))[0],
         employee_count=40, num_sites=2)
    out[-1].update(current_spend=42000, priority="security")

    out.append({"id": 5, "title": "Ineligible-request probe: 2-person shop asks for Managed SD-WAN",
                "expect": "Advisor refuses P10 and explains why",
                "gstin": None, "trade_name": "Corner shop", "udyam_number": None,
                "profile": {"segment": "micro", "city_tier": 2, "employee_count": 2,
                            "num_sites": 1}, "current_spend": 1500, "priority": "price",
                "message": "I want Managed SD-WAN for my shop", "requested": ["P10"]})
    return out
