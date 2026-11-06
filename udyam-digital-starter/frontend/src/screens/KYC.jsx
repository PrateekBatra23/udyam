import React, { useEffect, useState } from "react";
import { useJourney } from "../App.jsx";
import { api } from "../api/client.js";
import { ConsentModal, Empty, MaskedId } from "../components/ui.jsx";

// O4 + O8 - consent first (nothing is collected before it), then upload + validate.
const SLOTS = ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"];
const STYLE = { APPROVE: "bg-save/10 text-save", REJECT: "bg-red-100 text-red-600", REVIEW: "bg-amber-100 text-amber-700" };
const SEV = { fail: "❌", review: "⚠️", ok: "✅" };

export default function KYC() {
  const { t, journey, setJourney, goto } = useJourney();
  const [notice, setNotice] = useState(null);
  const [asking, setAsking] = useState(false);
  const [declined, setDeclined] = useState(false);
  const [files, setFiles] = useState({});
  const [result, setResult] = useState(null);
  const [batch, setBatch] = useState(null);
  const [applicants, setApplicants] = useState([]);
  const [applicant, setApplicant] = useState("K02");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const receipt = journey.consent;

  useEffect(() => { api.consentNotice().then(setNotice).catch(() => {}); }, []);
  useEffect(() => { if (!receipt && notice && !declined) setAsking(true); }, [notice, receipt, declined]);
  useEffect(() => { if (receipt) api.kycApplicants().catch(() => []).then((a) => a && setApplicants(a)); }, [receipt]);

  // KYC is only reachable after quote acceptance (data minimisation, spec O8)
  if (!journey.orderId && !receipt) return <Empty text={t("no_bundle")} cta={t("nav_checkout")} onClick={() => goto("checkout")} />;

  async function accept() {
    setBusy(true);
    try {
      const r = await api.recordConsent(journey.gstin || "visitor");
      setJourney({ consent: r }); setAsking(false);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  async function run(fn) {
    setBusy(true); setErr(""); setResult(null); setBatch(null);
    try { await fn(); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  const upload = () => run(async () => {
    const f = new FormData();
    SLOTS.forEach((s) => files[s] && f.append(s, files[s]));
    if (journey.gstin) f.append("typed_gstin", journey.gstin);
    if (journey.orderId) f.append("order_id", journey.orderId);
    const r = await api.kycUpload(f, receipt.receipt_id);
    setResult(r); setJourney({ kycDecision: r.decision });
  });
  const specimen = () => run(async () => setResult(await api.kycValidate(applicant, receipt.receipt_id)));
  const all = () => run(async () => setBatch(await api.kycAll(receipt.receipt_id)));

  async function withdraw() {
    if (!window.confirm("Withdraw consent? The verification record linked to it will be erased.")) return;
    try { await api.withdrawConsent(receipt.receipt_id); setJourney({ consent: null, kycDecision: null }); setResult(null); setBatch(null); setDeclined(true); }
    catch (e) { setErr(e.message); }
  }

  function download() {
    const blob = new Blob([JSON.stringify(receipt, null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `${receipt.receipt_id}.json`; a.click();
  }
  const daysLeft = receipt ? Math.max(0, Math.ceil((new Date(receipt.retention_until) - new Date()) / 864e5)) : null;

  return (
    <div className="space-y-4">
      {asking && !receipt && (
        <ConsentModal notice={notice} t={t} busy={busy} onAccept={accept}
          onDecline={() => { setAsking(false); setDeclined(true); }} />)}

      {!receipt && (
        <div className="card text-center text-slate-600">
          <p className="text-sm">{t("consent_title")}</p>
          <button className="btn mt-3" onClick={() => { setDeclined(false); setAsking(true); }}>{t("consent_accept")}</button>
          {err && <p className="text-sm text-red-600 mt-2">{err}</p>}
        </div>)}

      {receipt && (
        <>
          <div className="card !p-4 text-sm">
            <div className="flex justify-between items-start">
              <div>
                <div className="font-medium">{t("consent_receipt")} <span className="font-mono text-xs">{receipt.receipt_id}</span></div>
                <div className="text-xs text-slate-500">{new Date(receipt.timestamp_utc).toLocaleString()} · <MaskedId value={receipt.business_ref} /></div>
                <div className="text-xs text-save mt-1">{t("retention_countdown", { n: daysLeft })}</div>
              </div>
              <div className="flex flex-col gap-1 items-end">
                <button className="pill bg-accel-light text-accel" onClick={download}>{t("download_receipt")}</button>
                <button className="pill bg-slate-100 text-slate-600" onClick={withdraw}>{t("withdraw")}</button>
              </div>
            </div>
          </div>

          <div className="card space-y-3">
            <h3 className="font-semibold">{t("kyc_upload_title")}</h3>
            {journey.gstin && <p className="text-xs text-slate-500">GSTIN <MaskedId value={journey.gstin} /></p>}
            {SLOTS.map((s) => (
              <label key={s} className="block text-sm">
                <span className="font-medium">{t("kyc_slot_" + s)}</span>
                <input type="file" accept="image/png,image/jpeg" className="block w-full text-xs mt-1"
                  onChange={(e) => setFiles((f) => ({ ...f, [s]: e.target.files[0] }))} />
              </label>))}
            <button className="btn w-full" onClick={upload} disabled={busy || !Object.keys(files).length}>
              {busy ? t("verifying") : t("verify")}</button>
          </div>

          <div className="card space-y-2">
            <div className="text-sm font-medium">{t("kyc_demo")}</div>
            <div className="flex gap-2">
              <select className="input" value={applicant} onChange={(e) => setApplicant(e.target.value)}>
                {applicants.map((k) => <option key={k}>{k}</option>)}</select>
              <button className="btn" onClick={specimen} disabled={busy}>{t("verify")}</button>
            </div>
            <button className="btn-ghost w-full" onClick={all} disabled={busy}>{busy ? t("verifying") : t("run_all")}</button>
          </div>
        </>)}

      {err && receipt && <p className="text-sm text-red-600" role="alert">{err}</p>}
      {result && <ResultCard r={result} t={t} onTrack={() => goto("tracker")} />}

      {batch && (
        <div className="card">
          <div className="text-3xl font-bold text-accel" data-testid="stp">{batch.stp_rate}%</div>
          <div className="text-xs text-slate-500">{t("stp")} ({batch.approved}/{batch.total}) ·
            {" "}{batch.review} review · {batch.rejected} rejected</div>
          <ul className="mt-3 space-y-2 text-sm">
            {batch.results.map((r) => (
              <li key={r.applicant}>
                <div className="flex justify-between"><span>{r.applicant}</span>
                  <span className={`pill ${STYLE[r.decision]}`}>{t("decision_" + r.decision)}</span></div>
                {r.reasons.slice(0, 2).map((x, i) => (
                  <div key={i} className="text-[11px] text-slate-500 ml-2">{SEV[x.severity]} {x.reason}</div>))}
              </li>))}
          </ul>
        </div>)}
    </div>
  );
}

function ResultCard({ r, t, onTrack }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <span className="font-semibold">{r.applicant}</span>
        <span className={`pill ${STYLE[r.decision]}`}>{t("decision_" + r.decision)}</span>
      </div>
      <div className="text-xs text-slate-400">mean OCR confidence {r.mean_confidence}
        {r.gstin_masked && <> · GSTIN <MaskedId value={r.gstin_masked} /> ({r.gstin_source})</>}</div>

      {r.reasons.length > 0 && (
        <ul className="mt-3 space-y-1.5 text-sm">
          {r.reasons.map((x, i) => (
            <li key={i} className="flex gap-2"><span>{SEV[x.severity]}</span>
              <span>{x.reason}{x.doc && <span className="text-slate-400"> - {x.doc.replaceAll("_", " ")}</span>}</span></li>))}
        </ul>)}

      <details className="mt-3 text-xs">
        <summary className="cursor-pointer text-slate-500">All checks ({r.checks.length}) and extracted fields</summary>
        <ul className="mt-2 space-y-1">
          {r.checks.map((c, i) => (
            <li key={i}>{SEV[c.severity]} <b>{c.check.replaceAll("_", " ")}</b> - <span className="text-slate-500">{c.detail}</span></li>))}
        </ul>
        {Object.entries(r.extracted).map(([doc, d]) => (
          <div key={doc} className="mt-2">
            <div className="font-medium">{doc.replaceAll("_", " ")} <span className="text-slate-400">(conf {d.confidence})</span></div>
            {Object.entries(d.fields).map(([k, v]) => (
              <div key={k} className="flex justify-between text-slate-600"><span>{k}</span>
                <span>{v.value} <span className="text-slate-400">{Math.round(v.conf)}%</span></span></div>))}
          </div>))}
      </details>
      {r.decision === "APPROVE" && <button className="btn w-full mt-4" onClick={onTrack}>{t("nav_tracker")} →</button>}
    </div>
  );
}
