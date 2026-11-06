# Project Udyam Digital — prototype

Digital-first acquisition & onboarding journey for Accel Business (fictional).
Built to the accompanying `PROJECT_UDYAM_BUILD_SPEC.md`. **All data is synthetic.**

This is a **starter scaffold**: the deterministic backend logic (eligibility,
quote, GSTIN checksum + OCR correction, KYC validation, propensity) is
implemented; the LLM advisor, model training and frontend screens are wired and
runnable. Build on top of it following the spec's build order (§0).

## Prerequisites
- Python 3.11+, Node 18+
- **PostgreSQL 14+** running (stores orders + consent receipts; reference data
  stays in memory). Create a database and set `DATABASE_URL`:
  ```bash
  createdb udyam     # or: psql -c "CREATE DATABASE udyam;"
  export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/udyam
  ```
  Tables are created automatically on backend startup (`db.init_db()`).
- Tesseract OCR engine (for the KYC module):
  - Debian/Ubuntu: `sudo apt-get install -y tesseract-ocr`
  - macOS: `brew install tesseract`

## 1. Add the data pack
Place the provided synthetic data here (see spec §0):
```
data/product_catalogue.csv
data/smb_leads.csv
data/mock_gstin_registry.csv
data/mock_udyam_registry.csv
data/kyc_documents/Kxx_*.png
```

## 2. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload           # http://localhost:8000  (docs at /docs)
```
Optional LLM advisor: `export LLM_API_KEY=sk-...` (without it, the advisor runs
the rules-only fallback — the demo never hard-depends on an API).

## 3. Train the propensity model (Tier 2)
```bash
python notebooks/train_propensity.py       # writes models/propensity.pkl
python notebooks/churn_nps_analysis.py      # prints segment/contract churn & NPS
```
Until the model exists, `/score` uses a documented heuristic.

## 4. Frontend
```bash
cd frontend
npm install
npm run dev                         # http://localhost:5173 (proxies /api -> :8000)
```

## Demo path (≤3 min)
1. **Start** — enter an Active GSTIN from the registry → business autofills,
   segment inferred.
2. **Advisor** — 3 questions → Value + Lite bundles (ineligible items auto-removed).
3. **Quote** — toggle add-ons, see live savings vs current spend → Accept.
4. **KYC** — accept consent → validate with the GSTIN captured at onboarding:
   `K01` (Cancelled GSTIN → **REJECT**), `K05` (missing Udyam → **REJECT**),
   `K11` (stale address proof → **REJECT**). "Run all 12" runs the OCR-only
   batch and shows the STP rate (status/identity checks need the typed GSTIN;
   unreadable certs route to **REVIEW**, never a false reject — see note below).
5. **Track** — order stages + expected activation date.
6. **Insights** — activation by GSTIN/segment/source, churn, NPS, drop reasons.

## Endpoint → module map
See spec §15. API docs auto-generated at `/docs`.

## Known behaviour & tuning notes
- **Typed GSTIN is authoritative (spec O4).** KYC status/identity checks are
  reliable when the GSTIN is captured at onboarding. In the pure-OCR batch
  (`/kyc/validate_all`, no typed input), certs whose GSTIN can't be read/repaired
  to a registry match route to **REVIEW** — by design, not a bug. The three
  planted failures that don't depend on GSTIN OCR (K05 missing doc, K11 stale
  proof) are caught in the batch; status issues (K01 Cancelled) are caught via
  the typed path. Smoke-tested: K01+typed → REJECT (Cancelled), K05 → REJECT
  (missing Udyam), K11 → REJECT (stale).
- **OCR preprocessing is a tuning surface.** These specimens are clean digital
  images; heavy deskew can occasionally hurt a read. If batch REVIEW rate is too
  high, try OCR on the original image first and fall back to preprocessing only
  on low confidence. Left as a clearly-marked tuning point in `kyc/ocr.py`.

## Assumptions made
_(Claude Code: record here any decision made mid-build that the spec didn't
cover — per spec §14.)_
- KYC "name consistency" compares the GST legal/trade name to the signatory
  card's *For business* field (not the person's name), and a mismatch routes to
  REVIEW rather than auto-reject (OCR field extraction is noisy).
- `/kyc/validate_all` runs OCR-only (no typed GSTIN) as an STP stress view.
