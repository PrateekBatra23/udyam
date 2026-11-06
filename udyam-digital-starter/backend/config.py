"""Central config. Every tunable the spec pins (sections 0, 14C) lives here."""
import os
import re
from datetime import date


def parse_dotenv(text: str) -> dict:
    """Minimal .env parser: KEY=VALUE lines, optional quotes, '# comments' (whole-line or
    after whitespace). No dependency needed."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = re.split(r"\s+#", val.strip(), maxsplit=1)[0].strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key.strip()] = val
    return out


def _load_dotenv():
    """Load <project>/.env into the environment (real environment variables win)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    try:
        with open(path, encoding="utf-8") as f:
            for k, v in parse_dotenv(f.read()).items():
                if v != "":
                    os.environ.setdefault(k, v)
    except OSError:
        pass


_load_dotenv()

# --- Section 0 constants ---
TODAY = date(2026, 7, 15)                      # all date checks use this, not the clock
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
ADDRESS_PROOF_MAX_AGE_DAYS = 90                # reject proofs older than this before TODAY

# --- LLM (Advisor) ---
LLM_API_KEY = (os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
               or os.environ.get("GOOGLE_API_KEY") or "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-2.5-flash")   # Google Gemini
USE_LLM = bool(LLM_API_KEY)                    # if False, advisor uses rules-only fallback

# --- Section 14C thresholds ---
PROPENSITY_HIGH = 0.15
PROPENSITY_MED = 0.07                          # Med band = [MED, HIGH); Low < MED
OCR_AUTO_APPROVE_CONFIDENCE = 80               # mean field confidence to auto-approve
NAME_MATCH = 0.85                              # >= match
NAME_REVIEW = 0.60                             # [REVIEW, MATCH) -> review; < REVIEW -> reject

# --- Section 14B product defaults ---
RETENTION_DAYS = 180                           # DPDP document retention
PRICE_ROUND = 10                               # midpoint pricing rounded to nearest Rs 10

# OCR character-confusion map for checksum-based correction (section O4)
OCR_CONFUSIONS = {"O": "0", "I": "1", "S": "5", "Z": "2", "B": "8",
                  "0": "O", "1": "I", "5": "S", "2": "Z", "8": "B"}


# Segment codes used by the engine <-> the full labels used in smb_leads.csv
SEGMENT_CODE = {"Micro retail & services": "micro", "Professional offices": "prof",
                "Small multi-site businesses": "multi", "Small manufacturers": "mfg"}
SEGMENT_LABEL = {v: k for k, v in SEGMENT_CODE.items()}

# Postgres (orders + consent receipts)
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/udyam")
