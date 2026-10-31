"""Deterministic transaction categorisation for Indian bank narrations (RD §9.2).

Rules only — no LLM guessing. Anything ambiguous falls to "other" and can be
corrected by the user (RD §26).
"""

import re

CATEGORIES: dict[str, str] = {
    "salary": "Salary",
    "income_other": "Other income",
    "refund": "Refunds",
    "food_delivery": "Food & delivery",
    "groceries": "Groceries",
    "ecommerce": "Online shopping",
    "travel": "Travel",
    "fuel": "Fuel",
    "utilities": "Bills & utilities",
    "rent": "Rent",
    "education": "Education",
    "healthcare": "Healthcare",
    "entertainment": "Entertainment",
    "subscriptions": "Subscriptions",
    "insurance": "Insurance premiums",
    "emi": "Loan EMIs",
    "card_payment": "Credit card bills",
    "investments": "Investments",
    "cash": "Cash withdrawals",
    "transfers": "Transfers",
    "other": "Other",
}

# Ordered: longer / more specific keywords first. (keyword, merchant display, category)
MERCHANTS: list[tuple[str, str, str]] = [
    ("swiggy instamart", "Swiggy Instamart", "groceries"),
    ("instamart", "Swiggy Instamart", "groceries"),
    ("swiggy", "Swiggy", "food_delivery"),
    ("zomato", "Zomato", "food_delivery"),
    ("eatsure", "EatSure", "food_delivery"),
    ("dominos", "Domino's", "food_delivery"),
    ("blinkit", "Blinkit", "groceries"),
    ("zepto", "Zepto", "groceries"),
    ("bigbasket", "BigBasket", "groceries"),
    ("dmart", "DMart", "groceries"),
    ("amazon pay", "Amazon", "ecommerce"),
    ("amazon", "Amazon", "ecommerce"),
    ("flipkart", "Flipkart", "ecommerce"),
    ("myntra", "Myntra", "ecommerce"),
    ("ajio", "AJIO", "ecommerce"),
    ("meesho", "Meesho", "ecommerce"),
    ("nykaa", "Nykaa", "ecommerce"),
    ("tatacliq", "Tata CLiQ", "ecommerce"),
    ("irctc", "IRCTC", "travel"),
    ("makemytrip", "MakeMyTrip", "travel"),
    ("goibibo", "Goibibo", "travel"),
    ("cleartrip", "Cleartrip", "travel"),
    ("indigo", "IndiGo", "travel"),
    ("air india", "Air India", "travel"),
    ("akasa", "Akasa Air", "travel"),
    ("redbus", "redBus", "travel"),
    ("ixigo", "ixigo", "travel"),
    ("uber", "Uber", "travel"),
    ("ola ", "Ola", "travel"),
    ("olacabs", "Ola", "travel"),
    ("rapido", "Rapido", "travel"),
    ("hpcl", "HPCL", "fuel"),
    ("bpcl", "BPCL", "fuel"),
    ("indian oil", "Indian Oil", "fuel"),
    ("iocl", "Indian Oil", "fuel"),
    ("petrol", "Fuel station", "fuel"),
    ("bescom", "BESCOM", "utilities"),
    ("msedcl", "MSEDCL", "utilities"),
    ("tata power", "Tata Power", "utilities"),
    ("adani electricity", "Adani Electricity", "utilities"),
    ("electricity", "Electricity bill", "utilities"),
    ("mahanagar gas", "Mahanagar Gas", "utilities"),
    ("indane", "Indane Gas", "utilities"),
    ("broadband", "Broadband", "utilities"),
    ("act fibernet", "ACT Fibernet", "utilities"),
    ("jio", "Jio", "utilities"),
    ("airtel", "Airtel", "utilities"),
    ("bsnl", "BSNL", "utilities"),
    ("recharge", "Mobile recharge", "utilities"),
    ("netflix", "Netflix", "subscriptions"),
    ("spotify", "Spotify", "subscriptions"),
    ("hotstar", "JioHotstar", "subscriptions"),
    ("youtube", "YouTube Premium", "subscriptions"),
    ("prime video", "Prime Video", "subscriptions"),
    ("sonyliv", "SonyLIV", "subscriptions"),
    ("zee5", "ZEE5", "subscriptions"),
    ("apple.com", "Apple", "subscriptions"),
    ("google play", "Google Play", "subscriptions"),
    ("bookmyshow", "BookMyShow", "entertainment"),
    ("pvr", "PVR INOX", "entertainment"),
    ("inox", "PVR INOX", "entertainment"),
    ("apollo", "Apollo", "healthcare"),
    ("pharmeasy", "PharmEasy", "healthcare"),
    ("1mg", "Tata 1mg", "healthcare"),
    ("netmeds", "Netmeds", "healthcare"),
    ("medplus", "MedPlus", "healthcare"),
    ("practo", "Practo", "healthcare"),
    ("hospital", "Hospital", "healthcare"),
    ("clinic", "Clinic", "healthcare"),
    ("byju", "BYJU'S", "education"),
    ("unacademy", "Unacademy", "education"),
    ("coursera", "Coursera", "education"),
    ("udemy", "Udemy", "education"),
    ("school", "School fees", "education"),
    ("college", "College fees", "education"),
    ("tuition", "Tuition", "education"),
    ("nobroker", "NoBroker", "rent"),
    ("zerodha", "Zerodha", "investments"),
    ("groww", "Groww", "investments"),
    ("mutual fund", "Mutual fund", "investments"),
    (" sip ", "SIP", "investments"),
    ("lic of india", "LIC", "insurance"),
    ("lic premium", "LIC", "insurance"),
    ("star health", "Star Health", "insurance"),
    ("niva bupa", "Niva Bupa", "insurance"),
    ("care health", "Care Health", "insurance"),
    ("hdfc ergo", "HDFC ERGO", "insurance"),
    ("icici lombard", "ICICI Lombard", "insurance"),
    ("max life", "Max Life", "insurance"),
    ("tata aia", "Tata AIA", "insurance"),
]

