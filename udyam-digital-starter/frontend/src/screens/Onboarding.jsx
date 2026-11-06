import React, { useState } from "react";
import { useJourney } from "../App.jsx";
import { api } from "../api/client.js";

// O1 — GSTIN-first onboarding with registry autofill + confirmable segment.
const SEG_LABEL = { micro: "Micro retail & services", prof: "Professional office",
                    multi: "Small multi-site business", mfg: "Small manufacturer" };

export default function Onboarding() {
  const { t, setJourney, goto } = useJourney();
  const [gstin, setGstin] = useState("");
  const [found, setFound] = useState(null);
  const [segment, setSegment] = useState("micro");
  const [err, setErr] = useState("");

  async function lookup() {
    setErr(""); setFound(null);
    try {
      const d = await api.onboard(gstin.trim().toUpperCase());
      setFound(d);
      setSegment(d.inferred_segment?.segment || "micro");
    } catch (e) { setErr("GSTIN not found in registry. Check and retry, or continue without one."); }
  }

  function confirm() {
    setJourney((j) => ({ ...j, profile: {
      segment, city_tier: 1, employee_count: 10, num_sites: 1,
      has_active_gstin: found?.status === "Active", gstin,
      legal_name: found?.legal_name } }));
    goto("advisor");
  }

  return (
    <div className="space-y-4">
      <div className="card">
        <label className="text-sm font-medium">{t("gstin_label")}</label>
        <input className="input mt-2" value={gstin} placeholder="e.g. 32TTNXB7384T1ZW"
               onChange={(e) => setGstin(e.target.value)} />
        <button className="btn w-full mt-3" onClick={lookup} disabled={gstin.length < 10}>
          {t("gstin_cta")}
        </button>
        {err && <p className="text-xs text-amber-600 mt-2">{err}</p>}
        <button className="text-xs text-slate-400 mt-3 underline"
                onClick={() => { setJourney((j) => ({ ...j, profile: { segment: "micro",
                  city_tier: 2, employee_count: 2, num_sites: 1, has_active_gstin: false } }));
                  goto("advisor"); }}>
          I don't have a GSTIN — continue
        </button>
      </div>

      {found && (
        <div className="card">
          <div className="text-xs text-slate-400">We found your business</div>
          <div className="font-semibold text-lg">{found.legal_name}</div>
          <div className="text-sm text-slate-500">{found.constitution} · {found.state}</div>
          <div className="text-sm mt-1">Status:
            <span className={`pill ml-1 ${found.status === "Active" ? "bg-save/10 text-save" : "bg-red-100 text-red-600"}`}>
              {found.status}</span>
          </div>
          <div className="mt-4">
            <div className="text-sm font-medium">{t("confirm_segment")}</div>
            <select className="input mt-1" value={segment} onChange={(e) => setSegment(e.target.value)}>
              {Object.entries(SEG_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <p className="text-[11px] text-slate-400 mt-1">
              Guessed from your registration ({found.inferred_segment?.confidence} confidence) — adjust if wrong.
            </p>
          </div>
          <button className="btn w-full mt-4" onClick={confirm}>Continue to advisor</button>
        </div>)}
    </div>
  );
}
