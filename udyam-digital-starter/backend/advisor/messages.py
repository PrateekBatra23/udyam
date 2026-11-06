"""Plain-language copy for the advisor (English + Hindi). Other languages are
produced by the LLM path when a key is configured; the rules-only path falls back
to English for them. Product names stay in English (they are brand names)."""

WHY = {
    "en": {
        "P01": "Fast, reliable fibre internet for billing, UPI and video calls.",
        "P02": "Faster fibre (300 Mbps) so your whole team and customers stay online.",
        "P03": "Gigabit fibre with priority support for heavy, always-on use.",
        "P04": "Plug-and-play 5G internet - live in about 2 days, no cable needed.",
        "P05": "A dedicated line with a 99.5% uptime promise for work that cannot stop.",
        "P06": "A dedicated 100 Mbps line with a 99.9% uptime promise.",
        "P07": "A business mobile line with unlimited calls and 50 GB data.",
        "P08": "Premium business line: 150 GB, roaming and priority care.",
        "P09": "A backup 4G/5G link that switches on by itself if the main line drops.",
        "P10": "One dashboard to manage the internet at every site.",
        "P11": "A fixed public IP so you can watch CCTV or reach systems remotely.",
        "P12": "Business phone lines with IVR and call recording - one number for customers.",
        "P13": "A free-to-call 1800 number that customers trust.",
        "P14": "10,000 SMS a month for offers, reminders and alerts.",
        "P15": "Reach customers on WhatsApp with your catalogue and quick replies.",
        "P16": "Business email on your own name, plus documents and meetings.",
        "P17": "Automatic backup of your PCs and phones - nothing gets lost.",
        "P18": "A simple website and domain so customers can find you online.",
        "P19": "GST-ready billing and UPI/card payments on a tablet.",
        "P20": "Antivirus and ransomware protection for your computers and phones.",
        "P21": "A managed firewall watched by Accel's security team.",
        "P22": "Secure Wi-Fi with a separate guest network for customers.",
        "P23": "HD cloud CCTV you can watch on your phone.",
        "P24": "Track machine uptime and power use with IoT sensors.",
        "P25": "Live GPS tracking for your vehicles.",
    },
    "hi": {
        "P01": "बिलिंग, UPI और वीडियो कॉल के लिए तेज़ और भरोसेमंद फाइबर इंटरनेट।",
        "P02": "तेज़ फाइबर (300 Mbps) - पूरी टीम और ग्राहक ऑनलाइन रहें।",
        "P03": "भारी उपयोग के लिए गीगाबिट फाइबर और प्राथमिकता सहायता।",
        "P04": "प्लग-एंड-प्ले 5G इंटरनेट - लगभग 2 दिन में चालू, केबल की ज़रूरत नहीं।",
        "P05": "99.5% अपटाइम के वादे के साथ समर्पित लाइन।",
        "P06": "99.9% अपटाइम के वादे के साथ समर्पित 100 Mbps लाइन।",
        "P07": "असीमित कॉल और 50 GB डेटा वाली बिज़नेस मोबाइल लाइन।",
        "P08": "प्रीमियम बिज़नेस लाइन: 150 GB, रोमिंग और प्राथमिकता सेवा।",
        "P09": "मुख्य लाइन बंद होने पर अपने-आप चालू होने वाला बैकअप 4G/5G लिंक।",
        "P10": "हर साइट का इंटरनेट एक ही डैशबोर्ड से संभालें।",
        "P11": "फिक्स्ड पब्लिक IP - CCTV या सिस्टम दूर से देखें।",
        "P12": "IVR और कॉल रिकॉर्डिंग वाली बिज़नेस फ़ोन लाइनें।",
        "P13": "ग्राहकों का भरोसा बढ़ाने वाला 1800 टोल-फ्री नंबर।",
        "P14": "ऑफ़र, रिमाइंडर और अलर्ट के लिए हर महीने 10,000 SMS।",
        "P15": "WhatsApp पर कैटलॉग और त्वरित जवाबों के साथ ग्राहकों तक पहुँचें।",
        "P16": "अपने नाम से बिज़नेस ईमेल, साथ में डॉक्युमेंट और मीटिंग।",
        "P17": "आपके पीसी और फ़ोन का अपने-आप बैकअप।",
        "P18": "ग्राहक आपको ऑनलाइन खोज सकें - सरल वेबसाइट और डोमेन।",
        "P19": "GST-तैयार बिलिंग और टैबलेट पर UPI/कार्ड भुगतान।",
        "P20": "कंप्यूटर और फ़ोन के लिए एंटीवायरस और रैनसमवेयर सुरक्षा।",
        "P21": "Accel की सुरक्षा टीम द्वारा निगरानी वाला मैनेज्ड फ़ायरवॉल।",
        "P22": "ग्राहकों के लिए अलग गेस्ट नेटवर्क के साथ सुरक्षित वाई-फ़ाई।",
        "P23": "फ़ोन पर देखें - HD क्लाउड CCTV।",
        "P24": "IoT सेंसर से मशीन अपटाइम और बिजली उपयोग पर नज़र।",
        "P25": "आपके वाहनों की लाइव GPS ट्रैकिंग।",
    },
}

SEGMENT_NAME = {
    "en": {"micro": "small shop or service business", "prof": "professional office",
           "multi": "multi-site business", "mfg": "small manufacturer"},
    "hi": {"micro": "छोटी दुकान / सेवा व्यवसाय", "prof": "प्रोफ़ेशनल ऑफ़िस",
           "multi": "मल्टी-साइट व्यवसाय", "mfg": "छोटा निर्माता"},
}

