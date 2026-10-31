"""Fast deterministic answers for common financial questions.

These answers explain concepts only. Questions about a user's own card or
policy continue through document and calculation tools.
"""

import re

from sqlalchemy.orm import Session

from app.models import CardProduct, InsuranceProduct


FAQS = [
    ("credit_utilisation", "cards", r"credit utili[sz]ation|utili[sz]ation ratio|limit ka kitna", "What is credit utilisation?", "Credit utilisation is the share of your total card limit currently used. Example: ₹20,000 outstanding on a ₹1 lakh limit is 20%. Lower and consistently paid-in-full utilisation is generally healthier than frequently maxing out cards."),
    ("minimum_due", "cards", r"minimum (?:amount )?due|min(?:imum)? due", "What does minimum amount due mean?", "Minimum amount due is the smallest payment that normally keeps the bill from being marked unpaid. Paying only that amount can leave the rest accruing interest and may also end the interest-free period. Pay the full statement balance by the due date when possible."),
    ("statement_due", "cards", r"statement (?:date|balance).*(?:due date)?|difference.*statement.*due|billing date", "Statement date vs due date", "The statement date closes a billing cycle and fixes that month's bill. The due date is the deadline to pay it. Purchases after the statement date usually appear in the next cycle, subject to the issuer's posting rules."),
    ("interest_free", "cards", r"interest[- ]free|grace period|free credit period", "How does the interest-free period work?", "The interest-free period runs from a purchase date to that statement's payment due date. Its length varies by purchase timing. It usually applies only when previous dues are paid in full; cash withdrawals and carried balances can follow different rules."),
    ("cash_advance", "cards", r"cash (?:withdraw|advance)|atm.*credit card", "Should I withdraw cash using a credit card?", "Credit-card cash withdrawals commonly have a fee and can start accruing interest immediately, without the normal purchase grace period. Check the issuer's current tariff before using this option."),
    ("reward_value", "cards", r"reward point.*(?:worth|value)|point value|redeem.*points", "How much is one reward point worth?", "A reward point has no universal rupee value. It depends on the card and redemption option, and transfers, vouchers, travel bookings and statement credit may value the same point differently. Check conversion rates, caps, fees and expiry together."),
    ("reward_missing", "cards", r"reward.*(?:missing|not credited|nahi mila)|points.*(?:missing|nahi)", "Why were rewards not credited?", "Common reasons are excluded merchant categories, monthly caps, minimum transaction rules, refunds, wallet loads, rent or government payments, or a different merchant category code. Compare the posted transaction and current reward terms; raise a dispute if it still qualifies."),
    ("rupay_upi", "cards", r"rupay.*upi|upi.*credit card", "How does RuPay credit card on UPI work?", "An eligible RuPay credit card can be linked to a supported UPI app for merchant payments. Person-to-person transfers and some merchant categories may be restricted, and rewards depend on the issuer's terms."),
    ("forex_markup", "cards", r"forex|foreign currency|international transaction.*fee", "What is a forex markup?", "Forex markup is an issuer charge on foreign-currency transactions, usually added to the card-network conversion. Taxes may apply to the markup. Dynamic currency conversion can be costlier, so compare paying in local currency with the displayed INR conversion."),
    ("chargeback", "cards", r"chargeback|card dispute|unauthori[sz]ed transaction", "What should I do about an unauthorised card transaction?", "Block or temporarily lock the card, inform the issuer immediately, and raise a dispute through its official channel. Keep the complaint reference and evidence. Reporting timelines matter, so do not wait for the next statement."),
    ("card_emi", "cards", r"convert.*(?:purchase|transaction).*(?:emi)|card emi|emi conversion", "How does credit-card EMI conversion work?", "Card EMI splits an eligible purchase or outstanding amount into instalments. Compare the interest rate, processing fee, taxes, foreclosure charge and lost rewards against other credit options before converting."),
    ("waiting_period", "insurance", r"waiting period|ped wait|pre[- ]existing.*wait", "What is an insurance waiting period?", "A waiting period is time during which specified claims are not covered. Health policies may have separate initial, pre-existing-disease and named-treatment waiting periods. Accidents can have different rules. The policy wording and customer information sheet control the exact dates."),
    ("sum_insured", "insurance", r"sum insured|insurance cover amount", "What is sum insured?", "Sum insured is the policy's stated coverage limit, subject to deductibles, sub-limits, co-pay, exclusions and restoration rules. In a family floater, members generally share the available limit; in individual cover, each person has a separate limit."),
    ("family_floater", "insurance", r"family floater|floater.*individual|individual.*floater", "Family floater vs individual health insurance", "A family floater shares one sum insured among covered family members. Individual policies allocate cover separately. Floaters can be economical for younger families, while separate cover can reduce the risk that one large claim exhausts cover for everyone."),
    ("copay", "insurance", r"co[- ]?pay|copayment", "What is co-pay in health insurance?", "Co-pay is the percentage of an admissible claim that you must pay. With a 20% co-pay, the insurer assesses the covered claim and you bear 20% of the admissible amount, plus any non-payable items."),
    ("deductible", "insurance", r"deductible", "What is an insurance deductible?", "A deductible is the amount that must be borne before the policy pays under its terms. In top-up plans it may apply per claim; in super top-up plans it is commonly tested against eligible claims accumulated over the policy year. Check the exact wording."),
    ("room_rent", "insurance", r"room rent|room limit|proportionate deduction", "Why does the room-rent limit matter?", "A room-rent cap limits the eligible hospital room category or daily amount. Some policies can proportionately reduce associated charges when you choose a room above the allowed limit. Confirm both the cap and the proportionate-deduction clause."),
    ("cashless_reimbursement", "insurance", r"cashless.*reimburse|reimburse.*cashless|cashless claim", "Cashless vs reimbursement claim", "In a cashless claim, the network hospital seeks insurer or TPA authorisation and the approved amount is settled directly. In reimbursement, you pay first and submit documents later. Cashless authorisation is not a guarantee that every expense is payable."),
    ("restoration", "insurance", r"restoration|restore benefit|recharge.*cover", "What is restoration benefit?", "Restoration can refill used sum insured under stated conditions. Plans differ on whether it activates after partial or full exhaustion, covers the same illness, and can be used once or repeatedly. It is not automatically identical to extra base cover."),
    ("topup", "insurance", r"super top[- ]?up|top[- ]?up.*insurance|difference.*top.*super", "Top-up vs super top-up health insurance", "A top-up commonly applies the deductible to each claim. A super top-up commonly considers eligible claims accumulated during the policy year. Because wording varies, compare deductible basis, exclusions, waiting periods and whether the base policy must be from the same insurer."),
    ("network_hospital", "insurance", r"network hospital|non[- ]network hospital", "What is a network hospital?", "A network hospital has a cashless arrangement with the insurer or TPA. Networks can change, so verify the hospital and branch with the insurer before planned admission. Non-network treatment may still be reimbursable if policy conditions are met."),
    ("claim_documents", "insurance", r"claim.*documents|documents.*claim|claim ke liye.*document", "Which documents are usually needed for a health claim?", "Common documents include the claim form, policy or health-card details, discharge summary, final itemised bill, payment receipts, prescriptions, investigation reports, pharmacy bills, ID and bank details. Your insurer may require additional originals or forms."),
    ("term_vs_investment", "insurance", r"term insurance.*investment|term.*endowment|pure term", "Term insurance vs savings insurance", "Pure term insurance primarily pays the death benefit if the insured dies during the covered term and usually has no maturity value. Savings or endowment plans combine insurance with a savings benefit. Compare protection needed, guaranteed and non-guaranteed values, liquidity and total premiums separately."),
    ("nominee", "insurance", r"nominee|nomination", "What does an insurance nominee do?", "A nominee is the person designated to receive policy money and support claim processing after the policyholder's death, subject to applicable law and policy terms. Keep nomination and contact details current and tell the nominee where policy records are stored."),
    ("free_look", "insurance", r"free[- ]look|free look period", "What is the free-look period?", "The free-look period lets a new policyholder review the issued policy and request cancellation within the permitted window if the terms are unsuitable. Deductions and timelines follow the policy and applicable rules, so use the insurer's official cancellation process promptly."),
]

