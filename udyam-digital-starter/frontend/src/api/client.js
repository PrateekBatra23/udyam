// All backend calls go through here. In dev, Vite proxies /api -> :8000.
const BASE = import.meta.env.VITE_API_BASE || "/api";

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

export const api = {
  health: () => req("/health"),
  catalogue: () => req("/catalogue"),
  onboard: (gstin, udyam) =>
    req(`/onboard?gstin=${encodeURIComponent(gstin)}${udyam ? `&udyam=${udyam}` : ""}`),
  recommend: (profile, current_spend, language = "en") =>
    req("/advisor/recommend", { method: "POST", body: JSON.stringify({ profile, current_spend, language }) }),
  quote: (payload) => req("/quote", { method: "POST", body: JSON.stringify(payload) }),
  kycValidate: (applicant, typed_gstin) =>
    req(`/kyc/validate?applicant=${applicant}${typed_gstin ? `&typed_gstin=${typed_gstin}` : ""}`),
  kycAll: () => req("/kyc/validate_all"),
  createOrder: (bundle) => req("/order", { method: "POST", body: JSON.stringify({ bundle }) }),
  getOrder: (id) => req(`/order/${id}`),
  advanceOrder: (id) => req(`/order/${id}/advance`, { method: "POST" }),
  score: (lead) => req("/score", { method: "POST", body: JSON.stringify({ lead }) }),
  analytics: () => req("/analytics/summary"),
  consent: () => req("/privacy/consent"),
};
