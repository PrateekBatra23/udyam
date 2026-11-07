"""GSTIN and Udyam validators (spec sections 6 + Notes on identifiers).

- GSTIN: 15 chars, real structure + checksum. Accept any 4th-PAN char incl. 'X'.
- Udyam: UDYAM-XX-00-NNNNNNN; accept district code '00'.
- OCR correction: if an OCR'd GSTIN fails the checksum, try common character
  confusions (O<->0, I<->1, ...) to repair it (section O4).
"""
import re
import config

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum_ok(g: str) -> bool:
    if not g or len(g) != 15:
        return False
    try:
        s = 0
        for i, ch in enumerate(g[:14]):
            v = _ALPHABET.index(ch)
            p = v * (2 if i % 2 else 1)
            s += p // 36 + p % 36
        chk = _ALPHABET[(36 - (s % 36)) % 36]
        return chk == g[14]
    except ValueError:
        return False


GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")


def gstin_format_ok(g: str) -> bool:
    """Structural check. Note: the synthetic data uses 'X' as the 4th PAN char,
    which this pattern allows (it does not constrain entity type)."""
    return bool(g) and len(g) == 15 and bool(GSTIN_RE.match(g))


def correct_gstin_ocr(raw: str, known: set | None = None) -> tuple[str | None, bool]:
    """Try to repair an OCR'd GSTIN. Generates candidates by applying common
    character confusions at up to two positions, keeps those that pass the
    checksum, and — crucially — prefers a candidate that EXISTS in `known` (the
    registry) over a merely checksum-valid one. Returns (value, was_corrected).

    `known` should be the set of registry GSTINs; without it the function can
    only guarantee checksum validity, not the right business."""
    if not raw:
        return None, False
    raw = raw.strip().upper()
    if gstin_checksum_ok(raw) and (known is None or raw in known):
        return raw, False

    chars = list(raw[:15].ljust(15))
    conf_positions = [i for i, ch in enumerate(chars) if ch in config.OCR_CONFUSIONS]
    candidates = []

    # single-position substitutions
    for i in conf_positions:
        cand = chars.copy()
        cand[i] = config.OCR_CONFUSIONS[chars[i]]
        candidates.append("".join(cand))
    # two-position substitutions (bounded; 15 chars so cheap)
    for a in conf_positions:
        for b in conf_positions:
            if b <= a:
                continue
            cand = chars.copy()
            cand[a] = config.OCR_CONFUSIONS[chars[a]]
            cand[b] = config.OCR_CONFUSIONS[chars[b]]
            candidates.append("".join(cand))

    valid = [c for c in candidates if gstin_checksum_ok(c)]
    if known is not None:
        for c in valid:
            if c in known:
                return c, True            # best: real registry match
    if gstin_checksum_ok(raw):
        return raw, False                 # original was already valid (no registry hit)
    return (valid[0], True) if valid else (raw, False)


UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")


def udyam_format_ok(u: str) -> bool:
    """Accepts district code '00' (the synthetic data always uses it)."""
    return bool(u) and bool(UDYAM_RE.match(u.strip().upper()))