_KEYWORDS: list[tuple[re.Pattern, str, str | None]] = [
    # (pattern, category, direction constraint)
    (re.compile(r"\bsal(ary)?\b|\bpayroll\b|salary credit", re.I), "salary", "credit"),
    (re.compile(r"\brefund\b|\breversal\b|\bcashback\b", re.I), "refund", "credit"),
    (re.compile(r"\bint(erest)?\.?\s?(pd|paid|credit)\b|\bsb int\b|interest", re.I), "income_other", "credit"),
    # Specific purposes before the generic mandate (NACH/ECS) → EMI rule
    (re.compile(r"\bpremium\b|\binsurance\b|\bpolicy\b", re.I), "insurance", "debit"),
    (re.compile(r"credit ?card|\bcc ?(payment|pymt|bill)\b|card ?payment|\bcred\b", re.I), "card_payment", "debit"),
    (re.compile(r"\brent\b", re.I), "rent", "debit"),
    (re.compile(r"\bemi\b|\bloan\b|\bnach\b|\bach d\b|\becs\b|finance ltd|finserv", re.I), "emi", "debit"),
    (re.compile(r"\batm\b|cash ?wdl|\bcash withdrawal\b|\bnwd\b", re.I), "cash", "debit"),
]

_CHANNELS = [
    ("UPI", re.compile(r"\bupi\b", re.I)),
    ("NEFT", re.compile(r"\bneft\b", re.I)),
    ("IMPS", re.compile(r"\bimps\b", re.I)),
    ("RTGS", re.compile(r"\brtgs\b", re.I)),
    ("NACH", re.compile(r"\bnach\b|\bach\b|\becs\b", re.I)),
    ("CARD", re.compile(r"\bpos\b|\bcard\b", re.I)),
    ("ATM", re.compile(r"\batm\b|\bnwd\b", re.I)),
]


