"""Scoped retrieval over a user's documents (RD §10.3).

Keyword (BM25-style) scoring over page-level chunks and extracted facts. The
scope is always the user's own documents, and a specific document first when
one is given. Returns `found: False` rather than guessing.
"""

import math
import re
from collections import Counter

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, DocumentChunk, DocumentFact

_STOP = set(
    "a an the is are was were be been of to in on for and or with my me i we you it this that what which how when "
    "do does did can could will would should about any there their from by as at if not no mera meri mere kya hai "
    "ka ki ke ko se me mein aur ya kaise kab kitna kitni batao bata".split()
)

# small bilingual synonym map so Hinglish queries reach English policy text
_SYN = {
    "hospital": ["hospitalisation", "hospitalization", "inpatient", "in-patient"],
    "admit": ["hospitalisation", "admission"],
    "exclusion": ["excluded", "exclusions", "not covered"],
    "excluded": ["exclusion", "exclusions", "not covered"],
    "waiting": ["waiting period"],
    "claim": ["claims", "claim procedure"],
    "documents": ["document", "documents required"],
    "kagaz": ["documents"],
    "cashless": ["cashless", "network hospital"],
    "prepay": ["prepayment", "part-prepayment", "foreclosure"],
    "prepayment": ["part-prepayment", "foreclosure"],
    "foreclose": ["foreclosure"],
    "late": ["penal", "late payment", "overdue"],
    "penalty": ["penal", "late payment"],
    "fee": ["charges", "fees"],
    "charges": ["fee", "fees"],
    "maternity": ["maternity", "pregnancy", "childbirth"],
    "room": ["room rent"],
    "copay": ["co-payment", "copayment"],
    # --- everyday wording -> the labels these documents use (insurance)
    "expire": ["end date", "renewal date"], "expiry": ["end date", "renewal date"], "renew": ["renewal date", "end date"],
    "renewal": ["end date", "renewal date"], "valid": ["end date", "renewal date"], "validity": ["end date", "renewal date"],
    "till": ["end date"], "run": ["end date"],
    "cover": ["sum insured", "benefits"], "payout": ["sum insured", "death benefit"], "maximum": ["sum insured"],
    "assured": ["sum insured"], "insured": ["sum insured"],
    "yearly": ["premium annual"], "monthly": ["premium monthly"], "instalment": ["emi"], "installment": ["emi"],
    "mother": ["senior care", "mother"], "mummy": ["senior care", "mother"], "mom": ["senior care", "mother"],
    "parent": ["senior care"], "senior": ["senior care"],
    "floater": ["family health shield", "family health"], "term": ["term secure", "term life"],
    "die": ["death benefit", "nominee", "term life"], "death": ["death benefit", "nominee"], "nominee": ["death benefit", "term life"],
    "existing": ["pre-existing disease", "waiting period"], "already": ["pre-existing disease", "waiting period"],
    "pehle": ["pre-existing disease", "prepayment"], "purani": ["pre-existing disease"], "bimari": ["pre-existing disease", "illness"],
    "share": ["co-payment"], "part": ["co-payment", "part-prepayment"],
    "pay": ["premium", "claim"], "cheque": ["bounce charge", "dishonoured"], "auto-debit": ["bounce charge", "dishonoured"],
    "bounce": ["bounce charge", "dishonoured"], "dishonour": ["bounce charge", "dishonoured"],
    "interest": ["interest rate"], "byaaj": ["interest rate"], "rate": ["interest rate"],
    "early": ["foreclosure", "prepayment"], "close": ["foreclosure"], "closure": ["foreclosure"],
    "upfront": ["processing fee", "cashless"], "without": ["cashless"], "myself": ["reimbursement"], "refund": ["reimbursement"],
    "call": ["helpline"], "phone": ["helpline"], "number": ["helpline"], "contact": ["helpline"],
    "admitted": ["hospitalisation", "claim"], "admission": ["hospitalisation"],
    "inform": ["claim intimation"], "notify": ["claim intimation"], "intimate": ["claim intimation"],
    "paperwork": ["documents"], "kagaz": ["documents"], "papers": ["documents"],
    "private": ["room rent limit"], "ac": ["room rent limit"],
    "surgery": ["conditions", "limited"], "limit": ["sub-limit", "limited"], "cap": ["limited", "sub-limit"],
    "nahi": ["exclusions", "not covered"], "excluded": ["exclusions"],
}


def _stem(tok: str) -> str:
    """Strip a plural 's' so "periods" matches "period" (deliberately minimal; no 'ies'/'ing' rules)."""
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss") else tok


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9\-]+", text.lower())
    return [_stem(t) for t in toks if t not in _STOP and len(t) > 1]


_SYN = {_stem(k): v for k, v in _SYN.items()}
LABEL_BOOST = 2.0  # a query that names a field ("waiting period") should find that field first


def _expand(tokens: list[str]) -> list[str]:
    out = list(tokens)
    for t in tokens:
        for s in _SYN.get(t, []):
            out.extend(tokenize(s))
    return out


def _bm25(query: list[str], docs: list[list[str]], k1: float = 1.4, b: float = 0.75) -> list[float]:
    n = len(docs)
    if n == 0:
        return []
    avg = sum(len(d) for d in docs) / n or 1
    df = Counter()
    for d in docs:
        df.update(set(d))
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for q in set(query):
            if q not in tf:
                continue
            idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
            s += idf * tf[q] * (k1 + 1) / (tf[q] + k1 * (1 - b + b * len(d) / avg))
        scores.append(s)
    return scores


