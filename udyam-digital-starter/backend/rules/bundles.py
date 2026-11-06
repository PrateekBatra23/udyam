"""Indicative segment bundles (spec section 9) used as the advisor's defaults
and the rules-only fallback. The eligibility engine filters these per profile,
so a no-GSTIN or small profile automatically drops gated items.

VALUE = the full indicative bundle for the segment.
LITE  = connectivity core + one productivity/communication item (section 14B).
"""

VALUE_BUNDLE = {
    "micro": ["P01", "P07", "P15", "P19", "P23"],
    "prof":  ["P02", "P08", "P16", "P20", "P12"],
    "multi": ["P02", "P09", "P10", "P13", "P23", "P22"],
    "mfg":   ["P05", "P11", "P21", "P24", "P16"],
}

LITE_BUNDLE = {
    "micro": ["P04", "P07"],
    "prof":  ["P01", "P16"],
    "multi": ["P02", "P16"],
    "mfg":   ["P05", "P16"],
}

DEFAULT_QTY = {"P07": 1}  # extend if a product is typically multi-quantity
