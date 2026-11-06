import React from "react";

export const rupee = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");

export function MaskedId({ value }) {
  const s = String(value || "");
  return <span className="font-mono">{"•".repeat(Math.max(s.length - 4, 0)) + s.slice(-4)}</span>;
}

export function MetricTile({ label, value, sub }) {
  return (
    <div className="card !p-4">
      <div className="text-2xl font-bold text-accel">{value}</div>
      <div className="text-xs text-slate-500 mt-1">{label}</div>
      {sub && <div className="text-[11px] text-slate-400 mt-0.5">{sub}</div>}
    </div>
  );
}

export function BundleCard({ title, quote, selected, onSelect }) {
  if (!quote) return null;
  const s = quote.savings;
  return (
    <div className={`card ${selected ? "ring-2 ring-accel" : ""}`}>
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{title}</h3>
        <span className="pill bg-accel-light text-accel">{quote.contract_months} mo</span>
      </div>
      <div className="mt-2 text-3xl font-bold">{rupee(quote.monthly_inr)}
        <span className="text-sm font-normal text-slate-500"> /mo</span></div>
      <div className="text-xs text-slate-500">{rupee(quote.one_time_inr)} one-time setup</div>
      {s && s.monthly_saving_inr > 0 && (
        <div className="mt-2 text-save text-sm font-medium">
          {rupee(s.monthly_saving_inr)}/mo cheaper than you pay now
        </div>)}
      <ul className="mt-3 space-y-1 text-sm">
        {(quote.products || quote.lines || []).map((p) => (
          <li key={p.product_id} className="flex justify-between">
            <span>{p.name || p.product_id}</span>
            <span className="text-slate-500">{rupee(p.monthly_inr || 0)}</span>
          </li>))}
      </ul>
      {onSelect && <button className="btn w-full mt-4" onClick={onSelect}>Choose {title}</button>}
    </div>
  );
}
