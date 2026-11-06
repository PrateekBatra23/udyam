import React, { useEffect, useState } from "react";
import { useJourney } from "../App.jsx";
import { api } from "../api/client.js";
import { MaskedId, rupee } from "../components/ui.jsx";

// Order status view - the owner checks here instead of calling support.
const KYC_STYLE = { APPROVE: "bg-save/10 text-save", REVIEW: "bg-amber-100 text-amber-700", REJECT: "bg-red-100 text-red-600" };

export default function Tracker() {
  const { t, journey } = useJourney();
  const [order, setOrder] = useState(null);
  const [id, setId] = useState(journey.orderId || "");
  const [err, setErr] = useState("");

  async function load(oid) {
    setErr("");
    try { setOrder(await api.getOrder(oid.trim())); } catch (e) { setOrder(null); setErr(e.status === 404 ? "Order not found" : e.message); }
  }
  useEffect(() => { if (journey.orderId) { setId(journey.orderId); load(journey.orderId); } }, [journey.orderId, journey.kycDecision]);

  async function advance() { if (order) setOrder(await api.advanceOrder(order.order_id)); }

  return (
    <div className="space-y-4">
      <div className="card flex gap-2">
        <input className="input" placeholder="ORD-XXXXXXXX" value={id} aria-label="Order id"
               onChange={(e) => setId(e.target.value.toUpperCase())} />
        <button className="btn" onClick={() => load(id)} disabled={!id}>{t("track")}</button>
      </div>
      {err && <p className="text-sm text-red-600" role="alert">{err}</p>}

      {order && (
        <div className="card">
          <div className="flex justify-between items-start">
            <div>
              <div className="text-sm text-slate-500">{t("tracker_title")}</div>
              <div className="font-mono font-semibold">{order.order_id}</div>
            </div>
            {order.kyc_status && <span className={`pill ${KYC_STYLE[order.kyc_status]}`}>KYC: {t("decision_" + order.kyc_status)}</span>}
          </div>
          <div className="mt-3 rounded-xl bg-accel-light p-3">
            <div className="text-xs text-accel">{t("expected_activation")}</div>
            <div className="text-xl font-bold text-accel" data-testid="eta">{order.expected_activation}</div>
          </div>

          <ol className="mt-4 space-y-3" aria-label="Order stages">
            {order.stages.map((s, i) => {
              const done = i <= order.current_stage_index, now = i === order.current_stage_index;
              return (
                <li key={s} className="flex items-center gap-3" aria-current={now ? "step" : undefined}>
                  <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs shrink-0
                    ${done ? "bg-accel text-white" : "bg-slate-200 text-slate-400"} ${now ? "ring-2 ring-accel/40" : ""}`}>
                    {done ? "✓" : i + 1}</span>
                  <span className={`flex-1 ${done ? "font-medium" : "text-slate-400"}`}>{s}</span>
                  <span className="text-xs text-slate-400">{order.stage_eta[i]}</span>
                </li>);
            })}
          </ol>

          {order.lines.length > 0 && (
            <div className="mt-4 border-t border-slate-100 pt-3 text-sm">
              {order.lines.map((l) => (
                <div key={l.product_id} className="flex justify-between"><span>{l.name}</span>
                  <span className="text-slate-500">{rupee(l.monthly_inr)}</span></div>))}
              <div className="flex justify-between font-semibold mt-1"><span>{t("monthly")}</span><span>{rupee(order.monthly_inr)}</span></div>
              <div className="text-xs text-slate-400">{rupee(order.one_time_inr)} {t("one_time")} · {order.contract_months} {t("months")}</div>
            </div>)}
          {order.kyc_gstin_masked && <p className="text-xs text-slate-400 mt-2">GSTIN <MaskedId value={order.kyc_gstin_masked} /></p>}
          {order.retention_until && <p className="text-xs text-slate-400">Records retained until {order.retention_until}</p>}
          <button className="btn-ghost w-full mt-4" onClick={advance}>{t("simulate_next")} →</button>
        </div>)}
    </div>
  );
}
