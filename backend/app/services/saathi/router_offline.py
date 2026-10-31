"""Tool mode — Vitt Saathi without an LLM (RD §26 "Gemini/LLM unavailable").

A deterministic intent router (English + Hinglish keywords) that calls the
same tools as the Gemini path and composes answers only from tool outputs.
It never produces free-form financial claims. The UI labels this mode.
"""

import re

from app.services.statements.categorizer import categorize

# --- slot parsing -----------------------------------------------------------

_AMT_UNITS = [
    (r"(\d+(?:\.\d+)?)\s*(?:crore|crores|cr\b|करोड़|करोड)", 10_000_000),
    (r"(\d+(?:\.\d+)?)\s*(?:lakh\b|lakhs\b|lac\b|lacs\b|l\b|लाख)", 100_000),
    (r"(\d+(?:\.\d+)?)\s*(?:k\b|thousand\b|hazaar\b|hazar\b|hajar\b|हज़ार|हजार)", 1_000),
]


def parse_amount(text: str) -> float | None:
    t = text.lower().replace("₹", " ₹ ")
    for pat, mult in _AMT_UNITS:
        m = re.search(pat, t)
        if m:
            return float(m.group(1)) * mult
    m = re.search(r"(?:₹|rs\.?|inr|रु\.?)\s*([\d,]+(?:\.\d+)?)", t)
    if m:
        return float(m.group(1).replace(",", ""))
    for m in re.finditer(r"\b(\d{1,3}(?:,\d{2,3})+|\d{4,9})(?:\.\d+)?\b", t):
        v = float(m.group(1).replace(",", ""))
        after = t[m.end(): m.end() + 8]
        if re.match(r"\s*(months?|mahine|years?|saal|days?|%)", after) or 1900 <= v <= 2100:
            continue
        return v
    return None


def parse_tenure(text: str) -> int | None:
    t = text.lower()
    m = re.search(r"(\d{1,2}(?:\.\d)?)\s*(?:years?\b|yrs?\b|saal\b|sal\b|varsh\b|साल|वर्ष)", t)
    if m:
        return int(round(float(m.group(1)) * 12))
    m = re.search(r"(\d{1,3})\s*(?:months?\b|mahine\b|mahina\b|mo\b|महीने|महीना)", t)
    if m:
        return int(m.group(1))
    return None


def parse_days(text: str) -> int | None:
    m = re.search(r"(\d{1,3})\s*(?:days?\b|din\b|दिन)", text.lower())
    return int(m.group(1)) if m else None


def parse_rate(text: str) -> float | None:
    m = re.search(r"(\d{1,2}(?:\.\d{1,2})?)\s*%", text)
    return float(m.group(1)) if m else None


PURPOSE_WORDS = [
    ("home_renovation", r"renovat|repair|interior|makeover|मरम्मत"),
    ("home", r"\bhome loan|\bhouse\b|\bflat\b|\bghar\b|apartment|property (?:buy|purchase)|buy (?:a )?(?:home|house)|घर|मकान|फ़्लैट|फ्लैट"),
    ("vehicle", r"\bcar\b|\bbike\b|scooter|vehicle|gaadi|gadi|two[- ]wheeler|गाड़ी|गाडी|कार|बाइक|स्कूटर"),
    ("education", r"educat|college|course|padhai|study|studies|mba|masters|university|fees|पढ़ाई|पढाई|शिक्षा|कॉलेज"),
    ("medical", r"medical|hospital|surgery|treatment|ilaaj|operation|इलाज|अस्पताल|मेडिकल|ऑपरेशन"),
    ("wedding", r"wedding|shaadi|shadi|marriage|vivah|शादी|विवाह"),
    ("travel", r"travel|trip|vacation|holiday|ghoomne|यात्रा|घूमने"),
    ("debt_consolidation", r"consolidat|credit card (?:debt|dues)|pay off|close (?:my )?loans"),
    ("personal", r"personal|urgent|emergency fund|kuch kaam|पर्सनल|निजी"),
]


def parse_purpose(text: str) -> str | None:
    t = text.lower()
    for key, pat in PURPOSE_WORDS:
        if re.search(pat, t):
            return key
    return None


