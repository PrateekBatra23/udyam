"""OCR with preprocessing, layout-aware field extraction and per-field
confidence (spec section O4).

Findings that shaped this module (measured on the 47 specimens):
  * The specimens are two-column "label | value" layouts (or stacked
    label-over-value on the ID card), some rotated a few degrees, some blurred.
    Single-line label regexes therefore capture the *next label* instead of the
    value, so extraction works on word boxes grouped into rows.
  * Hard binarisation (Otsu) + rotation *hurts* GSTIN reads (it injects extra
    characters and blanks some documents). Preprocessing is therefore tried in
    order of aggressiveness and stops as soon as the read is confident:
        1. grayscale + deskew + 2x upscale
        2. 1. + unsharp mask (rescues the blurred specimen)
        3. 1. + Otsu threshold (the classic pipeline, last resort)
    GSTIN candidates are pooled from every variant that was run.
"""
import re
from difflib import SequenceMatcher

try:
    import cv2
    import numpy as np
    _HAVE_CV2 = True
except Exception:  # pragma: no cover
    _HAVE_CV2 = False

try:
    import pytesseract
    from PIL import Image
    _HAVE_OCR = True
except Exception:  # pragma: no cover
    _HAVE_OCR = False

CONFIDENT = 85.0          # stop trying more variants above this mean confidence

# ---------------------------------------------------------------- preprocess
def estimate_skew(gray) -> float:
    """Skew in degrees via projection-profile search on the dark-pixel mask."""
    h, w = gray.shape[:2]
    s = 700.0 / max(w, 1)
    small = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    mask = ((small < 110) * 255).astype("uint8")
    if int((mask > 0).sum()) < 300:
        return 0.0
    hh, ww = mask.shape

    def score(a):
        M = cv2.getRotationMatrix2D((ww / 2, hh / 2), a, 1)
        r = cv2.warpAffine(mask, M, (ww, hh), flags=cv2.INTER_NEAREST)
        prof = (r > 0).sum(axis=1).astype("float64")
        return float(np.sum(np.diff(prof) ** 2))

    coarse = max(np.arange(-12, 12.1, 1.0), key=score)
    fine = max(np.arange(coarse - 1, coarse + 1.01, 0.25), key=score)
    return float(fine)


def _rotate(img, angle):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=255)


def variants(path: str):
    """Lazy generator of (name, image) preprocessing variants."""
    gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(path)
    ang = estimate_skew(gray)
    if abs(ang) >= 0.75:
        gray = _rotate(gray, ang)
    up = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    yield "gray2x", up
    blur = cv2.GaussianBlur(up, (0, 0), 3)
    yield "sharpen", cv2.addWeighted(up, 2.2, blur, -1.2, 0)
    _, thr = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield "otsu", thr


# -------------------------------------------------------------------- words
def _words(img):
    d = pytesseract.image_to_data(img, config="--psm 6",
                                  output_type=pytesseract.Output.DICT)
    out = []
    for i, t in enumerate(d["text"]):
        t = t.strip()
        if not t:
            continue
        try:
            c = float(d["conf"][i])
        except ValueError:
            c = -1.0
        if c < 0:
            continue
        out.append({"t": t, "x": d["left"][i], "y": d["top"][i], "w": d["width"][i],
                    "h": d["height"][i], "c": c})
    return out


