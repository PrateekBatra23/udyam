// Mirrors backend/rules/quote.py so toggling an add-on recomputes instantly in the
// browser. The server recomputes everything again when the order is placed.
export function pricePoint(p, segment, mode) {
  const lo = Number(p.price_min_inr_per_month), hi = Number(p.price_max_inr_per_month);
  if (segment === "micro" || mode === "floor") return lo;
  return Math.round((lo + hi) / 2 / 10) * 10;
}

export function lineFromProduct(p, segment, mode, numSites, qty = 1) {
  const perSite = String(p.unit || "").trim().toLowerCase() === "per site";
  const unit = pricePoint(p, segment, mode);
  return {
    product_id: p.product_id, name: p.product_name, category: p.category, unit: p.unit,
    per_site: perSite, qty, unit_price_inr: unit,
    monthly_inr: unit * (perSite ? numSites : 1) * qty,
    one_time_inr: Number(p.one_time_setup_inr || 0) * qty,
    min_contract_months: Number(p.min_contract_months || 1),
    typical_install_days: Number(p.typical_install_days || 0),
    requires_one_of: String(p.requires_one_of || "").split("|").filter(Boolean),
  };
}

export function totals(lines) {
  const monthly = lines.reduce((s, l) => s + l.monthly_inr, 0);
  const oneTime = lines.reduce((s, l) => s + l.one_time_inr, 0);
  const contract = Math.max(1, ...lines.map((l) => l.min_contract_months));
  const install = Math.max(0, ...lines.map((l) => l.typical_install_days));
  return { monthly, oneTime, contract, install };
}

// Remove lines whose dependency ("needs one of ...") is no longer in the bundle.
export function closeDependencies(lines) {
  let cur = lines, changed = true, dropped = [];
  while (changed) {
    changed = false;
    const ids = new Set(cur.map((l) => l.product_id));
    const bad = cur.filter((l) => l.requires_one_of.length && !l.requires_one_of.some((d) => ids.has(d)));
    if (bad.length) { dropped = dropped.concat(bad); cur = cur.filter((l) => !bad.includes(l)); changed = true; }
  }
  return { lines: cur, dropped };
}
