import React, { useMemo, useState } from "react";
import { useJourney } from "../App.jsx";
import { api } from "../api/client.js";
import { rupee } from "../components/ui.jsx";

// O3 — itemised quote, toggle add-ons, live savings vs current spend.
export default function Checkout() {
  const { journey, setJourney, goto } = useJourney();
  const sel = journey.selectedBundle;
  const [disabled, setDisabled] = useState({}); // product_id -> true if toggled off
  const [placing, setPlacing] = useState(false);

  if (!sel) return (
    <div className="card text-center text-slate-500">No bundle selected yet.
      <button className="btn mt-3" onClick={() => goto("advisor")}>Back to advisor</button></div>
  );

  const lines = (sel.lines || sel.products || []).filter((l) => l.monthly_inr != null);
  const active = lines.filter((l) => !disabled[l.product_id]);
  const monthly = useMemo(() => active.reduce((s, l) => s + (l.monthly_inr || 0), 0), [active]);
  const oneTime = useMemo(() => active.reduce((s, l) => s + (l.one_time_inr || 0), 0), [active]);
  const current = sel.savings?.current_spend_inr;
  const saving = current != null ? current - monthly : null;

  async function placeOrder() {
    setPlacing(true);
    try {
      const o = await api.createOrder(active.map((l) => l.product_id));
      setJourney((j) => ({ ...j, orderId: o.order_id }));
      goto("kyc");
    } finally { setPlacing(false); }
  }

  return (
    <div className="space-y-4">
      <div className="card">
        <h3 className="font-semibold mb-2">Your plan</h3>
        <ul className="divide-y divide-slate-100">
          {lines.map((l) => (
            <li key={l.product_id} className="flex items-center justify-between py-2">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={!disabled[l.product_id]}
                  onChange={() => setDisabled((d) => ({ ...d, [l.product_id]: !d[l.product_id] }))} />
                {l.name || l.product_id}
              </label>
              <span className="text-sm text-slate-500">{rupee(l.monthly_inr)}/mo</span>
            </li>))}
        </ul>
      </div>

      <div className="card">
        <Row k="Monthly" v={`${rupee(monthly)}/mo`} big />
        <Row k="One-time setup" v={rupee(oneTime)} />
        {saving != null && (
          <Row k="You pay now" v={`${rupee(current)}/mo`} />
        )}
        {saving != null && saving > 0 && (
          <div className="mt-2 text-save font-medium">You save {rupee(saving)}/mo 🎉</div>)}
        {saving != null && saving <= 0 && (
          <div className="mt-2 text-slate-500 text-sm">
            +{rupee(-saving)}/mo for more services on one bill.</div>)}
        <button className="btn w-full mt-4" onClick={placeOrder} disabled={placing || !active.length}>
          {placing ? "Placing…" : "Accept & start KYC"}
        </button>
      </div>
    </div>
  );
}

const Row = ({ k, v, big }) => (
  <div className="flex justify-between items-baseline py-1">
    <span className="text-sm text-slate-500">{k}</span>
    <span className={big ? "text-2xl font-bold" : "font-medium"}>{v}</span>
  </div>
);