def _rows(words):
    """Group words into visual rows by y-centre."""
    if not words:
        return []
    hs = sorted(w["h"] for w in words)
    tol = max(6, 0.55 * hs[len(hs) // 2])
    rows = []
    for w in sorted(words, key=lambda w: w["y"] + w["h"] / 2):
        yc = w["y"] + w["h"] / 2
        if rows and abs(rows[-1]["yc"] - yc) <= tol:
            r = rows[-1]
            r["words"].append(w)
            r["yc"] = sum(x["y"] + x["h"] / 2 for x in r["words"]) / len(r["words"])
        else:
            rows.append({"yc": yc, "words": [w]})
    for r in rows:
        r["words"].sort(key=lambda w: w["x"])
    return rows


# ------------------------------------------------------------------- schema
# label (as words) -> field key. A key of None marks a continuation label
# ("place of business" is the 2nd line of the address label).
SCHEMAS = {
    "gst_certificate": [
        ("gstin", "gstin"), ("legal name", "legal_name"), ("trade name", "trade_name"),
        ("constitution", "constitution"), ("address of principal", "address"),
        ("place of business", None), ("date of liability", "date"),
        ("type of registration", "registration_type")],
    "udyam_certificate": [
        ("udyam reg. number", "udyam"), ("enterprise name", "enterprise_name"),
        ("major activity", "major_activity"), ("city", "city"), ("state", "state"),
        ("date of registration", "date")],
    "signatory_id": [
        ("name", "name"), ("designation", "designation"),
        ("for business", "for_business"), ("id no.", "id_no"),
        ("valid till", "valid_till")],
    "address_proof": [
        ("consumer no.", "consumer_no"), ("billed to", "billed_to"),
        ("supply address", "address"), ("bill date", "date"),
        ("units consumed", "units"), ("amount due (inr)", "amount")],
}
NOISE_PREFIXES = ("synthetic", "specimen", "accel", "fictional", "format", "not a valid")


def _fz(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(".:"), b.lower().strip(".:")).ratio()


def _match_label(row_words, labels):
    """Return (key|None, n_words, matched?) for the longest label prefixing the row."""
    best = None
    for text, key in labels:
        toks = text.split()
        if len(row_words) < len(toks):
            continue
        sc = [_fz(row_words[i]["t"], toks[i]) for i in range(len(toks))]
        if min(sc) >= 0.72 and (len(toks) > 1 or sc[0] >= 0.8):
            cand = (len(toks), sum(sc) / len(sc), key)
            if best is None or cand[:2] > best[:2]:
                best = cand
    return (best[2], best[0], True) if best else (None, 0, False)


def parse_fields(words, doc_type):
    """{field: {"value", "conf"}} from word boxes using the doc's label schema."""
    labels = SCHEMAS.get(doc_type, [])
    fields, cur = {}, None
    for row in _rows(words):
        ws = row["words"]
        line = " ".join(w["t"] for w in ws).lower()
        if line.startswith(NOISE_PREFIXES):
            cur = None if line.startswith(("accel", "synthetic")) else cur
            continue
        key, n, hit = _match_label(ws, labels)
        if hit:
            rest = ws[n:]
            if key is not None:
                cur = key
                fields.setdefault(cur, {"words": []})
            elif cur is None:
                continue
        else:
            rest = ws
            if cur is None:
                continue
        fields[cur]["words"].extend(w for w in rest if w["c"] >= 15)
    out = {}
    for k, v in fields.items():
        ws = v["words"]
        if not ws:
            continue
        out[k] = {"value": " ".join(w["t"] for w in ws).strip(),
                  "conf": round(sum(w["c"] for w in ws) / len(ws), 1)}
    return out


# ------------------------------------------------------- identifier tokens
GSTIN_TOKEN = re.compile(r"[0-9A-Z]{13,17}")
_DATE = re.compile(r"(\d{4})\s*-\s*(\d{2})\s*-\s*(\d{2})")


def normalise_udyam(text: str):
    m = re.search(r"([A-Z]{2})\s*-\s*(\d{2})\s*-\s*(\d{7})", (text or "").upper())
    return f"UDYAM-{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def normalise_date(text: str):
    m = _DATE.search(text or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


_CACHE: dict = {}


def read_document(path: str, doc_type: str) -> dict:
    """OCR one document image -> {fields, confidence, gstin_candidates, variant}.
    Results are cached per (path, mtime, doc_type)."""
    import os
    try:
        key = (os.path.abspath(path), os.path.getmtime(path), doc_type)
    except OSError:
        key = None
    if key in _CACHE:
        return _CACHE[key]
    result = _read_document(path, doc_type)
    if key:
        _CACHE[key] = result
    return result


def _read_document(path: str, doc_type: str) -> dict:
    if not (_HAVE_OCR and _HAVE_CV2):
        return {"fields": {}, "confidence": 0.0, "gstin_candidates": [], "variant": None}
    best, cands = None, []
    for name, img in variants(path):
        words = _words(img)
        confs = [w["c"] for w in words]
        conf = sum(confs) / len(confs) if confs else 0.0
        fields = parse_fields(words, doc_type)
        text = " ".join(w["t"] for w in words)
        toks = GSTIN_TOKEN.findall(text.upper())
        if "gstin" in fields:
            cands.append(re.sub(r"[^0-9A-Z]", "", fields["gstin"]["value"].upper()))
        cands.extend(toks)
        cur = {"fields": fields, "confidence": round(conf, 1), "variant": name}
        if best is None or conf > best["confidence"]:
            best = cur
        needed = {"gst_certificate": "gstin", "udyam_certificate": "udyam",
                  "signatory_id": "for_business", "address_proof": "date"}.get(doc_type)
        if conf >= CONFIDENT and needed in fields:
            if doc_type != "gst_certificate" or _plausible_gstin(fields["gstin"]["value"]):
                break
    best["gstin_candidates"] = list(dict.fromkeys(c for c in cands if 13 <= len(c) <= 17))
    return best


def _plausible_gstin(v: str) -> bool:
    from rules.identifiers import gstin_checksum_ok
    return gstin_checksum_ok(re.sub(r"[^0-9A-Z]", "", v.upper()))


# --------------------------------------------- backwards-compatible helpers
def ocr_text_and_confidence(path: str):
    """Plain text + mean confidence (best variant). Kept for ad-hoc inspection."""
    if not (_HAVE_OCR and _HAVE_CV2):
        return "", 0.0
    name, img = next(variants(path))
    words = _words(img)
    confs = [w["c"] for w in words]
    return " ".join(w["t"] for w in words), (sum(confs) / len(confs) if confs else 0.0)
