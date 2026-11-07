import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import en from "./i18n/en.json";
import hi from "./i18n/hi.json";
import { api } from "./api/client.js";
import { LangToggle } from "./components/ui.jsx";
import Onboarding from "./screens/Onboarding.jsx";
import Advisor from "./screens/Advisor.jsx";
import Checkout from "./screens/Checkout.jsx";
import KYC from "./screens/KYC.jsx";
import Tracker from "./screens/Tracker.jsx";
import BackOffice from "./screens/BackOffice.jsx";

const DICT = { en, hi };

// Shared journey state so screens can hand off profile / bundle / consent to each other.
const Ctx = createContext(null);
export const useJourney = () => useContext(Ctx);

const SCREENS = [
  ["onboard", Onboarding, "nav_onboard"],
  ["advisor", Advisor, "nav_advisor"],
  ["checkout", Checkout, "nav_checkout"],
  ["kyc", KYC, "nav_kyc"],
  ["tracker", Tracker, "nav_tracker"],
  ["backoffice", BackOffice, "nav_backoffice"],
];

const EMPTY = { biz: null, gstin: "", profile: null, answers: null, rec: null,
                choice: null, plan: null, consent: null, orderId: null, kycDecision: null };

export default function App() {
  const [lang, setLang] = useState("en");
  const [tab, setTab] = useState("onboard");
  const [journey, setJourneyState] = useState(EMPTY);
  const [catalogue, setCatalogue] = useState([]);

  useEffect(() => { api.catalogue().then(setCatalogue).catch(() => {}); }, []);

  const t = useMemo(() => (k, vars = {}) => {
    let s = DICT[lang][k] ?? DICT.en[k] ?? k;
    Object.entries(vars).forEach(([n, v]) => { s = s.replaceAll(`{${n}}`, v); });
    return s;
  }, [lang]);

  const setJourney = (fn) => setJourneyState((j) => (typeof fn === "function" ? fn(j) : { ...j, ...fn }));
  const reset = () => { setJourneyState(EMPTY); setTab("onboard"); };
  const value = { lang, setLang, t, journey, setJourney, goto: setTab, catalogue, reset };
  const Active = SCREENS.find(([k]) => k === tab)[1];

  return (
    <Ctx.Provider value={value}>
      <div className="max-w-md mx-auto min-h-screen flex flex-col">
        <header className="px-4 pt-5 pb-3 flex items-center justify-between">
          <div>
            <div className="text-accel font-bold text-lg leading-tight">{t("app_title")}</div>
            <div className="text-xs text-slate-500">{t("tagline")}</div>
          </div>
          <LangToggle lang={lang} setLang={setLang} />
        </header>

        <main className="flex-1 px-4 pb-24"><Active /></main>

        <nav className="fixed bottom-0 inset-x-0 max-w-md mx-auto bg-white border-t border-slate-100
                        flex justify-around py-2 text-xs" aria-label="Journey steps">
          {SCREENS.map(([k, , labelKey]) => (
            <button key={k} onClick={() => setTab(k)} aria-current={tab === k ? "page" : undefined}
              className={`px-2 py-1 rounded-lg ${tab === k ? "text-accel font-semibold" : "text-slate-400"}`}>
              {t(labelKey)}
            </button>
          ))}
        </nav>
      </div>
    </Ctx.Provider>
  );
}
