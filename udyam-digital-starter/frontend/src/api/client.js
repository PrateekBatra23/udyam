// All backend calls go through here. In dev, Vite proxies /api -> :8000.
const BASE = import.meta.env.VITE_API_BASE || "/api";

async function req(path, opts = {}) {
  const isForm = opts.body instanceof FormData;
  const res = await fetch(BASE + path, {
    ...opts,
    headers: { ...(isForm ? {} : { "Content-Type": "application/json" }), ...(opts.headers || {}) },
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : (j.detail?.message || JSON.stringify(j.detail)); } catch {}
    const e = new Error(msg); e.status = res.status; throw e;
  }
  return res.json();
}
const post = (path, body) => req(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => req("/health"),
  catalogue: () => req("/catalogue"),
  demoProfiles: () => req("/demo/profiles"),
  onboard: (gstin) => req(`/onboard?gstin=${encodeURIComponent(gstin)}`),
  questions: (segment, lang) => req(`/advisor/questions?segment=${segment}&lang=${lang}`),
  recommend: (body) => post("/advisor/recommend", body),
  quote: (body) => post("/quote", body),
  createOrder: (body) => post("/order", body),
  getOrder: (id) => req(`/order/${id}`),
  advanceOrder: (id) => req(`/order/${id}/advance`, { method: "POST" }),
  consentNotice: () => req("/privacy/consent"),
  recordConsent: (ref) => req(`/privacy/consent?business_ref=${encodeURIComponent(ref || "visitor")}`, { method: "POST" }),
  getConsent: (id) => req(`/privacy/consent/${id}`),
  kycApplicants: () => req("/kyc/applicants"),
  kycValidate: (applicant, receipt, typedGstin) =>
    req(`/kyc/validate?applicant=${applicant}${typedGstin ? `&typed_gstin=${typedGstin}` : ""}`, { headers: { "X-Consent-Receipt": receipt } }),
  kycAll: (receipt) => req("/kyc/validate_all", { headers: { "X-Consent-Receipt": receipt } }),
  kycUpload: (form, receipt) => req("/kyc/upload", { method: "POST", body: form, headers: { "X-Consent-Receipt": receipt } }),
  score: (lead) => post("/score", { lead }),
  analytics: () => req("/analytics/summary"),
  retention: () => req("/analytics/retention"),
  leads: (limit = 25, band) => req(`/analytics/leads?limit=${limit}${band ? `&band=${band}` : ""}`),
};
