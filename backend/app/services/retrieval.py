"""Scoped retrieval over a user's documents (RD §10.3).

Keyword (BM25-style) scoring over page-level chunks and extracted facts. The
scope is always the user's own documents, and a specific document first when
one is given. Returns `found: False` rather than guessing.
"""

import math
import re
from collections import Counter

from sqlalchemy.orm import Session

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
}


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9\-]+", text.lower())
    return [t for t in toks if t not in _STOP and len(t) > 1]


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


def search(db: Session, user_id: str, query: str, document_ids: list[str] | None = None,
           doc_types: list[str] | None = None, limit: int = 4) -> dict:
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
    items = []
    for c in chunks:
        items.append(("chunk", c, tokenize(f"{c.section or ''} {c.text}")))
    for f in facts:
        val = f.value if isinstance(f.value, str) else " ".join(map(str, f.value)) if isinstance(f.value, list) else str(f.value)
        items.append(("fact", f, tokenize(f"{f.label} {f.section or ''} {val} {f.snippet or ''}")))
    scores = _bm25(q, [t for _, _, t in items])
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
