"""Quote builder (sections O3 + 14B).

Pricing rule:
  - micro segment  -> price_min
  - other segments -> midpoint(min, max) rounded to nearest Rs PRICE_ROUND
Per-site rule:
  - products whose `unit` == 'per site' are multiplied by num_sites
Savings:
  - savings = current_monthly_spend - bundle_monthly  (shown when positive)
  - payback_months = one_time_total / savings          (when saving > 0)
"""
import math
import config
from data_store import get_store


def _price_point(p: dict, segment: str, price_mode: str = "auto") -> int:
    """price_mode 'floor' (Lite bundle) forces price_min; 'auto' applies the
    segment rule (micro -> floor, others -> rounded midpoint)."""
    lo = int(p["price_min_inr_per_month"])
    hi = int(p["price_max_inr_per_month"])
    if segment == "micro" or price_mode == "floor":
        return lo
    mid = (lo + hi) / 2
    return int(round(mid / config.PRICE_ROUND) * config.PRICE_ROUND)


def _line(pid: str, qty: int, segment: str, num_sites: int, price_mode: str = "auto") -> dict:
    p = get_store().product(pid)
    unit_price = _price_point(p, segment, price_mode)
    per_site = str(p.get("unit", "")).strip().lower() == "per site"
    multiplier = (num_sites if per_site else 1) * max(qty, 1)
    monthly = unit_price * multiplier
    setup = int(p.get("one_time_setup_inr", 0)) * max(qty, 1)
    return {
        "product_id": pid,
        "name": p["product_name"],
        "category": p["category"],
        "unit": p.get("unit"),
        "qty": max(qty, 1),
        "per_site": per_site,
        "unit_price_inr": unit_price,
        "price_min_inr": int(p["price_min_inr_per_month"]),
        "price_max_inr": int(p["price_max_inr_per_month"]),
        "monthly_inr": monthly,
        "one_time_inr": setup,
        "min_contract_months": int(p.get("min_contract_months", 1)),
        "typical_install_days": int(p.get("typical_install_days", 0)),
    }


def build_quote(segment: str, num_sites: int, bundle: list[str],
                qty: dict | None = None, current_spend: int | None = None,
                price_mode: str = "auto") -> dict:
    qty = qty or {}
    num_sites = max(int(num_sites or 1), 1)
    lines = [_line(pid, qty.get(pid, 1), segment, num_sites, price_mode) for pid in bundle]
    monthly = sum(l["monthly_inr"] for l in lines)
    one_time = sum(l["one_time_inr"] for l in lines)
    contract = max([l["min_contract_months"] for l in lines], default=1)
    install_days = max([l["typical_install_days"] for l in lines], default=0)

    out = {
        "lines": lines,
        "monthly_inr": monthly,
        "one_time_inr": one_time,
        "contract_months": contract,
        "expected_install_days": install_days,
        "price_mode": price_mode,
        "num_sites": num_sites,
        "savings": None,
    }
    if current_spend is not None:
        saving = current_spend - monthly
        out["savings"] = {
            "current_spend_inr": current_spend,
            "monthly_saving_inr": saving,          # negative = costs more (reframe as value)
            "payback_months": (round(one_time / saving, 1) if saving > 0 else None),
        }
    return out