def parse_collateral(text: str) -> str | None:
    t = text.lower()
    if re.search(r"no collateral|without collateral|girvi nahi|kuch (?:bhi )?girvi nahi|nothing to pledge|unsecured|kuch nahi rakh|गिरवी नहीं|कुछ (?:भी )?गिरवी नहीं", t):
        return "none"
    if re.search(r"\bgold\b|\bsona\b|jewell?ery|gehne|सोना|गहने", t):
        return "gold"
    if re.search(r"(?:property|ghar|house|flat|plot|zameen).{0,20}(?:girvi|pledge|mortgage|collateral)|(?:girvi|pledge|mortgage|collateral).{0,20}(?:property|ghar|house|flat|plot)", t):
        return "property"
    if re.search(r"\bfd\b|fixed deposit", t):
        return "fixed_deposit"
    return None


RELATIONS = [
    ("mother", r"\bmother\b|\bmom\b|\bmaa\b|\bmummy\b|\bmaata\b|\bamma\b|माँ|मां|माता|मम्मी"),
    ("father", r"\bfather\b|\bdad\b|\bpapa\b|\bpita\b|\bappa\b|पिता|पापा"),
    ("spouse", r"\bwife\b|\bhusband\b|\bspouse\b|\bpatni\b|\bpati\b|\bbiwi\b|पत्नी|पति|बीवी"),
    ("child", r"\bson\b|\bdaughter\b|\bbeta\b|\bbeti\b|\bchild\b|\bkid\b|\bbachcha\b|\bbacche\b|बेटा|बेटी|बच्चा|बच्चे"),
    ("self", r"\bme\b|\bmyself\b|\bmujhe\b|\bmera\b|\bmain\b|\bi am\b|\bi'm\b|\bmeri\b|मुझे|मेरा|मेरी|मैं"),
]


def parse_relation(text: str) -> str | None:
    t = text.lower()
    for rel, pat in RELATIONS:
        if re.search(pat, t):
            return rel
    return None


CARD_CATS = [
    ("travel", r"flight|air ?ticket|airline|hotel|train|irctc|travel|trip|booking|makemytrip|goibibo|cleartrip|फ़्लाइट|फ्लाइट|उड़ान|होटल|ट्रेन|टिकट"),
    ("food_delivery", r"swiggy|zomato|food|order(?:ing)? (?:food|dinner|lunch)|khana|स्विगी|ज़ोमैटो|जोमैटो|खाना"),
    ("groceries", r"grocer|blinkit|zepto|bigbasket|instamart|dmart|sabzi|ration|किराना|राशन|सब्ज़ी"),
    ("ecommerce", r"amazon|flipkart|myntra|ajio|online shopping|shopping|phone|laptop|tv\b|electronics|ऑनलाइन शॉपिंग|शॉपिंग|अमेज़न|फ़्लिपकार्ट|फ्लिपकार्ट"),
    ("fuel", r"fuel|petrol|diesel|pump|पेट्रोल|डीज़ल|डीजल"),
    ("utilities", r"electricity|bill|recharge|broadband|gas bill|water bill|बिजली|बिल|रिचार्ज"),
    ("entertainment", r"movie|bookmyshow|pvr|concert"),
    ("rent", r"\brent\b|kiraya"),
    ("insurance", r"premium|insurance"),
]


def parse_card_category(text: str) -> tuple[str | None, str | None]:
    t = text.lower()
    for cat, pat in CARD_CATS:
        m = re.search(pat, t)
        if m:
            merchant = None
            cat2, name, _ = categorize(text, "debit")
            if name:
                merchant = name
            return cat, merchant
    return None, None


# --- intent detection -------------------------------------------------------

