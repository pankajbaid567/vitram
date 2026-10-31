"""Insurance policy extraction (RD §10.1, §15.2).

Heuristic, label- and section-driven extraction from text-layer policy
schedules/wordings. Every fact carries page, section, snippet and confidence.
Anything not found stays absent (shown as "Not found in this document"),
never guessed.
"""

import re

from app.services.extractors.common import (
    AMOUNT,
    Extraction,
    Fact,
    bullets,
    chunk_pages,
    clean,
    find_line,
    find_section,
    looks_like_injection,
    mask_ref,
    parse_any_date,
    section_for_page_line,
    sections,
    strip_running_lines,
    snippet,
    to_amount,
)

_DATE = r"(\d{1,2}[/-][A-Za-z0-9]{1,3}[/-]\d{2,4}|\d{1,2} [A-Za-z]{3,9} \d{4})"

LABELLED = [
    # key, label, fact_type, regex, kind
    ("insurer", "Insurer", "identity", r"^(?:insurer|insurance company|issued by)\s*[:\-]\s*(.+)$", "text"),
    ("product_name", "Plan name", "identity", r"^(?:plan|product|policy)\s*name\s*[:\-]\s*(.+)$", "text"),
    ("policy_number", "Policy number", "identity", r"policy\s*(?:no\.?|number)\s*[:\-]\s*([A-Za-z0-9/\-]+)", "ref"),
    ("policyholder", "Policyholder", "people", r"^(?:policyholder|policy holder|proposer)(?:'s)?\s*(?:name)?\s*[:\-]\s*(.+)$", "text"),
    ("sum_insured", "Sum insured", "financials", r"(?:sum insured|sum assured|cover amount|basic sum insured)\s*[:\-]?\s*" + AMOUNT, "amount"),
    ("premium", "Premium", "financials", r"(?:total premium|premium amount|annual premium|premium payable|premium)\s*(?:\(.*?\))?\s*[:\-]\s*" + AMOUNT, "amount"),
    ("premium_frequency", "Premium frequency", "financials", r"(?:premium (?:payment )?(?:frequency|mode)|payment mode)\s*[:\-]\s*(annual|yearly|monthly|quarterly|half[- ]yearly|single)", "text"),
    ("deductible", "Deductible", "financials", r"(?:deductible|aggregate deductible)\s*[:\-]\s*" + AMOUNT, "amount"),
    ("copay", "Co-payment", "financials", r"co-?pay(?:ment)?\s*[:\-]\s*(nil|none|\d{1,2}(?:\.\d)?\s*%)", "pct"),
    ("room_rent_limit", "Room rent limit", "restrictions", r"room rent(?: limit| capping)?\s*[:\-]\s*(.+)$", "text"),
    ("initial_waiting_period", "Initial waiting period", "coverage", r"initial waiting period\s*[:\-]\s*(\d+\s*(?:days?|months?))", "text"),
    ("ped_waiting_period", "Pre-existing disease waiting period", "coverage", r"pre-?existing (?:disease|condition)s?(?: \(ped\))?(?: waiting period)?\s*[:\-]\s*(\d+\s*(?:months?|years?))", "text"),
    ("specific_disease_waiting_period", "Specific illness waiting period", "coverage", r"specific (?:disease|illness)(?:es)?(?: waiting period)?\s*[:\-]\s*(\d+\s*(?:months?|years?))", "text"),
    ("claim_intimation", "Claim intimation deadline", "claims", r"(?:intimat\w+|notify|inform)[^.]{0,60}?within\s+(\d+\s*hours?|\d+\s*days?)", "text"),
    ("tpa", "TPA", "claims", r"(?:tpa|third party administrator)\s*(?:name)?\s*[:\-]\s*(.+)$", "text"),
    ("helpline", "Claims helpline", "claims", r"(?:toll[- ]?free|helpline|claims? (?:helpline|contact|phone))\s*(?:no\.?|number)?\s*[:\-]\s*([\d\s\-+]{8,20})", "text"),
    ("claims_email", "Claims email", "claims", r"([\w.+-]+@[\w-]+\.[\w.]+)", "email"),
    ("maturity_benefit", "Maturity benefit", "coverage", r"maturity benefit\s*[:\-]\s*(.+)$", "text"),
    ("death_benefit", "Death benefit", "coverage", r"death benefit\s*[:\-]\s*(.+)$", "text"),
]

SECTION_LISTS = [
    # key, label, fact_type, heading keywords
    ("benefits", "Benefits covered", "coverage", ("coverage", "benefits", "what is covered", "what's covered", "scope of cover")),
    ("exclusions", "Exclusions", "restrictions", ("exclusion", "not covered", "what is not covered")),
    ("conditions", "Important conditions", "restrictions", ("condition", "limits", "sub-limit", "sublimit")),
    ("riders", "Riders / add-ons", "coverage", ("rider", "add-on", "add on", "optional cover")),
    ("cashless_process", "Cashless claim steps", "claims", ("cashless",)),
    ("reimbursement_process", "Reimbursement claim steps", "claims", ("reimbursement",)),
    ("claim_documents", "Documents needed for a claim", "claims", ("documents required", "documents needed", "claim documents", "required documents")),
    ("claim_process", "How to claim", "claims", ("claim procedure", "claim process", "how to claim", "claims process")),
]


def detect_type(text: str) -> tuple[str, float]:
    t = text.lower()
    if "travel" in t and ("trip" in t or "overseas" in t or "journey" in t):
        return "travel", 0.7
    if re.search(r"\bterm (?:life|insurance|plan)\b", t) or ("death benefit" in t and "maturity" not in t):
        return "term_life", 0.75
    if any(k in t for k in ("endowment", "money back", "maturity benefit")):
        return "traditional_life", 0.75
    if any(k in t for k in ("hospitali", "mediclaim", "health insurance", "health policy", "in-patient", "cashless")):
        return "health", 0.8
    return "other", 0.3


