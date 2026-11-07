import React, { useEffect, useMemo, useState } from "react";
import { useJourney } from "../App.jsx";
import { api } from "../api/client.js";
import { Empty, rupee } from "../components/ui.jsx";
import { closeDependencies, lineFromProduct, totals } from "../lib/pricing.js";

// O3 - itemised quote with add-on toggles. Everything recomputes in the browser the
// moment a toggle changes (no round-trip); the server re-validates eligibility and
// recomputes the price when the order is placed.
const QTY_UNITS = ["per user", "per line", "per device", "per camera", "per account", "per number", "per pack", "per counter", "per vehicle", "per channel", "per IP"];

export default function Checkout() {
  const { t, journey, setJourney, goto, catalogue } = useJourney();
  const { rec, profile, answers } = journey;
  const [which, setWhich] = useState(journey.choice || "value");
  const [cands, setCands] = useState([]);      // candidate lines (bundle + added)
  const [on, setOn] = useState({});
  const [note, setNote] = useState("");
  const [placing, setPlacing] = useState(false);
  const [err, setErr] = useState("");

  const bundle = rec?.[which];
  const mode = bundle?.price_mode || "auto";
  const sites = bundle?.num_sites || profile?.num_sites || 1;

  useEffect(() => {
    if (!bundle) return;
    setCands(bundle.lines.map((l) => ({ ...l })));
    setOn(Object.fromEntries(bundle.lines.map((l) => [l.product_id, true])));
    setNote(""); setErr("");
  }, [which, rec]);

  const active = useMemo(() => cands.filter((l) => on[l.product_id]), [cands, on]);
  const tot = useMemo(() => totals(active), [active]);

  if (!rec || !bundle) return <Empty text={t("no_bundle")} cta={t("nav_advisor")} onClick={() => goto("advisor")} />;

  const current = answers?.spend;
  const saving = current != null ? current - tot.monthly : null;
  const activeIds = new Set(active.map((l) => l.product_id));

  function toggle(id) {
    const next = { ...on, [id]: !on[id] };
    const kept = closeDependencies(cands.filter((l) => next[l.product_id]));
    const dropped = kept.dropped;
    dropped.forEach((l) => { next[l.product_id] = false; });
    setOn(next);
    setNote(dropped.length ? t("needs_line", { names: dropped.map((l) => l.name).join(", ") }) : "");
  }

  function setQty(id, d) {
    setCands((cs) => cs.map((l) => {
      if (l.product_id !== id) return l;
      const qty = Math.max(1, l.qty + d);
      return { ...l, qty, monthly_inr: l.unit_price_inr * (l.per_site ? sites : 1) * qty,
               one_time_inr: (l.one_time_inr / l.qty) * qty };
    }));
  }

  // eligible products not in the bundle that can be added right now
  const addable = (rec.eligible_product_ids || [])
    .filter((id) => !cands.some((l) => l.product_id === id))
    .map((id) => catalogue.find((p) => p.product_id === id)).filter(Boolean)
    .filter((p) => {
      const dep = String(p.requires_one_of || "").split("|").filter(Boolean);
      return !dep.length || dep.some((d) => activeIds.has(d));
    });

  function add(p) {
    const line = lineFromProduct(p, rec.segment, mode, sites);
    setCands((cs) => [...cs, line]); setOn((o) => ({ ...o, [line.product_id]: true }));
  }

  async function placeOrder() {
    setPlacing(true); setErr("");
    try {
      const qty = Object.fromEntries(active.map((l) => [l.product_id, l.qty]));
      const o = await api.createOrder({
        bundle: active.map((l) => l.product_id), qty, gstin: journey.gstin || null,
        profile, price_mode: mode, current_spend: current ?? null });
      setJourney((j) => ({ ...j, orderId: o.order_id, plan: { lines: active, ...tot, which }, order: o }));
      goto("kyc");
    } catch (e) { setErr(e.message); } finally { setPlacing(false); }
  }

  return (
    <div className="space-y-4">
      <div className="flex rounded-xl bg-slate-100 p-1 text-sm" role="tablist">
        {["value", "lite"].map((k) => (
          <button key={k} role="tab" aria-selected={which === k} onClick={() => setWhich(k)}
            className={`flex-1 py-1.5 rounded-lg font-medium ${which === k ? "bg-white shadow-sm text-accel" : "text-slate-500"}`}>
            {t(k + "_bundle")} · {rupee(rec[k].monthly_inr)}</button>))}
      </div>

      <div className="card">
        <h3 className="font-semibold mb-2">{t("your_plan")}</h3>
        <ul className="divide-y divide-slate-100">
          {cands.map((l) => (
            <li key={l.product_id} className="py-2.5">
              <div className="flex items-center justify-between gap-2">
                <label className="flex items-center gap-2 text-sm font-medium">
                  <input type="checkbox" className="w-4 h-4 accent-[#1F4E8C]" checked={!!on[l.product_id]} onChange={() => toggle(l.product_id)} />
                  <span className={on[l.product_id] ? "" : "text-slate-400 line-through"}>{l.name}</span>
                </label>
                <span className="text-sm text-slate-600 whitespace-nowrap">{rupee(l.monthly_inr)}</span>
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-400 ml-6">
                <span>{rupee(l.unit_price_inr)} {l.unit}{l.per_site ? ` ${t("per_site_note", { n: sites })}` : ""}</span>
                {on[l.product_id] && QTY_UNITS.includes(l.unit) && (
                  <span className="flex items-center gap-1" aria-label={`Quantity of ${l.name}`}>
                    <button className="w-6 h-6 rounded-full bg-slate-100" onClick={() => setQty(l.product_id, -1)} aria-label="decrease">-</button>
                    <span className="w-4 text-center text-slate-700">{l.qty}</span>
                    <button className="w-6 h-6 rounded-full bg-slate-100" onClick={() => setQty(l.product_id, 1)} aria-label="increase">+</button>
                  </span>)}
              </div>
            </li>))}
        </ul>
        {note && <p className="text-xs text-amber-700 mt-2" role="status">{note}</p>}
      </div>

      <div className="card">
        <div className="text-xs text-slate-400 mb-2">{t("today_vs")}</div>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="text-xs text-slate-500">{t("today")}</div>
            <div className="text-xl font-semibold">{current != null ? rupee(current) : "-"}</div>
            <div className="text-[11px] text-slate-400">{t("monthly")}</div>
          </div>
          <div className="rounded-xl bg-accel-light p-3">
            <div className="text-xs text-accel">{t("with_accel")}</div>
            <div className="text-xl font-bold text-accel" data-testid="monthly">{rupee(tot.monthly)}</div>
            <div className="text-[11px] text-slate-500">{t("monthly")}</div>
          </div>
        </div>
        <dl className="mt-3 text-sm space-y-1">
          <div className="flex justify-between"><dt className="text-slate-500">{t("one_time")}</dt><dd className="font-medium" data-testid="onetime">{rupee(tot.oneTime)}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-500">{t("contract")}</dt><dd className="font-medium" data-testid="contract">{tot.contract} {t("months")}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-500">{t("go_live", { d: "" }).replace(/\s*$/, "")}</dt><dd className="font-medium">~{tot.install} d</dd></div>
        </dl>
        {saving != null && saving > 0 && (
          <div className="mt-3 rounded-xl bg-save/10 p-3 text-save font-medium" data-testid="saving">
            {t("you_save", { v: rupee(saving) })}
            {tot.oneTime > 0 && <div className="text-xs font-normal">{t("payback", { m: (tot.oneTime / saving).toFixed(1) })}</div>}
          </div>)}
        {saving != null && saving <= 0 && (
          <div className="mt-3 rounded-xl bg-slate-50 p-3 text-sm text-slate-600" data-testid="valueadd">
            {t("value_added", { v: rupee(-saving) })}: {active.map((l) => l.name).join(" + ")}</div>)}

        {which === "value"
          ? <button className="btn-ghost w-full mt-3" onClick={() => setWhich("lite")}>{t("cheaper_option")}</button>
          : <button className="btn-ghost w-full mt-3" onClick={() => setWhich("value")}>{t("back_to_value")}</button>}
        {err && <p className="text-sm text-red-600 mt-2" role="alert">{err}</p>}
        <button className="btn w-full mt-3" onClick={placeOrder} disabled={placing || !active.length}>
          {placing ? t("placing") : t("accept_start")}</button>
      </div>

      {addable.length > 0 && (
        <div className="card">
          <h3 className="font-semibold text-sm mb-2">{t("addons_available")}</h3>
          <ul className="space-y-1.5">
            {addable.slice(0, 8).map((p) => {
              const l = lineFromProduct(p, rec.segment, mode, sites);
              return (
                <li key={p.product_id} className="flex items-center justify-between text-sm">
                  <span>{p.product_name}</span>
                  <button className="pill bg-accel-light text-accel" onClick={() => add(p)}>+ {rupee(l.monthly_inr)}</button>
                </li>);
            })}
          </ul>
        </div>)}
    </div>
  );
}
