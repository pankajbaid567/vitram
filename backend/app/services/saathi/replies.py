"""Tool-mode replies in English, Hindi and Hinglish — built strictly from tool output.

Every number comes from the tool result and is formatted with `inr`/`group`; only the wording changes by
language. Product, lender and document names are kept as-is (proper nouns). English detail strings from
tools (cautions, reasons) are shown in the cards below the reply rather than mixed into Hindi sentences.
"""

from datetime import date

from app.fmt import group, inr
from app.services.saathi.i18n import pick, t


def _months(n: int, lang: str) -> str:
    return pick(lang, f"{n} months", f"{n} महीने", f"{n} mahine")


def compose(name: str, d: dict, ctx: dict, lang: str = "en") -> str:
    P = lambda en, hi, hg: pick(lang, en, hi, hg)  # noqa: E731
    if d.get("needs") == "member_key":
        return t(lang, "who_for")
    if d.get("needs") == "emi_id":
        return t(lang, "which_emi")
    if d.get("needs") == "policy_id":
        return t(lang, "which_policy")

    if name == "loans_search":
        r = d["results"]
        if not r:
            missing = f" {d['missing_data'][0]['message']}" if d["missing_data"] and lang == "en" else ""
            return P("None of the loans in the sample catalogue fit these details." + missing,
                     "सैंपल कैटलॉग का कोई भी लोन इन जानकारियों पर फ़िट नहीं होता।",
                     "Sample catalogue ka koi bhi loan in details par fit nahi hota.")
        x = r[0]
        s = P(f"I found {len(r)} option{'s' if len(r) > 1 else ''} in the sample catalogue (fictional lenders, indicative rates). "
              f"{x['product']} from {x['lender']} may fit best: EMI about {inr(x['monthly_emi'])} for {x['tenure_months']} months, "
              f"total cost of credit {inr(x['total_cost_of_credit'])} including fees.",
              f"सैंपल कैटलॉग में {len(r)} विकल्प मिले (काल्पनिक लेंडर, अनुमानित दरें)। {x['lender']} का {x['product']} सबसे उपयुक्त हो सकता है: "
              f"{_months(x['tenure_months'], lang)} के लिए EMI लगभग {inr(x['monthly_emi'])}, फ़ीस मिलाकर लोन की कुल लागत {inr(x['total_cost_of_credit'])}।",
              f"Sample catalogue mein {len(r)} options mile (fictional lenders, indicative rates). {x['lender']} ka {x['product']} best fit ho sakta hai: "
              f"{x['tenure_months']} mahine ke liye EMI lagbhag {inr(x['monthly_emi'])}, fees milake total cost of credit {inr(x['total_cost_of_credit'])}.")
        if x["cautions"]:
            s += P(f" Note: {x['cautions'][0]}", " ध्यान देने वाली बातें नीचे कार्ड में हैं।", " Dhyaan dene wali baatein neeche card mein hain.")
        return s

    if name == "finance_loan_cost":
        s = P(f"Paying on time, EMI is {inr(d['monthly_emi'])} for {d['tenure_months']} months. Interest adds {inr(d['scheduled_interest'])} "
              f"and upfront charges with GST add {inr(d['upfront_charges_total'])}, so you'd pay {inr(d['scheduled_total_outflow'])} in total "
              f"for {inr(d['principal'])} borrowed.",
              f"समय पर भरने पर EMI {_months(d['tenure_months'], lang)} तक {inr(d['monthly_emi'])} है। ब्याज {inr(d['scheduled_interest'])} और GST समेत "
              f"शुरुआती चार्ज {inr(d['upfront_charges_total'])} जुड़ते हैं, यानी {inr(d['principal'])} उधार लेने पर आप कुल {inr(d['scheduled_total_outflow'])} चुकाएँगे।",
              f"Time par bharne par EMI {d['tenure_months']} mahine tak {inr(d['monthly_emi'])} hai. Interest {inr(d['scheduled_interest'])} aur GST ke saath "
              f"upfront charges {inr(d['upfront_charges_total'])} judte hain, yaani {inr(d['principal'])} udhaar lene par aap total {inr(d['scheduled_total_outflow'])} chukaoge.")
        if d.get("annualized_cost_pct"):
            s += P(f" That's an annualized cost of about {d['annualized_cost_pct']:.2f}% (estimate).",
                   f" यह सालाना लगभग {d['annualized_cost_pct']:.2f}% की लागत है (अनुमान)।",
                   f" Yeh saalana lagbhag {d['annualized_cost_pct']:.2f}% ki cost hai (estimate).")
        if d.get("missing"):
            s += P(f" Not included: {d['missing'][0]}.", " कुछ चार्ज दस्तावेज़ में नहीं लिखे, इसलिए शामिल नहीं हैं।", " Kuch charges likhe nahi hain, isliye include nahi kiye.")
        if d.get("contingent_charges"):
            s += P(" Late-payment and foreclosure charges are shown separately because they only apply in those situations.",
                   " लेट पेमेंट और फ़ोरक्लोज़र चार्ज अलग दिखाए गए हैं, क्योंकि वे सिर्फ़ उन्हीं हालात में लगते हैं।",
                   " Late payment aur foreclosure charges alag dikhaye hain, kyunki woh sirf unhi situations mein lagte hain.")
        return s

    if name in ("finance_loan_what_if", "finance_emi_what_if"):
        if not d.get("computable"):
            why = d.get("missing") or d.get("notes") or ["Some terms are missing."]
            return P(f"I can't calculate this precisely: {why[0]}. Add it and I'll work it out.",
                     "मैं इसका सटीक हिसाब नहीं लगा सकता, क्योंकि ज़रूरी शर्तें (जैसे लेट फ़ीस या ब्याज दर) दर्ज नहीं हैं। उन्हें जोड़िए, मैं हिसाब लगा दूँगा — अंदाज़े से जुर्माना नहीं बताऊँगा।",
                     "Main iska exact hisaab nahi laga sakta, kyunki zaroori terms (jaise late fee ya interest rate) add nahi hain. Unhe add karo, main calculate kar dunga — andaaze se penalty nahi bataunga.")
        k, b, s = d["kind"], d["baseline"], d["scenario"]
        if k in ("missed_payment", "late_payment"):
            return P(f"Paying {s['days_late']} days late would add about {inr(s['extra_cost'])} under the stated terms "
                     f"(late fee {inr(s['late_fee'])}, penal interest {inr(s['penal_interest'])}, GST {inr(s['gst'])}). The EMI itself is still due.",
                     f"{s['days_late']} दिन देर से भरने पर शर्तों के हिसाब से लगभग {inr(s['extra_cost'])} ज़्यादा लगेंगे "
                     f"(लेट फ़ीस {inr(s['late_fee'])}, पेनल ब्याज {inr(s['penal_interest'])}, GST {inr(s['gst'])})। EMI तो फिर भी भरनी होगी।",
                     f"{s['days_late']} din late bharne par terms ke hisaab se lagbhag {inr(s['extra_cost'])} extra lagenge "
                     f"(late fee {inr(s['late_fee'])}, penal interest {inr(s['penal_interest'])}, GST {inr(s['gst'])}). EMI toh phir bhi bharni hogi.")
        if k == "prepayment":
            reduce_emi = (d.get("inputs") or {}).get("mode") == "reduce_emi"
            sooner = max(b["tenure_months"] - s["total_tenure_months"], 0)
            s1 = P(f"Prepaying {inr(s['prepay_amount'])} saves about {inr(s['interest_saved'])} in interest; "
                   + (f"the EMI becomes {inr(s['monthly_emi'])}." if reduce_emi else f"the loan ends {sooner} months sooner."),
                   f"{inr(s['prepay_amount'])} पहले चुकाने से ब्याज में लगभग {inr(s['interest_saved'])} बचेंगे; "
                   + (f"EMI {inr(s['monthly_emi'])} हो जाएगी।" if reduce_emi else f"लोन {sooner} महीने पहले ख़त्म होगा।"),
                   f"{inr(s['prepay_amount'])} prepay karne se interest mein lagbhag {inr(s['interest_saved'])} bachenge; "
                   + (f"EMI {inr(s['monthly_emi'])} ho jayegi." if reduce_emi else f"loan {sooner} mahine pehle khatam hoga."))
            if s.get("prepayment_charge") is not None:
                s1 += P(f" The prepayment charge is {inr(s['prepayment_charge'])}.", f" प्रीपेमेंट चार्ज {inr(s['prepayment_charge'])} है।",
                        f" Prepayment charge {inr(s['prepayment_charge'])} hai.")
            else:
                s1 += P(" The prepayment charge isn't stated, so the net saving isn't known.",
                        " प्रीपेमेंट चार्ज लिखा नहीं है, इसलिए कुल बचत पता नहीं।", " Prepayment charge likha nahi hai, isliye net saving pata nahi.")
            return s1
        if k == "rate_change":
            if s["monthly_emi"] != b["monthly_emi"]:
                return P(f"At {s['annual_rate_pct']:g}%, the EMI would change from {inr(b['monthly_emi'])} to {inr(s['monthly_emi'])}.",
                         f"{s['annual_rate_pct']:g}% पर EMI {inr(b['monthly_emi'])} से बदलकर {inr(s['monthly_emi'])} हो जाएगी।",
                         f"{s['annual_rate_pct']:g}% par EMI {inr(b['monthly_emi'])} se badalkar {inr(s['monthly_emi'])} ho jayegi.")
            extra = s["total_interest"] - b["total_interest"]
            return P(f"At {s['annual_rate_pct']:g}% with the same EMI, the loan would take {s['tenure_months']} months instead of {b['tenure_months']}, costing {inr(extra)} more interest.",
                     f"{s['annual_rate_pct']:g}% पर उसी EMI के साथ लोन {b['tenure_months']} की जगह {s['tenure_months']} महीने चलेगा, और {inr(extra)} ज़्यादा ब्याज लगेगा।",
                     f"{s['annual_rate_pct']:g}% par same EMI ke saath loan {b['tenure_months']} ki jagah {s['tenure_months']} mahine chalega, aur {inr(extra)} zyada interest lagega.")
        if k in ("tenure_change", "amount_change"):
            return P(f"EMI goes from {inr(b['monthly_emi'])} to {inr(s['monthly_emi'])}, and total interest from {inr(b['total_interest'])} to {inr(s['total_interest'])}.",
                     f"EMI {inr(b['monthly_emi'])} से {inr(s['monthly_emi'])} और कुल ब्याज {inr(b['total_interest'])} से {inr(s['total_interest'])} हो जाता है।",
                     f"EMI {inr(b['monthly_emi'])} se {inr(s['monthly_emi'])} aur total interest {inr(b['total_interest'])} se {inr(s['total_interest'])} ho jata hai.")
        return P("Here's the scenario.", "यह रहा हिसाब।", "Yeh raha hisaab.")

    if name == "loans_compare":
        c = min(d["products"], key=lambda p: p["scheduled_total_outflow"])
        return P(f"Here's the side-by-side comparison. {c['product']} has the lowest scheduled total outflow ({inr(c['scheduled_total_outflow'])}); check the warnings for each.",
                 f"यह रही तुलना। {c['product']} में कुल भुगतान सबसे कम ({inr(c['scheduled_total_outflow'])}) है; हर विकल्प की चेतावनियाँ ज़रूर देखें।",
                 f"Yeh rahi comparison. {c['product']} mein total payment sabse kam ({inr(c['scheduled_total_outflow'])}) hai; har option ki warnings zaroor dekho.")

    if name == "cards_best_for_spend":
        if not d["ranked"]:
            return P("I couldn't put a rupee value on rewards for your cards for this purchase.",
                     "इस ख़रीदारी पर आपके कार्ड के रिवॉर्ड का रुपये में मूल्य नहीं निकाला जा सका।",
                     "Is purchase par aapke cards ke rewards ki rupee value nahi nikal paayi.")
        x = d["ranked"][0]
        worth = inr(x["value_inr"]) if x["value_inr"] is not None else None
        s = P(f"For this {d['category'].lower()} purchase, {x['card']} earns the most: about {group(x['reward_units'])} {x['unit']}" + (f" (worth about {worth})." if worth else "."),
              f"इस ख़रीदारी पर {x['card']} सबसे ज़्यादा देता है: लगभग {group(x['reward_units'])} {x['unit']}" + (f" (क़ीमत लगभग {worth})।" if worth else "।"),
              f"Is purchase par {x['card']} sabse zyada deta hai: lagbhag {group(x['reward_units'])} {x['unit']}" + (f" (value lagbhag {worth})." if worth else "."))
        if x["caveats"]:
            s += P(f" {x['caveats'][0]}", " सीमा और शर्तें नीचे कार्ड में हैं।", " Caps aur conditions neeche card mein hain.")
        if d["unranked"]:
            u = d["unranked"][0]["card"]
            s += P(f" {u} can't be compared in rupees because its points have no known value.",
                   f" {u} की रुपये में तुलना नहीं हो सकती, क्योंकि उसके पॉइंट्स का मूल्य पता नहीं है।",
                   f" {u} ko rupees mein compare nahi kar sakte, kyunki uske points ki value pata nahi hai.")
        return s

    if name == "cards_list":
        n = len(d["cards"])
        return P(f"You have {n} card{'s' if n != 1 else ''} in VITTRM.", f"VITTRM में आपके {n} कार्ड हैं।", f"VITTRM mein aapke {n} cards hain.")

    if name == "emis_list":
        if not d["emis"]:
            return P("You don't have any EMIs in VITTRM yet. Add one, or upload a bank statement to detect them.",
                     "VITTRM में अभी कोई EMI नहीं है। जोड़िए, या बैंक स्टेटमेंट अपलोड कीजिए ताकि वे पहचानी जा सकें।",
                     "VITTRM mein abhi koi EMI nahi hai. Add karo, ya bank statement upload karo taaki woh detect ho sakein.")
        nxt = min(d["emis"], key=lambda e: e["next_due"])
        unconf = sum(1 for e in d["emis"] if not e["confirmed"])
        n = len(d["emis"])
        s = P(f"You have {n} EMIs totalling {inr(d['monthly_total'])} a month. Next due: {nxt['title']} on {nxt['next_due']}.",
              f"आपकी {n} EMI हैं, हर महीने कुल {inr(d['monthly_total'])}। अगली: {nxt['title']}, {nxt['next_due']} को।",
              f"Aapki {n} EMIs hain, har mahine total {inr(d['monthly_total'])}. Agli: {nxt['title']}, {nxt['next_due']} ko.")
        if unconf:
            s += P(f" {unconf} {'was' if unconf == 1 else 'were'} detected from your statement and need confirming.",
                   f" {unconf} स्टेटमेंट से पहचानी गई हैं और उनकी पुष्टि बाक़ी है।",
                   f" {unconf} statement se detect hui hain aur confirm karni baaki hain.")
        return s

    if name == "reminders_create":
        ch = d["channel"]
        s = P(f"Reminders are set up ({ch}).", f"रिमाइंडर सेट हो गए ({'WhatsApp' if ch == 'WhatsApp' else 'ऐप में'})।",
              f"Reminders set ho gaye ({'WhatsApp' if ch == 'WhatsApp' else 'app mein'}).")
        if ch == "in-app" and not d["whatsapp_configured"]:
            s += P(" WhatsApp isn't connected in this environment, so they'll appear in VITTRM.",
                   " यहाँ WhatsApp जुड़ा नहीं है, इसलिए रिमाइंडर VITTRM में दिखेंगे।",
                   " Yahan WhatsApp connected nahi hai, isliye reminders VITTRM mein dikhenge.")
        return s

    if name == "insurance_search":
        r = d["results"]
        if not r:
            return P("No plans in the sample catalogue fit the selected people.", "सैंपल कैटलॉग का कोई प्लान चुने गए लोगों पर फ़िट नहीं होता।",
                     "Sample catalogue ka koi plan chune gaye logon par fit nahi hota.")
        x = r[0]
        prem = inr(x["indicative_premium"]) if x.get("indicative_premium") else None
        return P(f"From the sample catalogue (fictional insurers), {x['product']} by {x['insurer']} may fit" + (f" with an indicative premium of {prem} a year" if prem else "")
                 + f". {x['why'][-1] if x['why'] else ''} Premiums are indicative, not quotes.",
                 f"सैंपल कैटलॉग (काल्पनिक बीमा कंपनियाँ) से {x['insurer']} का {x['product']} उपयुक्त हो सकता है" + (f", अनुमानित प्रीमियम {prem} सालाना" if prem else "")
                 + "। प्रीमियम अनुमान हैं, कोटेशन नहीं।",
                 f"Sample catalogue (fictional insurers) se {x['insurer']} ka {x['product']} fit ho sakta hai" + (f", indicative premium {prem} saalana" if prem else "")
                 + ". Premiums indicative hain, quote nahi.")

    if name == "insurance_compare":
        return P("Here's the comparison. Premiums from the sample catalogue are indicative.", "यह रही तुलना। सैंपल कैटलॉग के प्रीमियम अनुमानित हैं।",
                 "Yeh rahi comparison. Sample catalogue ke premiums indicative hain.")

    if name == "insurance_find_applicable_existing":
        apps = [p for p in d["policies"] if p["status"] == "may_apply"]
        who = d["person"]
        if not d["policies"]:
            return P(f"I don't see any uploaded policy that covers {who}. Upload their policy, or talk to a consultant.",
                     f"{who} को कवर करने वाली कोई पॉलिसी अपलोड नहीं है। उनकी पॉलिसी अपलोड कीजिए या सलाहकार से बात कीजिए।",
                     f"{who} ko cover karne wali koi policy upload nahi hai. Unki policy upload karo ya consultant se baat karo.")
        if not apps:
            return P(f"None of {who}'s uploaded policies look applicable to {d['event'].lower()}.",
                     f"{who} की अपलोड की गई कोई भी पॉलिसी इस स्थिति पर लागू होती नहीं दिखती।",
                     f"{who} ki upload ki gayi koi bhi policy is situation par lagu hoti nahi dikhti.")
        p = apps[0]
        parts = [P(f"{p['name']} may apply for {who}", f"{who} के लिए {p['name']} काम आ सकती है", f"{who} ke liye {p['name']} kaam aa sakti hai")]
        if p.get("sum_insured"):
            parts[0] += P(f" (sum insured {inr(p['sum_insured'])})", f" (सम इंश्योर्ड {inr(p['sum_insured'])})", f" (sum insured {inr(p['sum_insured'])})")
        parts[0] += P(".", "।", ".")
        if p.get("claim_intimation"):
            hrs = str(p["claim_intimation"]).replace("hours", "घंटे").replace("days", "दिन") if lang == "hi" else p["claim_intimation"]
            parts.append(P(f"Inform the insurer within {p['claim_intimation']}.", f"बीमा कंपनी को {hrs} के अंदर सूचना दीजिए।",
                           f"Insurer ko {p['claim_intimation']} ke andar inform karo."))
        if p.get("copay"):
            parts.append(P(f"There's a {p['copay']:g}% co-payment.", f"{p['copay']:g}% को-पेमेंट है, यानी हर क्लेम का इतना हिस्सा आपको देना होगा।",
                           f"{p['copay']:g}% co-payment hai, yaani har claim ka itna hissa aapko dena hoga."))
        if p.get("helpline"):
            parts.append(P(f"Claims helpline: {p['helpline']}.", f"क्लेम हेल्पलाइन: {p['helpline']}।", f"Claims helpline: {p['helpline']}."))
        parts.append(P("The insurer decides the claim; I can't promise approval.",
                       "क्लेम का फ़ैसला बीमा कंपनी करती है; मैं मंज़ूरी का वादा नहीं कर सकता।",
                       "Claim ka faisla insurer karta hai; main approval ka promise nahi kar sakta."))
        return " ".join(parts)

    if name == "insurance_policy_summary":
        return P(f"Here's the summary of {d['policy']}. Tap a source to see where each value came from.",
                 f"यह रहा {d['policy']} का सारांश। हर जानकारी कहाँ से आई, देखने के लिए स्रोत पर टैप कीजिए।",
                 f"Yeh raha {d['policy']} ka summary. Har value kahan se aayi, dekhne ke liye source par tap karo.")

    if name == "document_summary":
        if not d.get("found"):
            return P("I couldn't open that document.", "वह दस्तावेज़ नहीं खुल सका।", "Woh document open nahi hua.")
        doc, facts = d["document"], d["facts"]
        n, c = len(facts), d["confirmed"]
        scan = P(" It was read from a scan or photo, so check each value.", " यह स्कैन या फ़ोटो से पढ़ा गया है, इसलिए हर मान जाँच लें।",
                 " Yeh scan ya photo se padha gaya hai, isliye har value check karo.") if doc["read_from_scan"] else ""
        if not n:
            return P(f"VITTRM didn't find any values in {doc['name']}.{scan}", f"{doc['name']} में कोई मान नहीं मिला।{scan}",
                     f"{doc['name']} mein koi value nahi mili.{scan}")
        def show(f):
            v = f["value"]
            if f.get("unit") == "INR" and isinstance(v, (int, float)):
                return inr(v, paise=True)
            if isinstance(v, list):
                return f"{len(v)} lines"
            if isinstance(v, str) and len(v) == 10 and v[4] == "-" and v[7] == "-":
                try:
                    d0 = date.fromisoformat(v)
                    return f"{d0.day} {d0.strftime('%b %Y')}"
                except ValueError:
                    return v
            return v
        head = [f"{f['label']}: {show(f)}" for f in facts[:5]]
        listing = "; ".join(head)
        return P(f"From {doc['name']} VITTRM read {n} values ({c} confirmed by you): {listing}.{scan} Unconfirmed values are extracted, not checked.",
                 f"{doc['name']} से {n} मान पढ़े गए ({c} आपने पक्के किए): {listing}.{scan} बिना पुष्टि वाले मान सिर्फ़ पढ़े गए हैं, जाँचे नहीं गए।",
                 f"{doc['name']} se {n} values padhi gayi ({c} aapne confirm ki): {listing}.{scan} Unconfirmed values sirf padhi gayi hain, check nahi hui.")

    if name == "documents_search":
        if not d["found"]:
            return P("I couldn't find that in your documents, so I won't guess. Check the full document or ask a consultant.",
                     "यह आपके दस्तावेज़ों में नहीं मिला, इसलिए मैं अंदाज़ा नहीं लगाऊँगा। पूरा दस्तावेज़ देखिए या सलाहकार से पूछिए।",
                     "Yeh aapke documents mein nahi mila, isliye main guess nahi karunga. Poora document dekho ya consultant se poochho.")
        r = d["results"][0]
        quote = r["text"] if len(r["text"]) <= 220 else r["text"][:217] + "…"
        page = r["page"]
        sec = f", {r['section']}" if r.get("section") else ""
        # Quoted document text stays in its original language — it is source material, not a translation.
        return P(f"Here's what {r['document']} says (page {page}{sec}): “{quote}”",
                 f"{r['document']} (पेज {page}{sec}) में लिखा है: “{quote}”",
                 f"{r['document']} (page {page}{sec}) mein likha hai: “{quote}”")

    if name == "consultation_request":
        return P("I've drafted a consultation request. Review the summary and confirm the call on the next screen — nothing is shared until you do.",
                 "मैंने सलाह के लिए कॉल का अनुरोध तैयार किया है। अगली स्क्रीन पर सारांश देखकर पुष्टि कीजिए — आपकी पुष्टि से पहले कुछ भी साझा नहीं होगा।",
                 "Maine consultation request draft kar di hai. Agli screen par summary dekhkar confirm karo — aapke confirm karne se pehle kuch share nahi hoga.")

    if name == "profile_get_slice":
        inc = d.get("monthly_income") or {}
        if isinstance(inc, dict) and inc.get("value"):
            est = inc.get("state") == "extracted"
            s = P(f"Your monthly income is {inr(inc['value'])} ({'estimated from your statement' if est else 'confirmed'}).",
                  f"आपकी मासिक आय {inr(inc['value'])} है ({'स्टेटमेंट से अनुमान' if est else 'पुष्टि की हुई'})।",
                  f"Aapki monthly income {inr(inc['value'])} hai ({'statement se estimate' if est else 'confirmed'}).")
            sur = (d.get("monthly_surplus") or {}).get("value") if isinstance(d.get("monthly_surplus"), dict) else None
            if sur is not None:
                s += P(f" On average you have {inr(sur)} left each month.", f" औसतन हर महीने {inr(sur)} बचते हैं।", f" Average har mahine {inr(sur)} bachte hain.")
            return s
        return P("Here's what VITTRM knows from your profile.", "आपकी प्रोफ़ाइल से VITTRM को यह पता है।", "Aapki profile se VITTRM ko yeh pata hai.")
    return ""
