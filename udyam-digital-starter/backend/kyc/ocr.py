"""OCR with preprocessing + per-field confidence (section O4).

preprocess: grayscale, 2x upscale, Otsu threshold, deskew — this is what lets
the stylised specimens read (plain Tesseract returns near-empty on some, e.g.
K02/K04). Degrades gracefully if cv2 is unavailable.
"""
import re

try:
    import cv2
    import numpy as np
    _HAVE_CV2 = True
except Exception:
    _HAVE_CV2 = False

try:
    import pytesseract
    from PIL import Image
    _HAVE_OCR = True
except Exception:
    _HAVE_OCR = False


def preprocess(path: str):
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(path)
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # deskew
    coords = np.column_stack(np.where(img < 255))
    if len(coords) > 100:
        angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        (h, w) = img.shape
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        img = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REPLICATE)
    return img


def ocr_text_and_confidence(path: str) -> tuple[str, float]:
    """Returns (full_text, mean_word_confidence 0-100)."""
    if not _HAVE_OCR:
        return "", 0.0
    try:
        src = preprocess(path) if _HAVE_CV2 else Image.open(path)
    except Exception:
        src = Image.open(path)
    data = pytesseract.image_to_data(src, output_type=pytesseract.Output.DICT)
    words, confs = [], []
    for w, c in zip(data["text"], data["conf"]):
        if w.strip():
            words.append(w)
            try:
                cv = float(c)
                if cv >= 0:
                    confs.append(cv)
            except ValueError:
                pass
    text = " ".join(words)
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    return text, mean_conf


# --- field extractors (label-based; tolerant of OCR line breaks) ---
def extract_fields(text: str) -> dict:
    t = re.sub(r"\s+", " ", text)
    def grab(pattern):
        m = re.search(pattern, t, re.IGNORECASE)
        return m.group(1).strip() if m else None
    return {
        "gstin": grab(r"GSTIN\s+([0-9A-Z]{10,18})"),
        "legal_name": grab(r"Legal name\s+(.+?)(?: Trade name| Constitution| GSTIN|$)"),
        "trade_name": grab(r"Trade name\s+(.+?)(?: Constitution| Address|$)"),
        "udyam": grab(r"(UDYAM-[A-Z0-9-]{10,20})"),
        "enterprise_name": grab(r"Enterprise name\s+(.+?)(?: Type| Major|$)"),
        "name": grab(r"Name\s+(.+?)(?: Designation| ID| For business|$)"),
        "for_business": grab(r"For business\s+(.+?)(?: ID| Valid| Designation|$)"),
        "date": grab(r"(\d{4}-\d{2}-\d{2})"),
        "state": grab(r"([A-Z][a-z]+ Pradesh|Kerala|Punjab|Tamil Nadu|Karnataka|"
                      r"Maharashtra|Gujarat|Rajasthan|Delhi|Telangana|West Bengal)"),
    }