PRIORITY_LINE = {
    "en": {"price": "You said price matters most, so the Lite plan is on top and every item is at its lowest price.",
           "reliability": "You said reliability matters most, so a backup link is included where it is allowed.",
           "customers": "You said reaching customers matters most, so messaging tools are included where allowed.",
           "security": "You said security matters most, so protection add-ons are included where allowed.",
           "safety": "You said safety matters most, so CCTV is included."},
    "hi": {"price": "आपने कहा कि कीमत सबसे ज़रूरी है, इसलिए Lite प्लान ऊपर है और हर चीज़ सबसे कम कीमत पर है।",
           "reliability": "आपने कहा कि भरोसेमंद इंटरनेट सबसे ज़रूरी है, इसलिए जहाँ संभव हो बैकअप लिंक शामिल है।",
           "customers": "आपने कहा कि ग्राहकों तक पहुँचना सबसे ज़रूरी है, इसलिए जहाँ संभव हो मैसेजिंग टूल शामिल हैं।",
           "security": "आपने कहा कि सुरक्षा सबसे ज़रूरी है, इसलिए जहाँ संभव हो सुरक्षा ऐड-ऑन शामिल हैं।",
           "safety": "आपने कहा कि सुरक्षा (निगरानी) ज़रूरी है, इसलिए CCTV शामिल है।"},
}

BLOCKER = {
    "en": {
        "employees": "needs at least {need} employees (you have {have})",
        "sites": "needs at least {need} sites (you have {have})",
        "gstin": "needs an active GSTIN",
        "city_tier": "is not offered in your city yet",
        "dependency": "needs an internet line in the same bundle first ({names})",
        "unknown": "is not in our catalogue",
    },
    "hi": {
        "employees": "के लिए कम से कम {need} कर्मचारी चाहिए (आपके पास {have})",
        "sites": "के लिए कम से कम {need} साइट चाहिए (आपके पास {have})",
        "gstin": "के लिए सक्रिय GSTIN ज़रूरी है",
        "city_tier": "आपके शहर में अभी उपलब्ध नहीं है",
        "dependency": "से पहले उसी बंडल में इंटरनेट कनेक्शन चाहिए ({names})",
        "unknown": "हमारे कैटलॉग में नहीं है",
    },
}


def why(lang: str, pid: str, fallback: str = "") -> str:
    return WHY.get(lang, WHY["en"]).get(pid) or WHY["en"].get(pid) or fallback


def blocker_text(lang: str, b: dict, name_of=lambda pid: pid) -> str:
    tpl = BLOCKER.get(lang, BLOCKER["en"])[b["code"]]
    names = ", ".join(name_of(p) for p in b.get("need", [])) if b["code"] == "dependency" else ""
    return tpl.format(need=b.get("need"), have=b.get("have"), names=names)


def refusal(lang: str, name: str, reasons: list, alternatives: list) -> str:
    if lang == "hi":
        base = f"मैं {name} नहीं जोड़ सकता: " + "; ".join(reasons) + "।"
        return base + (f" इसके बजाय {', '.join(alternatives)} देखें।" if alternatives else "")
    base = f"I can't add {name}: it " + "; and it ".join(reasons) + "."
    return base + (f" Instead, consider {', '.join(alternatives)}." if alternatives else "")


def rationale(lang: str, segment: str, employees: int, sites: int, names: list,
              priority: str | None, churn_pct: float | None) -> str:
    seg = SEGMENT_NAME.get(lang, SEGMENT_NAME["en"])[segment]
    plural = "s" if sites != 1 else ""
    if lang == "hi":
        out = (f"{seg} के लिए, जिसमें लगभग {employees} लोग और {sites} साइट हैं, हमने ये चुने हैं: "
               f"{', '.join(names)}। सब कुछ एक बिल और एक सपोर्ट नंबर पर।")
    else:
        out = (f"For a {seg} with about {employees} people across {sites} site{plural}, "
               f"we picked: {', '.join(names)}. One bill, one support number.")
    if priority in PRIORITY_LINE["en"]:
        out += " " + PRIORITY_LINE.get(lang, PRIORITY_LINE["en"])[priority]
    if churn_pct is not None:
        if lang == "hi":
            out += (f" हमारे डेटा में इस श्रेणी के {churn_pct:.0f}% ग्राहक 6 महीने में छोड़ गए, "
                    f"इसलिए हम ऐसा बंडल चुनते हैं जो रोज़ के काम में बैठ जाए।")
        else:
            out += (f" In our data {churn_pct:.0f}% of customers like you left within 6 months, so we "
                    f"favour a bundle that fits daily work rather than the biggest one.")
    return out


QUESTIONS = {
    "en": {
        "num_sites": "How many locations does your business operate from?",
        "current_spend": "Roughly how much do you spend on phone and internet each month (Rs)?",
        "priority": "What matters most to you right now?",
    },
    "hi": {
        "num_sites": "आपका व्यवसाय कितनी जगहों से चलता है?",
        "current_spend": "फ़ोन और इंटरनेट पर हर महीने लगभग कितना खर्च करते हैं (₹)?",
        "priority": "अभी आपके लिए सबसे ज़रूरी क्या है?",
    },
}
QUESTION_WHY = {
    "en": "Lets us show what you save against today's bills.",
    "hi": "ताकि हम दिखा सकें कि आज के बिलों की तुलना में आप कितना बचाते हैं।",
}
PRIORITY_LABEL = {
    "en": {"price": "Lowest price", "reliability": "Internet that never drops",
           "customers": "Reaching customers", "security": "Security",
           "safety": "Shop / site safety (CCTV)"},
    "hi": {"price": "सबसे कम कीमत", "reliability": "कभी न रुकने वाला इंटरनेट",
           "customers": "ग्राहकों तक पहुँचना", "security": "सुरक्षा",
           "safety": "दुकान / साइट की निगरानी (CCTV)"},
}