# --- hybrid ranking ----------------------------------------------------------------------------------------------------------------
# BM25 needs a shared word. Character trigrams share *fragments* ("hospitalis" ~ "hospitalised", "prepay" ~ "prepayment", a typo'd
# "waitng"), so cosine over TF-IDF trigram vectors catches what BM25 misses. The two rankings are merged with reciprocal rank fusion, which
# needs no score calibration between them. No model, no network, no new dependency.
NGRAM = 3
RRF_K = 60
MIN_COSINE = 0.3    # below this a trigram match alone is not evidence (swept on the dev half of the golden set, see evals/)
COS_WEIGHT = 0.3    # weight of the trigram ranking in the fusion (same sweep)


def _grams(text: str) -> Counter:
    out: Counter = Counter()
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in _STOP or len(w) < 2:
            continue
        w = f" {w} "
        out.update(w[i:i + NGRAM] for i in range(len(w) - NGRAM + 1))
    return out


def _cosines(query: str, texts: list[str]) -> list[float]:
    docs = [_grams(t) for t in texts]
    n = len(docs)
    if not n:
        return []
    df: Counter = Counter()
    for d in docs:
        df.update(d.keys())
    idf = {g: math.log(1 + n / c) for g, c in df.items()}

    def vec(c: Counter) -> dict[str, float]:
        v = {g: (1 + math.log(tf)) * idf.get(g, math.log(1 + n)) for g, tf in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / norm for g, x in v.items()}

    q = vec(_grams(query))
    out = []
    for d in docs:
        dv = vec(d)
        out.append(sum(w * dv.get(g, 0.0) for g, w in q.items()))
    return out


def _fuse(bm25: list[float], cos: list[float]) -> list[float]:
    """Reciprocal rank fusion of the two rankings; items neither ranker supports score 0."""
    def ranks(scores: list[float], floor: float) -> dict[int, int]:
        order = sorted((i for i, sc in enumerate(scores) if sc > floor), key=lambda i: -scores[i])
        return {i: r for r, i in enumerate(order, 1)}

    rb, rc = ranks(bm25, 0.0), ranks(cos, MIN_COSINE)
    return [(1 / (RRF_K + rb[i]) if i in rb else 0.0) + COS_WEIGHT * (1 / (RRF_K + rc[i]) if i in rc else 0.0) for i in range(len(bm25))]


def search(db: Session, user_id: str, query: str, document_ids: list[str] | None = None,
           doc_types: list[str] | None = None, limit: int = 4, mode: str | None = None) -> dict:
    q = _expand(tokenize(query))
    docs_q = db.query(Document).filter(Document.owner_user_id == user_id, Document.processing_status.in_(["ready", "needs_review"]))
    if document_ids:
        docs_q = docs_q.filter(Document.id.in_(document_ids))
    if doc_types:
        docs_q = docs_q.filter(Document.type.in_(doc_types))
    docs = {d.id: d for d in docs_q.all()}
    if not docs or not q:
        return {"found": False, "results": [], "query": query, "scope": list(docs)}

    chunks = db.query(DocumentChunk).filter(DocumentChunk.user_id == user_id, DocumentChunk.document_id.in_(docs)).all()
    facts = (
        db.query(DocumentFact)
        .filter(DocumentFact.user_id == user_id, DocumentFact.document_id.in_(docs), DocumentFact.key != "_terms")
        .all()
    )
    # Words in the file name ("senior care") let a question name the document it is about.
    name_tokens = {i: tokenize(re.sub(r"[_.]", " ", d.display_name.rsplit(".", 1)[0])) for i, d in docs.items()}
    items = []
    for c in chunks:
        items.append(("chunk", c, tokenize(f"{c.section or ''} {c.text}") + name_tokens[c.document_id]))
    for f in facts:
        val = f.value if isinstance(f.value, str) else " ".join(map(str, f.value)) if isinstance(f.value, list) else str(f.value)
        items.append(("fact", f, tokenize(f"{f.label} {f.section or ''} {val} {f.snippet or ''}") + name_tokens[f.document_id]))
    scores = _bm25(q, [t for _, _, t in items])
    qset = set(q)
    for i, (kind, obj, _) in enumerate(items):
        if kind == "fact":  # boost facts whose *label* the question mentions
            label = set(tokenize(obj.label))
            if label:
                scores[i] *= 1 + LABEL_BOOST * len(label & qset) / len(label)
    if (mode or get_settings().retrieval_mode) == "hybrid":
        texts = [" ".join(t) for _, _, t in items]
        scores = _fuse(scores, _cosines(" ".join(tokenize(query)), texts))
    ranked = sorted(zip(scores, items), key=lambda x: -x[0])
    results = []
    seen = set()
    top = ranked[0][0] if ranked else 0
    for score, (kind, obj, _) in ranked:
        if score <= 0 or score < top * 0.35:
            break
        d = docs[obj.document_id]
        if kind == "chunk":
            key = (obj.document_id, obj.page, obj.text[:40])
            text = obj.text
            page, section = obj.page, obj.section
            fact_key, verified, conf = None, False, None
        else:
            key = (obj.document_id, obj.page, obj.key)
            text = obj.snippet or str(obj.value)
            page, section = obj.page, obj.section
            fact_key, verified, conf = obj.key, obj.user_verified, obj.confidence
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "kind": kind,
            "score": round(score, 3),
            "text": text[:600],
            "fact": {"key": obj.key, "label": obj.label, "value": obj.value} if kind == "fact" else None,
            "citation": {
                "document_id": d.id, "document_type": d.type, "document_name": d.display_name,
                "page": page, "section": section, "snippet": (text[:220] + "…") if len(text) > 220 else text,
                "fact_key": fact_key, "confidence": conf, "user_verified": verified,
            },
        })
        if len(results) >= limit:
            break
    return {"found": bool(results), "results": results, "query": query, "scope": list(docs)}
