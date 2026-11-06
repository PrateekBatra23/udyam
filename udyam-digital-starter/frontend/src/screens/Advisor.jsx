import React, { useEffect, useState } from "react";
import { useJourney } from "../App.jsx";
import { api } from "../api/client.js";
import { BundleCard, Empty, Field, rupee } from "../components/ui.jsx";

// O2 - asks only 2-3 questions (sites, current spend, top priority); GSTIN autofill
// already supplied everything else. Returns Value + Lite bundles and explains any
// refusal in plain language.
export default function Advisor() {
  const { t, lang, journey, setJourney, goto } = useJourney();
  const p = journey.profile;
  const demo = journey.demo;
  const [qs, setQs] = useState([]);
  const [sites, setSites] = useState(p?.num_sites || 1);
  const [spend, setSpend] = useState(demo?.current_spend ?? "");
  const [priority, setPriority] = useState(demo?.priority || "price");
  const [message, setMessage] = useState(demo?.message || "");
  const [rec, setRec] = useState(journey.rec);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (p) api.questions(p.segment, lang).then(setQs).catch(() => {}); }, [p?.segment, lang]);
  useEffect(() => { if (p && journey.rec === null) setRec(null); }, [journey.rec]);

  if (!p) return <Empty text={t("gstin_label")} cta={t("nav_onboard")} onClick={() => goto("onboard")} />;
  const q = Object.fromEntries(qs.map((x) => [x.id, x]));

  async function recommend() {
    setBusy(true); setErr("");
    const profile = { ...p, num_sites: Number(sites) || 1 };
    try {
      const r = await api.recommend({
        gstin: journey.gstin || null, profile, current_spend: spend === "" ? null : Number(spend),
        language: lang, priority, message: message || null,
        requested: demo?.requested && message === demo.message ? demo.requested : null });
      setRec(r);
      setJourney((j) => ({ ...j, profile, rec: r, answers: { sites: profile.num_sites, spend: spend === "" ? null : Number(spend), priority } }));
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  function choose(which) {
    setJourney((j) => ({ ...j, choice: which, plan: null }));
    goto("checkout");
  }

  return (
    <div className="space-y-4">
      <div className="card space-y-4">
        <p className="text-sm text-slate-500">{t("advisor_intro", { n: qs.length || 3 })}</p>
        <Field label={q.num_sites?.text}>
          <input type="number" min="1" max="50" className="input" value={sites} onChange={(e) => setSites(e.target.value)} />
        </Field>
        <Field label={q.current_spend?.text} hint={q.current_spend?.why}>
          <input type="number" min="0" step="100" className="input" value={spend} placeholder="e.g. 2000"
                 onChange={(e) => setSpend(e.target.value)} />
        </Field>
        <div>
          <div className="text-sm font-medium">{q.priority?.text}</div>
          <div className="flex flex-wrap gap-2 mt-2" role="radiogroup" aria-label={q.priority?.text}>
            {(q.priority?.options || []).map((o) => (
              <button key={o.value} role="radio" aria-checked={priority === o.value} onClick={() => setPriority(o.value)}
                className={`pill !px-3 !py-1.5 border ${priority === o.value ? "bg-accel text-white border-accel" : "bg-white text-slate-600 border-slate-200"}`}>
                {o.label}</button>))}
          </div>
        </div>
        <Field label={t("advisor_request")}>
          <input className="input" value={message} placeholder={t("advisor_request_ph")} onChange={(e) => setMessage(e.target.value)} />
        </Field>
        <button className="btn w-full" onClick={recommend} disabled={busy}>{busy ? t("thinking") : t("advisor_cta")}</button>
        {err && <p className="text-sm text-red-600" role="alert">{err}</p>}
      </div>

      {rec && (
        <>
          {rec.refusals?.map((r) => (
            <div key={r.product_id} className="card border-amber-200 bg-amber-50" role="status">
              <div className="font-semibold text-amber-800">{t("refused_title")}: {r.name}</div>
              <p className="text-sm text-amber-900 mt-1">{r.message}</p>
            </div>))}

          <div className="card text-sm text-slate-700">
            <div className="font-semibold mb-1">{t("why_this")}</div>
            <p>{rec.rationale}</p>
            {rec.retention && (
              <p className="text-xs text-slate-500 mt-2">{t("ltv_line", { v: rupee(rec.retention.value_ltv_inr) })}
                {" · "}{rec.retention.segment_6m_churn_pct}% 6-month churn in your segment (n={rec.retention.n_activated})</p>)}
          </div>

          <BundleCard title={t("value_bundle")} quote={rec.value} recommended={rec.recommended === "value"}
            tag={rec.recommended === "value" ? t("recommended") : null}
            onSelect={() => choose("value")} selectLabel={t("choose", { name: t("value_bundle") })} />
          <BundleCard title={t("lite_bundle")} quote={rec.lite} recommended={rec.recommended === "lite"}
            tag={rec.recommended === "lite" ? t("recommended") : null}
            onSelect={() => choose("lite")} selectLabel={t("choose", { name: t("lite_bundle") })} />
          <p className="text-[11px] text-slate-400 text-center">
            {rec.source === "llm" ? "AI advisor" : "Rules advisor"} · every product is checked against eligibility rules on our server.
            {rec.llm_error && " (AI unavailable - rules answer shown)"}</p>
        </>)}
    </div>
  );
}