def detect_channel(desc: str) -> str | None:
    for name, pat in _CHANNELS:
        if pat.search(desc):
            return name
    return None


def counterparty(desc: str) -> str:
    """Normalised counterparty used for recurring grouping: strip refs, digits, VPAs' handles."""
    s = desc.lower()
    # UPI/DR/123456789/NAME/BANK/vpa@handle/note
    parts = re.split(r"[/|]", s)
    if parts and parts[0].strip() in {"upi", "neft", "imps", "rtgs"} and len(parts) >= 4:
        candidates = [p for p in parts[1:] if p.strip() and not re.fullmatch(r"[\sdrc\d]+", p.strip())]
        if candidates:
            s = candidates[0]
    s = re.sub(r"\S+@\S+", " ", s)
    s = re.sub(r"\w*\d\w*", " ", s)
    s = re.sub(r"\b(upi|neft|imps|rtgs|nach|ach|ecs|dr|cr|pos|ref|txn|no|p2m|p2a|mb|ib|to|from|by|transfer|trf|bbps)\b", " ", s)
    s = re.sub(_MONTHS, " ", s)
    s = re.sub(r"[^a-z& ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:60] or "unknown"


_MONTHS = re.compile(r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sep(t|tember)?|oct(ober)?|nov(ember)?|dec(ember)?)\b")
_MONTHS_UPPER = re.compile(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)\b")
_BANK_CODES = {"hdfc", "icic", "axis", "sbin", "yesb", "kkbk", "utib", "pytm", "ybl", "okaxis", "oksbi", "okhdfcbank", "okicici", "barb", "punb"}


def display_label(desc: str, merchant: str | None = None) -> str:
    """Human label for a narration: merchant name, UPI payee, or cleaned NEFT/NACH counterparty."""
    if merchant:
        return merchant
    parts = [p.strip() for p in re.split(r"[/|]", desc) if p.strip()]
    if parts and parts[0].upper() in {"UPI", "NEFT", "IMPS", "RTGS"} and len(parts) >= 4:
        for p in parts[1:]:
            low = p.lower()
            if re.fullmatch(r"[\d\s]+|dr|cr", low) or low in _BANK_CODES or "@" in p:
                continue
            return p.title()
    s = re.sub(r"^(NEFT|IMPS|RTGS|NACH|ACH|ECS|BBPS|POS)[-\s/:]*(DR|CR)?[-\s/:]*", "", desc.strip(), flags=re.I)
    s = re.sub(r"\b\w*\d\w*\b", "", s)
    s = re.sub(r"[-_/]+", " ", s)
    s = re.sub(r"\b(XX\w*)\b", "", s)
    s = re.sub(_MONTHS_UPPER, "", s)
    s = re.sub(r"\s+", " ", s).strip(" -")
    if s.isupper():
        s = s.title()
        for a in ("Emi", "Cc", "Sip", "Upi", "Neft", "Lic"):
            s = re.sub(rf"\b{a}\b", a.upper(), s)
    return s[:60] or desc[:60]


def categorize(desc: str, direction: str) -> tuple[str, str | None, float]:
    """Returns (category, merchant display name or None, confidence)."""
    padded = f" {desc.lower()} "
    for pat, cat, dir_constraint in _KEYWORDS[:3]:
        if (dir_constraint is None or dir_constraint == direction) and pat.search(desc):
            return cat, None, 0.8
    for kw, name, cat in MERCHANTS:
        if kw in padded:
            if direction == "credit":
                return "refund", name, 0.7
            return cat, name, 0.9
    for pat, cat, dir_constraint in _KEYWORDS[3:]:
        if (dir_constraint is None or dir_constraint == direction) and pat.search(desc):
            return cat, None, 0.75
    channel = detect_channel(desc)
    if channel in {"UPI", "NEFT", "IMPS", "RTGS"}:
        return ("transfers", None, 0.6) if direction == "debit" else ("income_other", None, 0.5)
    return ("other", None, 0.4) if direction == "debit" else ("income_other", None, 0.4)
