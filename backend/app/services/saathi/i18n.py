"""Language handling for Vitt Saathi Tool mode: English, Hindi (Devanagari) and Hinglish (Roman script).

Language only changes wording. Numbers are always taken from deterministic tool output and formatted
with the same Indian grouping, and it never changes which tools a page may use (RD §11.1).
"""

import re

LANGS = ("en", "hi", "hinglish")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_HINGLISH = re.compile(
    r"\b(hai|hain|kya|kaise|kitna|kitni|kitne|mujhe|mera|meri|mere|chahiye|karna|karni|lena|leni|nahi|nahin|"
    r"batao|bataiye|bata|kab|kaun|konsa|kaunsa|agar|toh|aur|liye|wala|wali|sakta|sakti|hoga|hogi|padega|"
    r"maa|mummy|papa|bharti|girvi|kisht|paisa|paise|sab|kuch|abhi|jaldi|chook|gaya|gayi|karo|kijiye)\b",
    re.I,
)


def normalize(text: str) -> str:
    return text.translate(_DIGITS)


def detect(text: str) -> str | None:
    """Returns 'hi', 'hinglish', 'en', or None when the message is too short/ambiguous (e.g. '3 lakh')."""
    dev = len(_DEVANAGARI.findall(text))
    lat = len(_LATIN.findall(text))
    if dev and dev >= lat * 0.5:
        return "hi"
    markers = len(_HINGLISH.findall(text))
    words = len(re.findall(r"[A-Za-z]+", text))
    if markers >= 2 or (markers == 1 and words <= 4):
        return "hinglish"
    if words >= 3:
        return "en"
    return None


def pick(lang: str, en: str, hi: str, hg: str) -> str:
    return {"hi": hi, "hinglish": hg}.get(lang, en)


# Fixed prompts (asks, help, notices)
TEXT: dict[str, tuple[str, str, str]] = {
    "ask_card": ("How much is the purchase, and what is it for (for example a flight, food delivery or online shopping)?",
                 "ख़रीदारी कितने की है और किस लिए है — जैसे फ़्लाइट, खाना मँगवाना या ऑनलाइन शॉपिंग?",
                 "Purchase kitne ka hai aur kis cheez ke liye — jaise flight, food delivery ya online shopping?"),
    "ask_loan_first": ("Which loan should I work this out for? Tell me the purpose and amount first, for example 'personal loan of ₹3 lakh for 3 years'.",
                       "किस लोन के लिए हिसाब लगाऊँ? पहले मक़सद और रक़म बताइए, जैसे '3 साल के लिए ₹3 लाख का पर्सनल लोन'।",
                       "Kis loan ke liye calculate karun? Pehle purpose aur amount batao, jaise '3 saal ke liye ₹3 lakh ka personal loan'."),
    "ask_compare_two": ("I need at least two loan options to compare. Tell me the purpose and amount so I can find some.",
                        "तुलना के लिए कम से कम दो लोन विकल्प चाहिए। मक़सद और रक़म बताइए, मैं विकल्प ढूँढता हूँ।",
                        "Compare karne ke liye kam se kam do loan options chahiye. Purpose aur amount batao, main options dhoondhta hoon."),
    "ask_prepay": ("How much would you like to prepay, and after how many months? For example, '₹50,000 after 12 months'.",
                   "कितना प्रीपे करना चाहते हैं और कितने महीने बाद? जैसे '12 महीने बाद ₹50,000'।",
                   "Kitna prepay karna hai aur kitne mahine baad? Jaise '12 mahine baad ₹50,000'."),
    "ask_prepay_amount": ("How much would you like to prepay?", "कितना प्रीपे करना चाहते हैं?", "Kitna prepay karna chahte ho?"),
    "ask_rate": ("What new interest rate should I assume? For example, '10.5%'.",
                 "कौन सी नई ब्याज दर मानूँ? जैसे '10.5%'।", "Kaunsi nayi interest rate maanun? Jaise '10.5%'."),
    "ask_tenure": ("What tenure should I compare against? For example, '5 years'.",
                   "किस अवधि से तुलना करूँ? जैसे '5 साल'।", "Kis tenure se compare karun? Jaise '5 saal'."),
    "ask_purpose": ("What is the loan for? For example a home, vehicle, education, medical expenses, a wedding or a personal need.",
                    "लोन किस लिए चाहिए? जैसे घर, गाड़ी, पढ़ाई, इलाज, शादी या कोई निजी ज़रूरत।",
                    "Loan kis liye chahiye? Jaise ghar, gaadi, padhai, ilaaj, shaadi ya koi personal zaroorat."),
    "ask_amount": ("How much do you need? For example ₹3 lakh.", "कितनी रक़म चाहिए? जैसे ₹3 लाख।", "Kitna amount chahiye? Jaise ₹3 lakh."),
    "ask_home_collateral": ("Home loans are secured by the property. Can the property you're buying be mortgaged to the lender (kya girvi rakh sakte hain)?",
                            "होम लोन में घर ही गिरवी रहता है। क्या आप जो घर ले रहे हैं उसे लोन देने वाले के पास गिरवी रख सकते हैं?",
                            "Home loan mein ghar hi girvi rehta hai. Kya aap jo ghar le rahe ho use lender ke paas girvi rakh sakte ho?"),
    "other_screen": ("That's handled on another screen. I've added a link so you can continue there.",
                     "यह काम दूसरी स्क्रीन पर होता है। वहाँ जाने के लिए मैंने लिंक जोड़ दिया है।",
                     "Yeh doosri screen par hota hai. Wahan jaane ke liye link add kar diya hai."),
    "who_for": ("Who is this for? Choose the person so I only look at their policies.",
                "यह किसके लिए है? व्यक्ति चुनिए ताकि मैं सिर्फ़ उन्हीं की पॉलिसी देखूँ।",
                "Yeh kiske liye hai? Person choose karo taaki main sirf unki policies dekhun."),
    "which_emi": ("Which EMI do you mean?", "कौन सी EMI की बात कर रहे हैं?", "Kaunsi EMI ki baat kar rahe ho?"),
    "which_policy": ("Which policy do you mean?", "कौन सी पॉलिसी की बात कर रहे हैं?", "Kaunsi policy ki baat kar rahe ho?"),
    "help_dashboard": ("I can help with loans, your cards, EMIs and insurance. Try one of these:",
                       "मैं लोन, आपके कार्ड, EMI और बीमा में मदद कर सकता हूँ। इनमें से कुछ पूछकर देखिए:",
                       "Main loan, cards, EMI aur insurance mein help kar sakta hoon. Inmein se kuch try karo:"),
    "help_loan": ("Tell me what the loan is for and how much you need, and I'll show suitable options with their real cost.",
                  "बताइए लोन किस लिए और कितना चाहिए — मैं सही विकल्प उनकी असली लागत के साथ दिखाऊँगा।",
                  "Batao loan kis liye aur kitna chahiye — main suitable options unki real cost ke saath dikhaunga."),
    "help_card": ("Tell me the purchase amount and what it's for, and I'll compare your cards.",
                  "ख़रीदारी की रक़म और मक़सद बताइए, मैं आपके कार्ड की तुलना करूँगा।",
                  "Purchase amount aur kis liye hai batao, main aapke cards compare karunga."),
    "help_emi": ("Ask me about due dates, reminders, or what happens if you miss or prepay an EMI.",
                 "ड्यू डेट, रिमाइंडर, या EMI छूटने या पहले चुकाने पर क्या होगा — यह पूछिए।",
                 "Due dates, reminders, ya EMI miss ya prepay karne par kya hoga — yeh poochho."),
    "help_insurance": ("Ask me about your policies — coverage, exclusions, claim steps — or explore new plans.",
                       "अपनी पॉलिसी के बारे में पूछिए — क्या कवर है, क्या नहीं, क्लेम कैसे करें — या नए प्लान देखिए।",
                       "Apni policies ke baare mein poochho — coverage, exclusions, claim steps — ya naye plans dekho."),
    "help_emergency": ("Tell me who needs care and I'll show which of their policies may apply and what to do next.",
                       "बताइए किसे इलाज चाहिए — मैं दिखाऊँगा कि उनकी कौन सी पॉलिसी काम आ सकती है और आगे क्या करना है।",
                       "Batao kisko care chahiye — main dikhaunga unki kaunsi policy kaam aa sakti hai aur aage kya karna hai."),
}


