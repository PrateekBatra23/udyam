# Project Udyam Digital - prototype

A digital-first, phone-first, bilingual (English / Hindi) journey that takes a small
business from "who are you?" to an activated bundle in one sitting: GSTIN-first
onboarding, an advisor that recommends a bundle, a transparent quote, document OCR
KYC under DPDP-style consent, and an order tracker. A back-office dashboard shows the
business case. Fictional brand "Accel Business"; **all data is synthetic**.

```
frontend (React + Vite + Tailwind)  --/api-->  backend (FastAPI)  -->  PostgreSQL (orders, consent)
                                                   |
                          in-memory: catalogue + GSTIN/Udyam registries + leads (pandas)
                          OCR: Tesseract + OpenCV     Advisor: rules engine (+ Claude if a key is set)
```

## Prerequisites
- Python 3.10+ and Node 18+
- **PostgreSQL 14+** reachable via `DATABASE_URL`. Tables are created on startup.
  - Docker: `docker run --name udyam-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=udyam -p 5432:5432 -d postgres:16`
    (already created: `docker start udyam-pg`)
  - or any local Postgres with a database named `udyam`.
- **Tesseract OCR** engine with English data:
  - Debian/Ubuntu `sudo apt-get install -y tesseract-ocr` - macOS `brew install tesseract`
  - Windows: install Tesseract and make sure `tesseract` is on PATH. If it reports a missing
    `eng.traineddata`, set `TESSDATA_PREFIX` to the folder that contains it.

## 1. Data
Put the synthetic data pack in `data/`:
```
data/product_catalogue.csv
data/smb_leads.csv
data/mock_gstin_registry.csv
data/mock_udyam_registry.csv
data/kyc_documents/Kxx_*.png        (47 images, applicants K01-K12)
```
(The data is git-ignored. To use another location set `DATA_DIR`.)

## 2. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/udyam
uvicorn app:app --reload                                # http://localhost:8000  (docs at /docs)
```
Optional LLM advisor: `export LLM_API_KEY=sk-...`. Without a key the advisor runs its
rules-only engine, so the demo never depends on an external API. Either way, every
bundle is re-validated against the eligibility rules on the server.

## 3. Propensity model (Tier 2)
```bash
python notebooks/train_propensity.py       # writes models/propensity.pkl, prints AUC + band table
python notebooks/churn_nps_analysis.py     # churn / NPS by segment and contract length
```
(`notebooks/*.ipynb` hold the same analysis.) Until a model file exists, `/score` uses a
documented heuristic and the dashboard says so.

## 4. Frontend
```bash
cd frontend
npm install
npm run dev                                 # http://localhost:5173  (proxies /api -> :8000)
```

## 5. Tests
```bash
cd backend
pip install pytest httpx
pytest -q          # rules, pricing, advisor, KYC decisions (incl. real OCR), API, privacy
```
Tests that need Postgres are skipped automatically if it is not running.

## Demo path (about 3 minutes)
Open the app on a phone-sized viewport. Use **Try a demo business** on the first screen.

1. **Start** - pick *2. Dental clinic*. The GSTIN gets an instant tick, the business card
   fills in (10 details), the segment is a guess you confirm (*Professional office*, from the
   registered activity) and the team size is pre-filled.
2. **Advisor** - three questions (sites, current spend, top priority). Get a **Value** and a
   **Lite** bundle with plain-language reasons. Switch to Hindi with the toggle.
   *Probe:* pick demo *5* (2-person shop asking for Managed SD-WAN) - it refuses, and says why.
3. **Quote** - toggle add-ons and watch the monthly total, setup fee and contract update
   instantly. Switch off the internet line and its dependants switch off with it. Tap
   **Show me a cheaper option** for Lite. See *Today vs With Accel* and the saving.
4. **Accept** - the **consent notice** appears before anything is collected. Accept, get a
   receipt (downloadable, withdrawable) and a retention countdown.
5. **KYC** - upload four documents, or use the specimens: *K01* (Cancelled GSTIN, and no Udyam
   number on the certificate), *K05* (missing Udyam certificate), *K11* (address proof 257 days
   old) are **rejected** with the reason; *K07* (name mismatch) and *K04* (unreadable) go to
   **review**, never a false reject. **Run all 12** shows the straight-through rate.
6. **Track** - stages with a date each, and the expected activation date.
7. **Insights** - the five success metrics against their baselines, funnel, propensity bands
   (who gets self-serve vs nurture), churn / NPS, and which drop reasons the journey removes.

## What is where
```
backend/   app.py (API)  rules/ (eligibility, quote, identifiers)  advisor/  kyc/  tracker/
           propensity/  analytics.py  privacy.py  demo.py  tests/
frontend/  src/screens (6 screens)  src/components  src/i18n (en, hi)  src/lib  src/api
notebooks/ propensity model + churn/NPS analysis (.py and .ipynb)
data/      synthetic data pack (git-ignored)      models/  trained model (git-ignored)
```

## Configuration
`backend/config.py` holds every pinned constant: `TODAY` (2026-07-15, used for all date
checks instead of the system clock), retention (180 days), propensity bands, OCR confidence
and name-match thresholds. Environment: `DATABASE_URL`, `DATA_DIR`, `LLM_API_KEY`, `LLM_MODEL`.

## Privacy by design
Consent before KYC and only after a quote is accepted; uploaded images are read from a temp
folder and deleted immediately; identifiers are masked to the last four characters in the UI,
API responses and logs; identifiers never travel in URLs; consent can be withdrawn (which
erases the linked verification record); records past 180 days are purged.
