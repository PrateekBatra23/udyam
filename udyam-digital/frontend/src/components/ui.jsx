import React from "react";

export const rupee = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");

// Identifiers are shown last-4 only after capture (DPDP / spec O8).
export function MaskedId({ value }) {
  const s = String(value || "");
  if (s.includes("*") || s.includes("•")) return <span className="font-mono">{s.replaceAll("*", "•")}</span>;
  return <span className="font-mono">{"•".repeat(Math.max(s.length - 4, 0)) + s.slice(-4)}</span>;
}

export function MetricTile({ label, value, sub, tone }) {
  return (
    <div className="card !p-4">
      <div className={`text-2xl font-bold ${tone === "good" ? "text-save" : "text-accel"}`}>{value}</div>
      <div className="text-xs text-slate-500 mt-1">{label}</div>
      {sub && <div className="text-[11px] text-slate-400 mt-0.5">{sub}</div>}
    </div>
  );
}

export function LangToggle({ lang, setLang }) {
  return (
    <div className="flex rounded-full bg-accel-light p-0.5 text-xs font-medium" role="group" aria-label="Language">
      {[["en", "EN"], ["hi", "हिन्दी"]].map(([k, label]) => (
        <button key={k} onClick={() => setLang(k)} aria-pressed={lang === k}
          className={`px-3 py-1 rounded-full ${lang === k ? "bg-accel text-white" : "text-accel"}`}>{label}</button>
      ))}
    </div>
  );
}

export function BundleCard({ title, quote, recommended, onSelect, selectLabel, tag }) {
  if (!quote) return null;
  const s = quote.savings;
  return (
    <div className={`card ${recommended ? "ring-2 ring-accel" : ""}`}>
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{title}</h3>
        <div className="flex gap-1">
          {tag && <span className="pill bg-save/10 text-save">{tag}</span>}
          <span className="pill bg-accel-light text-accel">{quote.contract_months} mo</span>
        </div>
      </div>
      <div className="mt-2 text-3xl font-bold">{rupee(quote.monthly_inr)}
        <span className="text-sm font-normal text-slate-500"> /mo</span></div>
      <div className="text-xs text-slate-500">{rupee(quote.one_time_inr)} one-time setup</div>
      {s && s.monthly_saving_inr > 0 && (
        <div className="mt-2 text-save text-sm font-medium">
          {rupee(s.monthly_saving_inr)}/mo cheaper than you pay now</div>)}
      <ul className="mt-3 space-y-2 text-sm">
        {quote.products.map((p) => (
          <li key={p.product_id}>
            <div className="flex justify-between gap-2">
              <span className="font-medium">{p.name}</span>
              <span className="text-slate-500 whitespace-nowrap">{rupee(p.monthly_inr)}</span>
            </div>
            <div className="text-xs text-slate-500">{p.reason}</div>
          </li>))}
      </ul>
      {onSelect && <button className="btn w-full mt-4" onClick={onSelect}>{selectLabel}</button>}
    </div>
  );
}

// Consent notice shown BEFORE any KYC collection (DPDP Act 2023, spec O8).
export function ConsentModal({ notice, t, onAccept, onDecline, busy }) {
  if (!notice) return null;
  return (
    <div className="fixed inset-0 z-20 bg-black/40 flex items-end sm:items-center justify-center"
         role="dialog" aria-modal="true" aria-labelledby="consent-h">
      <div className="bg-white rounded-t-3xl sm:rounded-3xl max-w-md w-full max-h-[90vh] overflow-y-auto p-5">
        <h3 id="consent-h" className="font-semibold text-lg">{t("consent_title")}</h3>
        <dl className="mt-3 space-y-3 text-sm">
          <div><dt className="font-medium">{t("consent_collect")}</dt>
            <dd className="text-slate-600">{notice.collected.join(", ")}</dd></div>
          <div><dt className="font-medium">{t("consent_purpose")}</dt>
            <dd className="text-slate-600">{notice.purpose}</dd></div>
          <div><dt className="font-medium">{t("consent_retention")}</dt>
            <dd className="text-slate-600">{t("consent_days", { n: notice.retention_days })}</dd></div>
          <div><dt className="font-medium">{t("consent_rights")}</dt>
            <dd className="text-slate-600">{notice.rights}</dd></div>
        </dl>
        <p className="text-xs text-slate-400 mt-3">{notice.minimisation}</p>
        <button className="btn w-full mt-4" onClick={onAccept} disabled={busy}>{t("consent_accept")}</button>
        <button className="btn-ghost w-full mt-2" onClick={onDecline}>{t("consent_decline")}</button>
      </div>
    </div>
  );
}

export const Field = ({ label, hint, children }) => (
  <label className="block">
    <span className="text-sm font-medium">{label}</span>
    {hint && <span className="block text-[11px] text-slate-400">{hint}</span>}
    <div className="mt-1">{children}</div>
  </label>
);

export const Empty = ({ text, cta, onClick }) => (
  <div className="card text-center text-slate-500">{text}
    <div><button className="btn mt-3" onClick={onClick}>{cta}</button></div></div>
);
