import React, { useEffect, useState } from "react";
import { useJourney } from "../App.jsx";
import { api } from "../api/client.js";
import { checkGstin } from "../lib/gstin.js";
import { Field, MaskedId } from "../components/ui.jsx";

// O1 - GSTIN-first onboarding: instant client-side validation, registry autofill,
// confirmable segment guess. "No GSTIN" routes to a lighter path.
const SEGS = ["micro", "prof", "multi", "mfg"];

export default function Onboarding() {
  const { t, setJourney, goto, journey, reset } = useJourney();
  const [gstin, setGstin] = useState(journey.gstin || "");
  const [found, setFound] = useState(journey.biz || null);
  const [segment, setSegment] = useState(journey.profile?.segment || "micro");
  const [team, setTeam] = useState(journey.profile?.employee_count || 3);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [demos, setDemos] = useState([]);
  const [skip, setSkip] = useState(false);
  const [tier, setTier] = useState(2);
  const [route, setRoute] = useState(null);
  const [sitesOv, setSitesOv] = useState(null);   // demo profiles carry their own site count

  const check = checkGstin(gstin);
  useEffect(() => { api.demoProfiles().then(setDemos).catch(() => {}); }, []);

  async function lookup(value = gstin) {
    setErr(""); setFound(null); setBusy(true);
    try {
      const d = await api.onboard(value.trim().toUpperCase());
      setFound(d);
      setSegment(d.inferred_segment.segment);
      setTeam(d.employee_prior);
      setTier(d.city_tier);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  function pickDemo(id) {
    const d = demos.find((x) => String(x.id) === id);
    if (!d) return;
    setJourney({ demo: d });
    if (d.gstin) {
      setSkip(false); setGstin(d.gstin);
      lookup(d.gstin).then(() => { setTeam(d.profile.employee_count); setSitesOv(d.profile.num_sites); });
    }
    else {
      setFound(null); setSkip(true); setSegment(d.profile.segment);
      setTeam(d.profile.employee_count); setTier(d.profile.city_tier); setGstin("");
    }
  }

  async function continueWithGstin() {
    setJourney({ biz: found, gstin: found.gstin, profile: {
      segment, city_tier: found.city_tier, employee_count: Number(team), num_sites: sitesOv || found.sites_prior || 1,
      legal_name: found.legal_name, city: found.city }, rec: null, plan: null });
    goto("advisor");
  }

  async function continueWithoutGstin() {
    const profile = { segment, city_tier: Number(tier), employee_count: Number(team), num_sites: 1 };
    // the skip-GSTIN lead goes through the propensity model: it decides the routing
    try { setRoute(await api.score({ has_gstin: "N", segment, city_tier: tier, employee_count: team, lead_source: "Website form" })); } catch {}
    setJourney({ biz: null, gstin: "", profile, rec: null, plan: null });
    goto("advisor");
  }

  const tone = { ok: "text-save", bad_format: "text-red-600", bad_checksum: "text-red-600", typing: "text-slate-400", empty: "" }[check.state];

  return (
    <div className="space-y-4">
      {demos.length > 0 && (
        <div className="card !p-3 flex items-center gap-2 text-sm">
          <span className="text-slate-500 whitespace-nowrap">{t("demo_pick")}</span>
          <select className="input !py-1.5" defaultValue="" onChange={(e) => pickDemo(e.target.value)} aria-label={t("demo_pick")}>
            <option value="" disabled>-</option>
            {demos.map((d) => <option key={d.id} value={d.id}>{d.id}. {d.title}</option>)}
          </select>
        </div>)}

      {!skip && (
        <div className="card">
          <label htmlFor="gstin" className="text-sm font-medium">{t("gstin_label")}</label>
          <div className="relative mt-2">
            <input id="gstin" className={`input pr-10 uppercase font-mono ${check.state === "ok" ? "!border-save" : check.state.startsWith("bad") ? "!border-red-400" : ""}`}
              value={gstin} maxLength={15} placeholder={t("gstin_hint")} autoComplete="off" inputMode="text"
              onChange={(e) => setGstin(e.target.value.toUpperCase().replace(/\s/g, ""))}
              aria-invalid={check.state.startsWith("bad")} aria-describedby="gstin-msg" />
            <span className={`absolute right-3 top-2.5 text-lg ${tone}`} aria-hidden="true">
              {check.state === "ok" ? "✓" : check.state.startsWith("bad") ? "✗" : ""}</span>
          </div>
          <p id="gstin-msg" className={`text-xs mt-1 min-h-[1rem] ${tone}`}>{check.message}</p>
          <button className="btn w-full mt-3" onClick={() => { setSitesOv(null); lookup(); }} disabled={check.state !== "ok" || busy}>
            {busy ? t("thinking") : t("gstin_cta")}</button>
          {err && <p className="text-sm text-red-600 mt-2" role="alert">{err}</p>}
          <button className="text-xs text-slate-500 mt-4 underline" onClick={() => { setSkip(true); setFound(null); }}>
            {t("gstin_skip")}</button>
        </div>)}

      {found && !found.accepted && (
        <div className="card border-red-200 bg-red-50" role="alert">
          <div className="font-semibold text-red-700">{t("gstin_rejected")}</div>
          <div className="text-sm mt-1">{found.legal_name}</div>
          <p className="text-sm text-red-700 mt-1">{found.reject_reason}</p>
        </div>)}

      {found && found.accepted && (
        <div className="card">
          <div className="text-xs text-slate-400">{t("found_title")} - {t("autofilled", { n: found.autofilled_fields })}</div>
          <div className="font-semibold text-lg">{found.legal_name}</div>
          <div className="text-sm text-slate-500">{found.constitution} · {found.city}, {found.state} (Tier {found.city_tier})</div>
          <div className="text-xs mt-1 text-slate-500">GSTIN <MaskedId value={found.gstin} />
            <span className="pill ml-2 bg-save/10 text-save">{found.status}</span>
            {found.udyam && <span className="ml-2">Udyam <MaskedId value={found.udyam.udyam_number} /> · {found.udyam.enterprise_type}</span>}</div>

          <div className="mt-4 space-y-3">
            <Field label={t("confirm_segment")}
              hint={t("segment_guess", { conf: found.inferred_segment.confidence, basis: found.inferred_segment.basis })}>
              <select className="input" value={segment} onChange={(e) => { setSegment(e.target.value); }}>
                {SEGS.map((k) => <option key={k} value={k}>{t("seg_" + k)}</option>)}
              </select>
            </Field>
            <Field label={t("team_size")} hint={t("team_size_note")}>
              <input type="number" min="1" className="input" value={team} onChange={(e) => setTeam(e.target.value)} />
            </Field>
          </div>
          <button className="btn w-full mt-4" onClick={continueWithGstin}>{t("continue_advisor")}</button>
        </div>)}

      {skip && (
        <div className="card space-y-3">
          <p className="text-sm text-slate-600">{t("gstin_skip_note")}</p>
          <Field label={t("confirm_segment")}>
            <select className="input" value={segment} onChange={(e) => setSegment(e.target.value)}>
              {SEGS.map((k) => <option key={k} value={k}>{t("seg_" + k)}</option>)}</select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("team_size")}><input type="number" min="1" className="input" value={team} onChange={(e) => setTeam(e.target.value)} /></Field>
            <Field label="City tier"><select className="input" value={tier} onChange={(e) => setTier(e.target.value)}>
              <option value="1">Tier 1</option><option value="2">Tier 2</option></select></Field>
          </div>
          {route && <p className="text-xs text-slate-500">Route: {route.recommended_action} ({route.band})</p>}
          <button className="btn w-full" onClick={continueWithoutGstin}>{t("continue_advisor")}</button>
          <button className="text-xs text-slate-500 underline" onClick={() => setSkip(false)}>← GSTIN</button>
        </div>)}

      {journey.profile && (
        <button className="text-xs text-slate-400 underline" onClick={reset}>Start over</button>)}
    </div>
  );
}