_PERSONAL = re.compile(r"\b(my|mine|mera|meri|mere|hamari|our|this policy|this card|is policy|is card)\b", re.I)

HINGLISH = {
    "credit_utilisation": "Credit utilisation matlab aapki total card limit ka kitna hissa use hua hai. Jaise ₹1 lakh limit par ₹20,000 outstanding ho toh utilisation 20% hai. Limit ko baar-baar max out karne ke bajay balance full aur time par pay karna generally healthier hota hai.",
    "minimum_due": "Minimum amount due woh sabse chhoti payment hai jo bill ko normally unpaid mark hone se bachati hai. Sirf minimum pay karne par baaki balance par interest lag sakta hai aur interest-free period bhi khatam ho sakta hai. Ho sake toh due date tak full statement balance pay karo.",
    "waiting_period": "Waiting period woh samay hai jisme kuch claims cover nahi hote. Health policy mein initial, pre-existing disease aur listed treatment ke alag waiting periods ho sakte hain. Exact dates policy wording aur customer information sheet mein milengi.",
    "family_floater": "Family floater mein ek sum insured sab covered members share karte hain; individual cover mein har person ka limit alag hota hai. Floater young family ke liye economical ho sakta hai, lekin ek bada claim sabke available cover ko kam kar sakta hai.",
    "claim_documents": "Health claim mein aam taur par claim form, policy details, discharge summary, itemised final bill, receipts, prescriptions, reports, pharmacy bills, ID aur bank details chahiye. Insurer extra originals ya forms bhi maang sakta hai.",
    "copay": "Co-pay admissible claim ka woh percentage hai jo aapko dena hota hai. 20% co-pay mein insurer covered claim assess karega aur admissible amount ka 20% aap denge, non-payable items alag.",
    "deductible": "Deductible woh amount hai jiske baad policy apni terms ke hisaab se pay karti hai. Top-up mein yeh aksar har claim par aur super top-up mein policy year ke eligible claims ke total par check hota hai. Exact wording zaroor dekho.",
}