def t(lang: str, key: str) -> str:
    en, hi, hg = TEXT[key]
    return pick(lang, en, hi, hg)


SUGGESTIONS_HI = {
    "dashboard": ["कार के लिए 5 लाख का लोन चाहिए", "₹30,000 की फ़्लाइट के लिए कौन सा कार्ड?", "मेरी आने वाली EMI दिखाओ", "माँ अस्पताल में हैं — कौन सी पॉलिसी काम आएगी?"],
    "loan": ["3 साल के लिए 3 लाख का पर्सनल लोन", "असली लागत कितनी है?", "पहले दो की तुलना करो"],
    "card": ["₹30,000 की फ़्लाइट के लिए कौन सा कार्ड?", "क्रेडिट यूटिलाइज़ेशन क्या है?", "मिनिमम अमाउंट ड्यू क्या है?"],
    "emi": ["अगर अगली EMI छूट जाए तो?", "₹1 लाख प्रीपे करूँ तो?"],
    "insurance": ["मेरी पॉलिसी में क्या कवर नहीं है?", "वेटिंग पीरियड क्या है?", "फैमिली फ्लोटर और इंडिविजुअल कवर में क्या अंतर है?"],
    "emergency": ["कौन सी पॉलिसी काम आएगी?", "कौन से दस्तावेज़ चाहिए?"],
    "document": ["इस दस्तावेज़ का सार बताओ", "कुल रकम कितनी है?"],
}
SUGGESTIONS_HINGLISH = {
    "dashboard": ["Car ke liye 5 lakh ka loan chahiye", "₹30,000 ki flight ke liye kaunsa card?", "Meri upcoming EMIs dikhao", "Maa hospital mein hai — kaunsi policy kaam aayegi?"],
    "loan": ["3 saal ke liye 3 lakh ka personal loan", "Real cost kitna padega?", "Top do compare karo"],
    "card": ["₹30,000 ki flight ke liye kaunsa card?", "Credit utilisation kya hai?", "Minimum amount due kya hai?"],
    "emi": ["Agar agli EMI miss ho gayi toh?", "₹1 lakh prepay karun toh?"],
    "insurance": ["Meri policy mein kya cover nahi hai?", "Waiting period kya hai?", "Family floater aur individual cover mein kya farq hai?"],
    "emergency": ["Kaunsi policy kaam aayegi?", "Kaunse documents chahiye?"],
    "document": ["Is document ka summary batao", "Total kitna hai?"],
}
