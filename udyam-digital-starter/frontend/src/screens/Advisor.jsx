import React, { useState } from "react";
import { useJourney } from "../App.jsx";
import { api } from "../api/client.js";
import { BundleCard } from "../components/ui.jsx";

// O2 — asks only 2-3 questions, returns Value + Lite bundles.
export default function Advisor() {
  const { t, lang, journey, setJourney, goto } = useJourney();
  const p = journey.profile;
  const [sites, setSites] = useState(p?.num_sites || 1);
  const [emp, setEmp] = useState(p?.employee_count || 2);
  const [spend, setSpend] = useState(2000);
  const [rec, setRec] = useState(null);
  const [loading, setLoading] = useState(false);

  if (!p) return <Empty goto={goto} />;

  async function recommend() {
    setLoading(true);
    const profile = { ...p, num_sites: Number(sites), employee_count: Number(emp) };
    try {
      const r = await api.recommend(profile, Number(spend), lang);
      setRec(r);
      setJourney((j) => ({ ...j, profile, recommendation: r }));
    } finally { setLoading(false); }
  }

  function choose(which) {
    setJourney((j) => ({ ...j, selectedBundle: rec[which] }));
    goto("checkout");
  }

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <div className="text-sm text-slate-500">A few quick questions:</div>
        <Field label="How many locations?"><input type="number" min="1" className="input"
          value={sites} onChange={(e) => setSites(e.target.value)} /></Field>
        <Field label="How many employees?"><input type="number" min="1" className="input"
          value={emp} onChange={(e) => setEmp(e.target.value)} /></Field>
        <Field label="Your current monthly telecom spend (₹)?"><input type="number" className="input"
          value={spend} onChange={(e) => setSpend(e.target.value)} /></Field>
        <button className="btn w-full" onClick={recommend} disabled={loading}>
          {loading ? "Thinking…" : "Recommend my bundle"}
        </button>
      </div>

      {rec && (
        <>
          {rec.rationale && <div className="card text-sm text-slate-600">{rec.rationale}</div>}
          <BundleCard title={t("value_bundle")} quote={rec.value} onSelect={() => choose("value")} />
          <BundleCard title={t("lite_bundle")} quote={rec.lite} onSelect={() => choose("lite")} />
          <p className="text-[11px] text-slate-400 text-center">
            Source: {rec.source} · ineligible products are removed automatically.
          </p>
        </>)}
    </div>
  );
}

const Field = ({ label, children }) => (
  <label className="block"><span className="text-sm">{label}</span><div className="mt-1">{children}</div></label>
);
const Empty = ({ goto }) => (
  <div className="card text-center text-slate-500">
    Start with your GSTIN first.
    <button className="btn mt-3" onClick={() => goto("onboard")}>Go to start</button>
  </div>
);