HINDI = {
    "credit_utilisation": "क्रेडिट यूटिलाइज़ेशन आपकी कुल कार्ड लिमिट का इस्तेमाल हुआ हिस्सा है। जैसे ₹1 लाख की लिमिट पर ₹20,000 बकाया हो तो यूटिलाइज़ेशन 20% है। लिमिट बार-बार पूरी इस्तेमाल करने के बजाय बिल पूरा और समय पर चुकाना आम तौर पर बेहतर होता है।",
    "minimum_due": "मिनिमम अमाउंट ड्यू वह सबसे छोटी राशि है जिसे चुकाने पर बिल सामान्यतः unpaid नहीं माना जाता। केवल यह राशि भरने पर बाकी बकाया पर ब्याज लग सकता है और interest-free period भी खत्म हो सकता है। संभव हो तो due date तक पूरा statement balance चुकाएँ।",
    "waiting_period": "वेटिंग पीरियड वह समय है जिसमें कुछ क्लेम कवर नहीं होते। हेल्थ पॉलिसी में initial, pre-existing disease और कुछ treatments के अलग waiting periods हो सकते हैं। सही तारीख policy wording और customer information sheet में देखें।",
    "family_floater": "फैमिली फ्लोटर में एक sum insured सभी covered members साझा करते हैं; individual cover में हर व्यक्ति की limit अलग होती है। एक बड़ा claim floater में बाकी परिवार के लिए उपलब्ध cover घटा सकता है।",
    "claim_documents": "हेल्थ क्लेम में आम तौर पर claim form, policy details, discharge summary, itemised final bill, receipts, prescriptions, reports, pharmacy bills, ID और bank details चाहिए। Insurer अतिरिक्त original documents भी माँग सकता है।",
    "copay": "Co-pay admissible claim का वह प्रतिशत है जो आपको देना होता है। 20% co-pay में admissible amount का 20% आप देंगे; non-payable items अलग हो सकते हैं।",
    "deductible": "Deductible वह राशि है जिसके बाद policy अपनी शर्तों के अनुसार भुगतान करती है। Top-up और super top-up में इसका आधार अलग हो सकता है, इसलिए exact policy wording देखें।",
}


def list_faqs(category: str | None = None) -> list[dict]:
    return [{"id": key, "category": cat, "question": question} for key, cat, _, question, _ in FAQS
            if not category or cat == category]


def answer(text: str, lang: str = "en") -> dict | None:
    if _PERSONAL.search(text):
        return None
    for key, category, pattern, question, response in FAQS:
        if re.search(pattern, text, re.I):
            localized = HINDI.get(key) if lang == "hi" else HINGLISH.get(key) if lang == "hinglish" else None
            return {"id": key, "category": category, "question": question, "text": localized or response}
    return None


def product_answer(db: Session, text: str) -> dict | None:
    """Explain a named market product without inventing its current terms."""
    query = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    if len(query) < 5:
        return None
    candidates = []
    for row in db.query(CardProduct).all():
        if row.data.get("reference_only"):
            candidates.append((row.card_name, row.issuer, "credit card", row.data))
    for row in db.query(InsuranceProduct).all():
        if row.data.get("reference_only"):
            candidates.append((row.product_name, row.insurer, row.type.replace("_", " "), row.data))
    candidates.sort(key=lambda item: len(item[0]), reverse=True)
    for name, provider, kind, data in candidates:
        needle = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
        short = re.sub(r"\b(?:credit card|insurance policy|insurance plan|card|policy|plan)\b", "", needle)
        short = re.sub(r"\s+", " ", short).strip()
        if needle in query or (len(short) >= 5 and short in query):
            uses = ", ".join(data.get("best_for", [])) or "general use"
            url = data.get("official_url")
            return {
                "id": data["id"], "category": "product", "question": name,
                "text": (f"{name} is a {kind} from {provider}. It is commonly positioned for {uses}. "
                         "VITRAM keeps it as a market-reference product, so I won't guess current fees, rewards, "
                         f"waiting periods or eligibility. Verify the latest terms on the official product page: {url}"),
            }
    return None
