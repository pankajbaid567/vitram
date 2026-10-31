"""Loan document extraction — KFS, sanction letter, agreement (RD §10.2, §12.9).

Produces facts with provenance plus a `terms` dict shaped like a catalogue
product so the same Real Cost / what-if engine runs on it. Clauses are
labelled with RD §12.7 severity; "hidden" means overlooked, never invented.
"""

import re

from app.services.extractors.common import (
    AMOUNT,
    Extraction,
    Fact,
    chunk_pages,
    clean,
    find_line,
    parse_any_date,
    section_for_page_line,
    sections,
    strip_running_lines,
    snippet,
    to_amount,
)

PCT = r"(\d{1,2}(?:\.\d{1,2})?)\s*%"


def _find(pages, secs, pattern):
    hit = find_line(pages, re.compile(pattern, re.I))
    if not hit:
        return None
    m, pno, line = hit
    return m, pno, line, section_for_page_line(secs, pno, line)


def _fee(pages, secs, key, label, pattern, facts, charges, gst_default=True, mandatory=True):
    """A fee may be stated as a % of the loan, a flat amount, or both (min)."""
    hit = _find(pages, secs, pattern + r"\s*[:\-]\s*(.+)$")
    if not hit:
        return
    m, pno, line, sec = hit
    body = m.group(m.lastindex)
    spec = {"key": key, "label": label, "gst_applicable": gst_default and "incl" not in body.lower(),
            "mandatory": mandatory, "source": {"page": pno, "snippet": snippet(line)}}
    if re.search(r"\bnil\b|not applicable|\bn\.?a\.?\b|waived", body, re.I):
        spec.update(basis="flat", value=0.0)
        value = "Nil"
    else:
        pm = re.search(PCT, body)
        am = re.search(AMOUNT, body.replace("%", " "), re.I) if not pm else None
        if pm:
            spec.update(basis="percent_of_principal", value=float(pm.group(1)))
            mn = re.search(r"(?:min(?:imum)?\.?\s*(?:of)?\s*)" + AMOUNT, body, re.I)
            if mn:
                spec["min"] = to_amount(mn.group(1), mn.group(2))
            mx = re.search(r"(?:max(?:imum)?\.?\s*(?:of)?\s*)" + AMOUNT, body, re.I)
            if mx:
                spec["max"] = to_amount(mx.group(1), mx.group(2))
            value = f"{pm.group(1)}% of loan amount"
        elif am and to_amount(am.group(1), am.group(2)):
            spec.update(basis="flat", value=to_amount(am.group(1), am.group(2)))
            value = spec["value"]
        else:
            spec.update(basis="flat", value=None)
            value = clean(body)
    if "gst" in body.lower() and "incl" not in body.lower():
        spec["gst_applicable"] = True
    charges.append(spec)
    facts.append(Fact("fees", key, label, value, pno, sec, snippet(line), 0.8, "INR" if isinstance(value, float) else None))


