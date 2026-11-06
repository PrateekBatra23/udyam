import React, { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { MetricTile } from "../components/ui.jsx";

// O5/O6/O7 — analytics dashboard (the visual for the business case).
export default function BackOffice() {
  const [a, setA] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.analytics().then(setA).catch((e) => setErr(String(e))); }, []);

  if (err) return <div className="card text-sm text-slate-500">Load smb_leads.csv to see insights.</div>;
  if (!a) return <div className="card">Loading…</div>;
  if (a.note) return <div className="card text-sm text-slate-500">{a.note}</div>;

  const RateTable = ({ title, data }) => (
    <div className="card">
      <h3 className="font-semibold mb-2">{title}</h3>
      {Object.entries(data).map(([k, v]) => (
        <div key={k} className="flex justify-between text-sm py-1">
          <span>{k}</span>
          <span className="text-slate-500">{v.rate_pct}% ({v.activated}/{v.total})</span>
        </div>))}
    </div>);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <MetricTile label="Activation rate" value={`${a.activation_rate_pct}%`} sub={`${a.total_leads} leads`} />
        <MetricTile label="Median days to activate" value={a.median_days_to_activation} />
        <MetricTile label="6-month churn" value={`${a.churn_rate_pct}%`} />
        <MetricTile label="Mean NPS" value={a.mean_nps} />
      </div>
      <RateTable title="Activation by GSTIN" data={a.by_gstin} />
      <RateTable title="Activation by segment" data={a.by_segment} />
      <RateTable title="Activation by lead source" data={a.by_lead_source} />
      <div className="card">
        <h3 className="font-semibold mb-2">Top drop reasons</h3>
        {Object.entries(a.top_drop_reasons).map(([k, v]) => (
          <div key={k} className="flex justify-between text-sm py-1">
            <span className="pr-2">{k}</span><span className="text-slate-500">{v}</span></div>))}
      </div>
    </div>
  );
}
