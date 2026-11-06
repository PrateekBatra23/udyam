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

# Base internet products a bundle must contain before dependents can be sold.
CONNECTIVITY = ["P01", "P02", "P03", "P04", "P05", "P06"]

# If the segment's preferred line is not sellable (tier / size / GSTIN), swap in
# the first eligible alternative from this list - "swap within the eligible set".
CONNECTIVITY_PREF = {
    "micro": ["P01", "P04", "P02"],
    "prof":  ["P02", "P01", "P04"],
    "multi": ["P02", "P03", "P01"],
    "mfg":   ["P05", "P02", "P01", "P03"],
}

# The owner's single "top priority" answer -> add-ons to include in Value when
# eligible (at most 2 are added per priority).
PRIORITIES = ["price", "reliability", "customers", "security", "safety"]
PRIORITY_ADDONS = {
    "price": [],
    "reliability": ["P09", "P11"],
    "customers": ["P15", "P14", "P13"],
    "security": ["P20", "P22", "P21"],
    "safety": ["P23"],
}

# Plain-language alternatives suggested when a request is refused.
ALTERNATIVES = {
    "P10": ["P09", "P02"], "P05": ["P02", "P01"], "P06": ["P05", "P03", "P02"],
    "P03": ["P02", "P01"], "P21": ["P20", "P22"], "P24": ["P23", "P25"],
    "P12": ["P08", "P07"], "P13": ["P15", "P07"], "P14": ["P15"], "P15": ["P18", "P07"],
}

# Free-text request -> product id (longest phrase wins).
REQUEST_KEYWORDS = [
    ("leased line 100", "P06"), ("leased line", "P05"), ("sd-wan", "P10"), ("sdwan", "P10"),
    ("sd wan", "P10"), ("firewall", "P21"), ("machine monitoring", "P24"), ("iot", "P24"),
    ("failover", "P09"), ("backup internet", "P09"), ("static ip", "P11"),
    ("cloud telephony", "P12"), ("sip", "P12"), ("ivr", "P12"), ("toll free", "P13"),
    ("toll-free", "P13"), ("1800", "P13"), ("cctv", "P23"), ("camera", "P23"),
    ("whatsapp", "P15"), ("sms", "P14"), ("email", "P16"), ("office suite", "P16"),
    ("pos", "P19"), ("billing", "P19"), ("wifi", "P22"), ("wi-fi", "P22"),
    ("1g", "P03"), ("gigabit", "P03"), ("fleet", "P25"), ("gps", "P25"),
    ("cloud backup", "P17"), ("website", "P18"), ("domain", "P18"),
    ("antivirus", "P20"), ("endpoint", "P20"),
]
