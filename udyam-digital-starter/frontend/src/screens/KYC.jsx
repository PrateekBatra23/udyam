import React, { useEffect, useState } from "react";
import { useJourney } from "../App.jsx";
import { api } from "../api/client.js";

// O4 — consent gate first, then validate an applicant (or run all + STP).
const DECISION_STYLE = { APPROVE: "bg-save/10 text-save", REJECT: "bg-red-100 text-red-600",
                         REVIEW: "bg-amber-100 text-amber-700" };

export default function KYC() {
  const { t } = useJourney();
  const [consented, setConsented] = useState(false);
  const [notice, setNotice] = useState(null);
  const [applicant, setApplicant] = useState("K01");
  const [result, setResult] = useState(null);
  const [batch, setBatch] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.consent().then(setNotice).catch(() => {}); }, []);

  if (!consented) return (
    <div className="card">
      <h3 className="font-semibold">{t("consent_title")}</h3>
      {notice && (
        <ul className="text-sm text-slate-600 mt-3 space-y-1 list-disc pl-5">
          <li>We collect: {notice.collected?.join(", ")}</li>
          <li>Purpose: {notice.purpose}</li>
          <li>Kept for {notice.retention_days} days, then deleted</li>
          <li>{notice.minimisation}</li>
        </ul>)}
      <button className="btn w-full mt-4" onClick={() => setConsented(true)}>{t("consent_accept")}</button>
    </div>);

  async function run() {
    setBusy(true); setResult(null);
    try { setResult(await api.kycValidate(applicant)); } finally { setBusy(false); }
  }
  async function runAll() {
    setBusy(true); setBatch(null);
    try { setBatch(await api.kycAll()); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="flex gap-2">
          <select className="input" value={applicant} onChange={(e) => setApplicant(e.target.value)}>
            {Array.from({ length: 12 }, (_, i) => `K${String(i + 1).padStart(2, "0")}`)
              .map((k) => <option key={k}>{k}</option>)}
          </select>
          <button className="btn" onClick={run} disabled={busy}>Validate</button>
        </div>
        <button className="btn-ghost w-full mt-3" onClick={runAll} disabled={busy}>
          Run all 12 & show STP rate
        </button>
      </div>

      {result && <ResultCard r={result} />}

      {batch && (
        <div className="card">
          <div className="text-3xl font-bold text-accel">{batch.stp_rate}%</div>
          <div className="text-xs text-slate-500">straight-through processing
            ({batch.approved}/{batch.total} auto-approved)</div>
          <ul className="mt-3 space-y-1 text-sm">
            {batch.results.map((r) => (
              <li key={r.applicant} className="flex justify-between">
                <span>{r.applicant}</span>
                <span className={`pill ${DECISION_STYLE[r.decision]}`}>{r.decision}</span>
              </li>))}
          </ul>
        </div>)}
    </div>
  );
}

function ResultCard({ r }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <span className="font-semibold">{r.applicant}</span>
        <span className={`pill ${DECISION_STYLE[r.decision]}`}>{r.decision}</span>
      </div>
      <div className="text-xs text-slate-400">mean OCR confidence {r.mean_confidence}</div>
      <ul className="mt-3 space-y-1 text-sm">
        {r.checks.map((c, i) => (
          <li key={i} className="flex gap-2">
            <span>{c.pass ? "✅" : "❌"}</span>
            <span><b>{c.check}</b> — <span className="text-slate-500">{c.detail}</span></span>
          </li>))}
      </ul>
    </div>);
}
