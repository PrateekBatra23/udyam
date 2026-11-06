import React, { useEffect, useState } from "react";
import { useJourney } from "../App.jsx";
import { api } from "../api/client.js";
import { MetricTile, rupee } from "../components/ui.jsx";

// O5/O6/O7 - the business-case dashboard. Every number is computed from the CSVs.
const BAND = { High: "bg-save/10 text-save", Med: "bg-amber-100 text-amber-700", Low: "bg-slate-100 text-slate-600" };

export default function BackOffice() {
  const { t } = useJourney();
  const [a, setA] = useState(null);
  const [ret, setRet] = useState(null);
  const [leads, setLeads] = useState(null);
  const [band, setBand] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    api.analytics().then(setA).catch((e) => setErr(e.message));
    api.retention().then(setRet).catch(() => {});
  }, []);
  useEffect(() => { api.leads(15, band || undefined).then(setLeads).catch(() => {}); }, [band]);

  if (err) return <div className="card text-sm text-slate-500">{err}</div>;
  if (!a) return <div className="card">Loading...</div>;
  if (a.note) return <div className="card text-sm text-slate-500">{a.note}</div>;
  const m = a.metrics, tg = a.targets;

  const Rate = ({ title, data }) => (
    <div className="card">
      <h3 className="font-semibold mb-2 text-sm">{title}</h3>
      {Object.entries(data).map(([k, v]) => (
        <div key={k} className="py-1">
          <div className="flex justify-between text-sm"><span>{k}</span><span className="text-slate-500">{v.rate_pct}% ({v.activated}/{v.total})</span></div>
          <div className="h-1.5 bg-slate-100 rounded"><div className="h-1.5 bg-accel rounded" style={{ width: `${Math.min(v.rate_pct * 5, 100)}%` }} /></div>
        </div>))}
    </div>);

  return (
    <div className="space-y-4">
      <h2 className="font-semibold">{t("insights_title")}</h2>
      <div className="grid grid-cols-2 gap-3">
        <MetricTile label="Lead → activation" value={`${m.activation_rate_pct}%`} sub={`${t("baseline")} · ${t("target")} ${tg.activation_rate_pct}%`} />
        <MetricTile label="Median days to activate" value={m.median_days_to_activation} sub={`mean ${m.mean_days_to_activation} · ${t("target")} ${tg.median_days_to_activation}`} />
        <MetricTile label="Blended cost of acquisition" value={rupee(m.blended_cac_inr)} sub={`per activated · ${t("target")} ${rupee(tg.blended_cac_inr)}`} />
        <MetricTile label="6-month churn" value={`${m.churn_6m_pct}%`} sub={`${t("target")} ≤${tg.churn_6m_pct}%`} />
        <MetricTile label="Mean NPS" value={m.mean_nps} sub={`${t("target")} ${tg.mean_nps}`} />
        <MetricTile label="Median monthly bundle" value={rupee(m.median_monthly_bundle_inr)} sub={`${m.mean_follow_up_calls} chase calls each`} />
      </div>
      <p className="text-[11px] text-slate-400">Baselines are computed from {a.total_leads.toLocaleString()} leads (Apr-Jun 2026). Targets are proposals.</p>

      <div className="card">
        <h3 className="font-semibold mb-2 text-sm">Funnel</h3>
        {a.funnel.map((f) => (
          <div key={f.stage} className="py-1">
            <div className="flex justify-between text-sm"><span>{f.stage}</span>
              <span className="text-slate-500">{f.leads.toLocaleString()}{f.pct_of_previous != null && ` · ${f.pct_of_previous}%`}</span></div>
            <div className="h-1.5 bg-slate-100 rounded"><div className="h-1.5 bg-accel rounded" style={{ width: `${f.leads / a.total_leads * 100}%` }} /></div>
          </div>))}
      </div>

      <Rate title="Activation by GSTIN" data={a.by_gstin} />
      <Rate title="Activation by segment" data={a.by_segment} />
      <Rate title="Activation by lead source" data={a.by_lead_source} />

      {leads && (
        <div className="card">
          <h3 className="font-semibold mb-1 text-sm">Lead routing (propensity)</h3>
          <p className="text-[11px] text-slate-400 mb-2">
            Logistic regression · held-out AUC {leads.model?.auc} · {leads.model_source}</p>
          <div className="grid grid-cols-3 gap-2 mb-3">
            {leads.bands.map((b) => (
              <button key={b.band} onClick={() => setBand(band === b.band ? "" : b.band)}
                className={`rounded-xl p-2 text-left border ${band === b.band ? "border-accel" : "border-slate-100"}`}>
                <span className={`pill ${BAND[b.band]}`}>{b.band}</span>
                <div className="text-lg font-bold mt-1">{b.leads}</div>
                <div className="text-[10px] text-slate-500">{b.actual_activation_pct}% activate</div>
              </button>))}
          </div>
          <p className="text-xs text-slate-500">Low band = {leads.economics.low_band_share_of_cost_pct}% of acquisition spend
            ({rupee(leads.economics.cost_on_low_band_inr)}) on leads that activate at the lowest rate → nurture, no field visit.</p>
          <div className="overflow-x-auto mt-3">
            <table className="w-full text-xs">
              <thead><tr className="text-left text-slate-400"><th>Lead</th><th>Type</th><th>P</th><th>Action</th></tr></thead>
              <tbody>{leads.leads.map((l) => (
                <tr key={l.lead_id} className="border-t border-slate-100">
                  <td className="py-1 pr-2 font-mono">{l.lead_id}</td><td className="pr-2">{l.business_type}</td>
                  <td className="pr-2">{(l.probability * 100).toFixed(0)}%</td>
                  <td><span className={`pill ${BAND[l.band]}`}>{l.band}</span></td></tr>))}</tbody>
            </table>
          </div>
          {leads.model?.top_coefficients && (
            <details className="mt-3 text-xs"><summary className="cursor-pointer text-slate-500">Top drivers</summary>
              {leads.model.top_coefficients.slice(0, 8).map((c) => (
                <div key={c.feature} className="flex justify-between"><span>{c.feature.replace(/^(cat|num)__/, "")}</span><span>{c.coef > 0 ? "+" : ""}{c.coef}</span></div>))}
            </details>)}
        </div>)}

      {ret && (
        <div className="card">
          <h3 className="font-semibold mb-2 text-sm">Churn & NPS (segment and contract level)</h3>
          {[...ret.by_segment, ...ret.by_contract_months].map((r) => (
            <div key={r.key} className="flex justify-between text-sm py-0.5">
              <span>{r.key}{r.low_n && <span className="text-amber-600 text-[10px]"> directional (n={r.n})</span>}</span>
              <span className="text-slate-500">{r.churn_pct}% churn · NPS {r.mean_nps} · n={r.n}</span></div>))}
          <p className="text-[11px] text-slate-400 mt-2">{ret.caveat}</p>
        </div>)}

      <div className="card">
        <h3 className="font-semibold mb-1 text-sm">Why leads dropped, and what the digital journey does about it</h3>
        <p className="text-xs text-slate-500 mb-2">{a.drop_reasons_recovered.removed_by_design} of {a.drop_reasons_recovered.total_dropped} drops cite a reason the journey removes; {a.drop_reasons_recovered.eased_by_design} more are eased.</p>
        {a.drop_reasons.filter((r) => r.addressed_by).map((r) => (
          <div key={r.reason} className="text-sm py-1 border-t border-slate-50">
            <div className="flex justify-between"><span>{r.reason}</span><span className="text-slate-500">{r.leads}</span></div>
            <div className="text-[11px] text-save">{r.effect === "removed" ? "Removed" : "Eased"} by: {r.addressed_by}</div>
          </div>))}
        <p className="text-[10px] text-slate-400 mt-2">{a.drop_reasons_recovered.note}</p>
      </div>

      <div className="card text-xs text-slate-500">
        <h3 className="font-semibold mb-1 text-sm text-slate-700">Pinned thresholds</h3>
        {Object.entries(a.thresholds).map(([k, v]) => (
          <div key={k} className="flex justify-between"><span>{k.replaceAll("_", " ")}</span><span>{String(v)}</span></div>))}
      </div>
    </div>
  );
}