INTENTS = [
    ("emergency", r"emergency|hospital|admit|bharti|accident|\bclaim\b|ilaaj|icu|surgery|cashless|अस्पताल|भर्ती|इमरजेंसी|आपातकाल|दुर्घटना|एक्सीडेंट|क्लेम|इलाज|कैशलेस"),
    ("consult", r"\bcall\b|consult|advisor|adviser|expert|baat kar|talk to (?:someone|a person|human)|कॉल|सलाहकार|बात करनी|बात करना"),
    ("cards_list", r"reward (?:balance|balances|points)|points balance|my cards|list (?:my )?cards|मेरे कार्ड|रिवॉर्ड (?:बैलेंस|पॉइंट्स)"),
    ("card_best", r"which card|kaunsa card|kaun sa card|best card|card (?:se|use)|konsa card|use for .*(?:flight|purchase|shopping)|कौन सा कार्ड|कौनसा कार्ड|कार्ड"),
    ("reminder", r"remind|yaad dila|reminder|notify|whatsapp|याद दिला|रिमाइंडर"),
    ("loan_cost", r"real cost|total cost|kitna padega|kitna lagega|asli (?:cost|kharcha)|all[- ]in|hidden charge|charges kya|fees kya|असली लागत|कुल लागत|कितना पड़ेगा|कितना लगेगा|असली ख़र्च|असली खर्च"),
    ("compare", r"compare|comparison|tulna|\bvs\b|versus|difference between|तुलना"),
    ("missed", r"miss|chook|chhoot|skip|nahi bhar|nahi de pa|bounce|late|der se|delay|छूट|चूक|देर|लेट|नहीं भर"),
    ("prepay", r"prepay|pre-pay|part[- ]?pay|jaldi chuka|pehle chuka|foreclos|close (?:the )?loan early|प्रीपे|पहले चुका|जल्दी चुका"),
    ("rate_change", r"rate (?:badh|increase|goes up|rise|hike|change)|interest (?:badh|increase|rise)|repo|ब्याज दर बढ़|रेट बढ़"),
    ("tenure", r"tenure|longer|shorter|zyada time|kam time|अवधि"),
    ("insurance_find", r"(?:health|term|life|travel|parents?'?|family) (?:insurance|cover|plan|policy)|insurance (?:chahiye|lena|suggest|recommend)|mediclaim|which (?:insurance|policy) should|बीमा चाहिए|हेल्थ इंश्योरेंस|टर्म इंश्योरेंस|स्वास्थ्य बीमा"),
    ("doc_question", r"exclu|waiting|covered|cover\b|room rent|co-?pay|maternity|documents? (?:needed|required|chahiye)|kaunse documents|clause|penal|foreclosure charge|prepayment charge|sub-?limit|deductible|pre-?existing|tpa|helpline|कवर|शामिल नहीं|प्रतीक्षा|वेटिंग|दस्तावेज़|दस्तावेज|कागज़|मैटरनिटी|हेल्पलाइन"),
    ("emis", r"\bemis?\b|kisht|instal|due date|upcoming|kab due|ईएमआई|किस्त|क़िस्त|EMI"),
    ("loan_search", r"\bloan\b|karz|karza|udhaar|udhar|borrow|finance (?:a|my)|\brin\b|लोन|ऋण|कर्ज़|कर्ज|उधार"),
    ("profile", r"income|salary|spend|kharcha|surplus|bachat|saving|where (?:does )?my money|profile|आय|सैलरी|तनख़्वाह|खर्च|ख़र्च|बचत"),
]


def detect_intent(text: str) -> str | None:
    t = text.lower()
    for name, pat in INTENTS:
        if re.search(pat, t):
            return name
    return None


EVENT_WORDS = [("death", r"death|passed away|died|expired|maut|मृत्यु|निधन"), ("accident", r"accident|injur|chot|दुर्घटना|एक्सीडेंट|चोट"),
               ("travel_medical", r"abroad|overseas|trip|travel|विदेश|यात्रा"), ("day_care", r"day ?care|cataract|dialysis|chemo|डे केयर|मोतियाबिंद|डायलिसिस")]


def parse_event(text: str) -> str:
    t = text.lower()
    for key, pat in EVENT_WORDS:
        if re.search(pat, t):
            return key
    return "hospitalisation"


def insurance_type(text: str) -> str | None:
    t = text.lower()
    if re.search(r"term|life cover|jeevan|टर्म|जीवन बीमा", t):
        return "term_life"
    if re.search(r"endowment|money[- ]?back|savings plan|lic", t):
        return "traditional_life"
    if re.search(r"travel", t):
        return "travel"
    if re.search(r"health|medical|mediclaim|hospital|parents?|senior|हेल्थ|स्वास्थ्य|मेडिकल|माता-पिता", t):
        return "health"
    return None


SUGGESTIONS = {
    "dashboard": ["I need a loan of 5 lakh for a car", "Which card should I use for a ₹30,000 flight?", "Show my upcoming EMIs",
                  "Mother is in hospital — which policy applies?"],
    "loan": ["Personal loan of 3 lakh for 3 years", "What's the real cost?", "Compare the top two", "What if I prepay ₹50,000 after a year?"],
    "card": ["Which card for a ₹30,000 flight?", "What is credit utilisation?", "What does minimum amount due mean?", "Show my reward balances"],
    "emi": ["What if I miss my next EMI?", "What if I prepay ₹1 lakh?", "Remind me before due dates"],
    "insurance": ["What's excluded in my policy?", "What is a waiting period?", "Family floater vs individual cover", "What documents do I need for a claim?"],
    "emergency": ["Which policy covers this?", "What documents do I need?", "Is there a waiting period?", "Call a consultant"],
    "document": ["Summarise this document", "What is the total?", "Is there a waiting period?", "Which page mentions the fees?"],
}