def _members(secs, pages) -> tuple[list[dict], Fact | None]:
    sec = find_section(secs, "insured person", "insured member", "persons insured", "members covered", "life assured", "insured details")
    if not sec:
        return [], None
    members = []
    for raw in sec.lines:
        line = clean(raw)
        m = re.match(r"^(?:\d+[.)]\s*)?([A-Za-z][A-Za-z .']{1,40}?)\s*[|,\-–]\s*(self|spouse|wife|husband|son|daughter|father|mother|child|parent|father-in-law|mother-in-law)\s*[|,\-–]?\s*(?:age\s*[:\-]?\s*)?(\d{1,3})?", line, re.I)
        if m:
            members.append({"name": m.group(1).strip(), "relation": m.group(2).lower(), "age": int(m.group(3)) if m.group(3) else None})
    if not members:
        return [], None
    return members, Fact("people", "insured_members", "Insured members", members, sec.page, sec.heading,
                         snippet(" ; ".join(clean(x) for x in sec.lines[:4])), 0.7)


def extract_policy(pages: list[str]) -> Extraction:
    pages = strip_running_lines(pages)
    secs = sections(pages)
    facts: list[Fact] = []
    full = "\n".join(pages)

    for key, label, ftype, pattern, kind in LABELLED:
        hit = find_line(pages, re.compile(pattern, re.I))
        if not hit:
            continue
        m, pno, line = hit
        sec = section_for_page_line(secs, pno, line)
        if kind == "amount":
            value = to_amount(m.group(1), m.group(2) if m.lastindex and m.lastindex >= 2 else None)
            if value is None:
                continue
            facts.append(Fact(ftype, key, label, value, pno, sec, snippet(line), 0.85, "INR"))
        elif kind == "pct":
            raw = m.group(1).lower()
            value = 0.0 if raw in ("nil", "none") else float(raw.rstrip("% "))
            facts.append(Fact(ftype, key, label, value, pno, sec, snippet(line), 0.85, "%"))
        elif kind == "ref":
            facts.append(Fact(ftype, key, label, mask_ref(m.group(1)), pno, sec, snippet(line.replace(m.group(1), mask_ref(m.group(1)))), 0.85))
        elif kind == "email":
            if "claim" not in line.lower() and "email" not in line.lower():
                continue
            facts.append(Fact(ftype, key, label, m.group(1), pno, sec, snippet(line), 0.7))
        else:
            facts.append(Fact(ftype, key, label, clean(m.group(1)).rstrip("."), pno, sec, snippet(line), 0.8))

    # policy period
    hit = find_line(pages, re.compile(r"(?:policy period|period of insurance|period of cover)\s*[:\-]?\s*(?:from\s*)?" + _DATE + r"\s*(?:to|till|-|–)\s*" + _DATE, re.I))
    if hit:
        m, pno, line = hit
        start, end = parse_any_date(m.group(1)), parse_any_date(m.group(2))
        if start:
            facts.append(Fact("identity", "start_date", "Start date", start.isoformat(), pno, section_for_page_line(secs, pno, line), snippet(line), 0.85))
        if end:
            facts.append(Fact("identity", "end_date", "End / renewal date", end.isoformat(), pno, section_for_page_line(secs, pno, line), snippet(line), 0.85))
    else:
        for key, label, pat in (("start_date", "Start date", r"(?:start date|commencement date|inception date)\s*[:\-]\s*" + _DATE),
                                ("end_date", "End / renewal date", r"(?:end date|expiry date|renewal date|maturity date)\s*[:\-]\s*" + _DATE)):
            h = find_line(pages, re.compile(pat, re.I))
            if h and parse_any_date(h[0].group(1)):
                facts.append(Fact("identity", key, label, parse_any_date(h[0].group(1)).isoformat(), h[1], None, snippet(h[2]), 0.8))

    ptype, pconf = detect_type(full)
    first_line = next((clean(x) for x in pages[0].splitlines() if clean(x)), "")
    facts.append(Fact("identity", "policy_type", "Policy type", ptype, 1, None, snippet(first_line), pconf))

    members, mfact = _members(secs, pages)
    if mfact:
        facts.append(mfact)

    injection_pages: set[int] = set()
    for key, label, ftype, kws in SECTION_LISTS:
        sec = find_section(secs, *kws)
        if not sec:
            continue
        items = bullets(sec)
        flagged = [i for i in items if looks_like_injection(i)]
        items = [i for i in items if not looks_like_injection(i)]
        if flagged:
            injection_pages.add(sec.page)
        if not items:
            continue
        facts.append(Fact(ftype, key, label, items[:25], sec.page, sec.heading, snippet(items[0]), 0.7))

    warnings = []
    for pno, text in enumerate(pages, start=1):
        if looks_like_injection(text):
            injection_pages.add(pno)
    if injection_pages:
        warnings.append(
            "This document contains text addressed to AI assistants (page "
            + ", ".join(map(str, sorted(injection_pages)))
            + "). VITTRM treated it as document text only and did not act on it."
        )
    have = {f.key for f in facts}
    for needed, label in (("sum_insured", "sum insured"), ("premium", "premium"), ("exclusions", "exclusions"), ("claim_documents", "claim documents")):
        if needed not in have:
            warnings.append(f"The {label} wasn't found in this document.")
    return Extraction(facts=facts, chunks=chunk_pages(pages), warnings=warnings)
