// Client-side GSTIN format + checksum so the owner sees a tick/cross instantly,
// with no server round-trip for the obvious-invalid case (spec O1). Mirrors
// backend/rules/identifiers.py. The 4th PAN character is not constrained, so the
// synthetic 'X' is accepted.
const ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$/;

export function gstinChecksumOk(g) {
  if (!g || g.length !== 15) return false;
  let s = 0;
  for (let i = 0; i < 14; i++) {
    const v = ALPHABET.indexOf(g[i]);
    if (v < 0) return false;
    const p = v * (i % 2 ? 2 : 1);
    s += Math.floor(p / 36) + (p % 36);
  }
  return ALPHABET[(36 - (s % 36)) % 36] === g[14];
}

// -> { state: "empty" | "typing" | "bad_format" | "bad_checksum" | "ok", message }
export function checkGstin(raw) {
  const g = (raw || "").trim().toUpperCase();
  if (!g) return { state: "empty", message: "" };
  if (g.length < 15) return { state: "typing", message: `${g.length}/15 characters` };
  if (g.length > 15 || !RE.test(g)) return { state: "bad_format", message: "Format looks wrong (15 characters: 2 digits, 5 letters, 4 digits, letter, letter/digit, Z, letter/digit)" };
  if (!gstinChecksumOk(g)) return { state: "bad_checksum", message: "Checksum doesn't match - please re-check the last characters" };
  return { state: "ok", message: "Valid GSTIN format" };
}