def extract_loan(pages: list[str]) -> Extraction:
    pages = strip_running_lines(pages)
    secs = sections(pages)
    facts: list[Fact] = []
    charges: list[dict] = []
    contingent: list[dict] = []
    clauses: list[dict] = []
    terms: dict = {}

    def add(ftype, key, label, value, hit, conf=0.85, unit=None):
        _, pno, line, sec = hit
        facts.append(Fact(ftype, key, label, value, pno, sec, snippet(line), conf, unit))
        return {"page": pno, "snippet": snippet(line)}

    for key, label, pattern in (
        ("lender", "Lender", r"^(?:lender|name of (?:the )?(?:lender|regulated entity|bank|nbfc))\s*[:\-]\s*(.+)$"),
        ("product_name", "Loan product", r"^(?:loan product|product name|type of loan|loan type)\s*[:\-]\s*(.+)$"),
        ("collateral", "Security / collateral", r"^(?:security|collateral|security offered)\s*[:\-]\s*(.+)$"),
    ):
        h = _find(pages, secs, pattern)
        if h:
            terms[key] = clean(h[0].group(1)).rstrip(".")
            add("core" if key != "collateral" else "security", key, label, terms[key], h)

    h = _find(pages, secs, r"(?:loan amount|sanctioned amount|amount of loan|principal amount)\s*(?:\(.*?\))?\s*[:\-]\s*" + AMOUNT)
    if h:
        terms["principal"] = to_amount(h[0].group(1), h[0].group(2))
        add("core", "principal", "Loan amount", terms["principal"], h, unit="INR")

    h = _find(pages, secs, r"(?:rate of interest|interest rate|roi)\s*(?:\(.*?\))?\s*[:\-]\s*" + PCT)
    if h:
        terms["annual_rate_pct"] = float(h[0].group(1))
        add("core", "annual_rate_pct", "Interest rate (p.a.)", terms["annual_rate_pct"], h, unit="%")
        low = h[2].lower()
        if "floating" in low or "variable" in low:
            terms["rate_type"] = "floating"
        elif "fixed" in low:
            terms["rate_type"] = "fixed"
    h = _find(pages, secs, r"(?:type of interest|interest type|rate type)\s*[:\-]\s*(fixed|floating|variable)")
    if h:
        terms["rate_type"] = "floating" if h[0].group(1).lower() != "fixed" else "fixed"
        add("core", "rate_type", "Interest type", terms["rate_type"], h)
    elif "rate_type" in terms:
        pass

    h = _find(pages, secs, r"(?:benchmark|external benchmark|reference rate)\s*[:\-]\s*(.+)$")
    if h:
        add("core", "benchmark", "Benchmark / spread", clean(h[0].group(1)), h, conf=0.75)

    h = _find(pages, secs, r"(?:tenure|loan term|term of loan|repayment period)\s*[:\-]\s*(\d{1,3})\s*(months?|years?)")
    if h:
        n = int(h[0].group(1))
        terms["tenure_months"] = n * 12 if h[0].group(2).lower().startswith("year") else n
        add("core", "tenure_months", "Tenure (months)", terms["tenure_months"], h)

    h = _find(pages, secs, r"(?:\bemi\b|equated monthly instal?ment|instal?ment amount)\s*(?:amount)?\s*[:\-]\s*" + AMOUNT)
    if h:
        terms["stated_emi"] = to_amount(h[0].group(1), h[0].group(2))
        add("core", "stated_emi", "EMI stated in document", terms["stated_emi"], h, unit="INR")

    h = _find(pages, secs, r"(?:number of instal?ments|no\. of emis?)\s*[:\-]\s*(\d{1,3})")
    if h:
        add("repayment", "instalments", "Number of instalments", int(h[0].group(1)), h)
        terms.setdefault("tenure_months", int(h[0].group(1)))

    for key, label, pat in (("first_due_date", "First EMI date", r"(?:first emi|first instal?ment)\s*(?:date|due date)?\s*[:\-]\s*(.+)$"),
                            ("disbursement_date", "Disbursement date", r"disbursement date\s*[:\-]\s*(.+)$")):
        h = _find(pages, secs, pat)
        if h:
            d = parse_any_date(h[0].group(1))
            add("repayment", key, label, d.isoformat() if d else clean(h[0].group(1)), h)
            if key == "first_due_date" and d:
                terms["due_day"] = d.day

    h = _find(pages, secs, r"(?:annual percentage rate|\bapr\b)\s*(?:\(.*?\))?\s*[:\-]\s*" + PCT)
    if h:
        terms["stated_apr_pct"] = float(h[0].group(1))
        add("core", "stated_apr_pct", "APR stated by lender", terms["stated_apr_pct"], h, unit="%")

    _fee(pages, secs, "processing_fee", "Processing fee", r"(processing (?:fee|charges?)|origination fee)", facts, charges)
    _fee(pages, secs, "documentation", "Documentation charges", r"(documentation (?:fee|charges?))", facts, charges)
    _fee(pages, secs, "legal_valuation", "Legal / valuation charges", r"((?:legal|valuation|technical)[^:]{0,30}(?:fee|charges?))", facts, charges)
    _fee(pages, secs, "stamp_duty", "Stamp duty", r"(stamp duty)", facts, charges, gst_default=False)
    _fee(pages, secs, "credit_insurance", "Bundled loan insurance", r"((?:loan protection|credit (?:life|shield)|insurance premium)[^:]{0,30})", facts, charges, gst_default=False)

    # contingent
    h = _find(pages, secs, r"(?:penal charges?|late payment charges?|overdue charges?)\s*[:\-]\s*(.+)$")
    if h:
        body = h[0].group(1)
        rule: dict = {}
        pm = re.search(PCT + r"\s*(p\.?a\.?|per annum|p\.?m\.?|per month|a month)?", body, re.I)
        if pm:
            monthly = bool(pm.group(2)) and re.match(r"p\.?m|per month|a month", pm.group(2), re.I)
            rule["penal_rate_pa"] = float(pm.group(1)) * (12 if monthly else 1)
        am = re.search(AMOUNT, re.sub(PCT, " ", body), re.I)
        if am and to_amount(am.group(1), am.group(2)):
            rule["flat_fee"] = to_amount(am.group(1), am.group(2))
        if "gst" in body.lower():
            rule["gst_applicable"] = True
        src = add("late", "late_payment", "Late-payment / penal charges", clean(body), h)
        contingent.append({"key": "late_payment", "label": "Late-payment charges", "rule": rule or None, "source": src})
        clauses.append({"title": "Late-payment charges", "severity": "cost_impact", "text": clean(body), "source": src})
    h = _find(pages, secs, r"(?:bounce|dishonour)\w*\s*charges?\s*[:\-]\s*(.+)$")
    if h:
        am = re.search(AMOUNT, h[0].group(1), re.I)
        src = add("late", "bounce_charge", "EMI bounce charge", clean(h[0].group(1)), h)
        contingent.append({"key": "bounce", "label": "EMI bounce charge",
                           "rule": {"flat_fee": to_amount(am.group(1), am.group(2))} if am else None, "source": src})

    for key, label, pat in (("foreclosure", "Foreclosure charges", r"(?:foreclosure|pre-?closure)\s*charges?\s*[:\-]\s*(.+)$"),
                            ("part_prepayment", "Part-prepayment charges", r"part[- ]?(?:pre-?)?payment\s*charges?\s*[:\-]\s*(.+)$")):
        h = _find(pages, secs, pat)
        if not h:
            continue
        body = h[0].group(1)
        rule = {"allowed": not re.search(r"not (?:allowed|permitted)", body, re.I)}
        if re.search(r"\bnil\b|no charge", body, re.I):
            rule["charge_pct"] = 0.0
        pm = re.search(PCT, body)
        if pm:
            rule["charge_pct"] = float(pm.group(1))
        lock = re.search(r"after\s+(\d{1,2})\s*(?:emis?|months?|instal)", body, re.I)
        if lock:
            rule["allowed_after_months"] = int(lock.group(1))
        cap = re.search(r"up to\s+" + PCT, body, re.I)
        if cap:
            rule["max_per_year_pct"] = float(cap.group(1))
        if "gst" in body.lower():
            rule["gst_applicable"] = True
        src = add("clauses", key, label, clean(body), h)
        contingent.append({"key": key, "label": label, "rule": rule if "charge_pct" in rule or not rule["allowed"] else None, "source": src})
        if key == "part_prepayment":
            terms["prepayment_rule"] = rule if "charge_pct" in rule or not rule["allowed"] else None
        clauses.append({"title": label, "severity": "flexibility_impact" if rule.get("allowed_after_months") or not rule["allowed"] else "cost_impact",
                        "text": clean(body), "source": src})

    for title, severity, pat in (
        ("Interest rate can be reset", "cost_impact", r"(?:rate (?:reset|revision)|reset of interest|linked to .*benchmark).{0,200}"),
        ("Loan insurance is a condition", "important", r"(?:insurance|protection cover).{0,40}(?:mandatory|compulsory|condition of (?:the )?loan).{0,120}"),
        ("Fees are non-refundable", "cost_impact", r"(?:non-?refundable).{0,160}"),
        ("Conversion charges apply", "cost_impact", r"(?:conversion|switch(?:ing)?) (?:fee|charges?).{0,160}"),
        ("Collateral condition", "eligibility_condition", r"(?:lien|hypothecat|pledge|mortgage).{0,160}"),
    ):
        h = find_line(pages, re.compile(pat, re.I))
        if h:
            m, pno, line = h
            src = {"page": pno, "snippet": snippet(line)}
            clauses.append({"title": title, "severity": severity, "text": snippet(line), "source": src})
            facts.append(Fact("clauses", f"clause_{title.lower().replace(' ', '_')}", title, snippet(line), pno,
                              section_for_page_line(secs, pno, line), snippet(line), 0.65))

    terms["charges"] = charges
    terms["contingent"] = contingent
    terms["clauses"] = clauses
    facts.append(Fact("core", "_terms", "Structured terms", terms, None, None, None, 0.8))
    warnings = []
    from app.services.extractors.common import looks_like_injection
    inj = [str(i) for i, t in enumerate(pages, start=1) if looks_like_injection(t)]
    if inj:
        warnings.append(f"This document contains text addressed to AI assistants (page {', '.join(inj)}). "
                        "VITTRM treated it as document text only and did not act on it.")
    for k, label in (("principal", "loan amount"), ("annual_rate_pct", "interest rate"), ("tenure_months", "tenure")):
        if k not in terms:
            warnings.append(f"The {label} wasn't found in this document, so the Real Cost can't be fully calculated.")
    return Extraction(facts=facts, chunks=chunk_pages(pages), warnings=warnings)
