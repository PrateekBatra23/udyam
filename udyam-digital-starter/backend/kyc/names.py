"""Business-name normalisation + fuzzy matching (spec section 14C).

normalise: lowercase, strip punctuation and legal suffixes (LLP / Pvt Ltd /
Prop.), then SequenceMatcher ratio. Thresholds live in config:
  ratio >= NAME_MATCH            -> match
  NAME_REVIEW <= ratio < MATCH   -> review
  ratio < NAME_REVIEW            -> mismatch
"""
import re
from difflib import SequenceMatcher

import config

_SUFFIX = re.compile(r"\b(private limited|pvt\.?\s*ltd\.?|limited|ltd\.?|llp|prop\.?|proprietor)\b")
_PROP = re.compile(r"^(?P<person>.*?)\s*\(\s*prop\.?\s*(?P<biz>.+?)\s*\)?\s*$", re.IGNORECASE)


def normalise(s: str) -> str:
    s = (s or "").lower()
    s = _SUFFIX.sub(" ", s)
    s = re.sub(r"[^a-z0-9& ]", " ", s)
    return " ".join(s.split())


def ratio(a: str, b: str) -> float:
    a, b = normalise(a), normalise(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def split_proprietor(legal_name: str) -> tuple[str | None, str]:
    """'Neha Kaur (Prop. Vindhya Tours & Travels)' -> ('Neha Kaur', 'Vindhya ...').
    For non-proprietorships returns (None, legal_name)."""
    m = _PROP.match((legal_name or "").strip())
    if m:
        return m.group("person").strip(), m.group("biz").strip().rstrip(")")
    return None, (legal_name or "").strip()


def verdict(r: float) -> str:
    if r >= config.NAME_MATCH:
        return "match"
    if r >= config.NAME_REVIEW:
        return "review"
    return "mismatch"
