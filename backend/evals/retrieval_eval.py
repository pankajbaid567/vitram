"""Retrieval quality on a golden set, measured on the sample workspace (fictional documents, so it is safe to publish).

    uv run python -m evals.retrieval_eval                 # compare bm25 and hybrid
    uv run python -m evals.retrieval_eval --mode hybrid   # one mode, with the misses listed

A question is a *hit at k* when one of the first k results is the expected fact of the expected document. Metrics: recall@1/3/5, MRR, and
for the unanswerable questions the *abstention rate* (the share that correctly return nothing instead of a confident wrong passage).
Questions are searched across ALL of the user's documents, which is harder than the assistant's usual per-document scope.
"""

import argparse
import json
import logging
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

GOLDEN = Path(__file__).with_name("retrieval_golden.json")


def _boot():
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/eval.db")
    for k, v in (("THROTTLE_ENABLED", "false"), ("RUN_SCHEDULER", "false"), ("APP_ORIGIN", "http://testserver"), ("CACHE_ENABLED", "false")):
        os.environ[k] = v
    logging.disable(logging.CRITICAL)


def build_workspace():
    """A sample workspace (five fictional documents) and its owner's id."""
    from fastapi.testclient import TestClient

    from app.db import SessionLocal
    from app.main import app
    from app.models import User

    client = TestClient(app)
    client.__enter__()
    client.headers["Origin"] = "http://testserver"
    assert client.post("/api/demo/workspace").status_code == 200
    db = SessionLocal()
    return db, db.query(User).filter(User.is_sample.is_(True)).first().id


def hit_rank(results: list[dict], doc: str, fact: str) -> int | None:
    for rank, r in enumerate(results, 1):
        c = r["citation"]
        if doc in c["document_name"] and c.get("fact_key") == fact:
            return rank
    return None


def split(golden: list[dict], part: str) -> list[dict]:
    """Odd ids are the *dev* half (what the synonym list and thresholds were tuned against); even ids are *held-out*."""
    return [g for g in golden if part == "all" or (g["id"] % 2 == 1) == (part == "dev")]


def evaluate(db, user_id: str, mode: str, golden: list[dict]) -> dict:
    from app.services import retrieval

    answerable = [g for g in golden if g["kind"] != "unanswerable"]
    ranks, misses = [], []
    by_kind: dict[str, list[int | None]] = defaultdict(list)
    for g in answerable:
        res = retrieval.search(db, user_id, g["q"], limit=5, mode=mode)["results"]
        rank = hit_rank(res, g["doc"], g["fact"])
        ranks.append(rank)
        by_kind[g["kind"]].append(rank)
        if rank is None or rank > 3:
            misses.append({**g, "rank": rank, "top": [f"{r['citation']['document_name'][:22]}:{r['citation'].get('fact_key') or 'chunk'}" for r in res[:3]]})

    def recall(rs, k):
        return sum(1 for r in rs if r is not None and r <= k) / len(rs) if rs else 0.0

    def mrr(rs):
        return sum(1 / r for r in rs if r) / len(rs) if rs else 0.0

    abstained = sum(1 for g in golden if g["kind"] == "unanswerable"
                    and not retrieval.search(db, user_id, g["q"], limit=5, mode=mode)["found"])
    n_un = sum(1 for g in golden if g["kind"] == "unanswerable")
    return {
        "mode": mode, "answerable": len(answerable),
        "recall@1": recall(ranks, 1), "recall@3": recall(ranks, 3), "recall@5": recall(ranks, 5), "mrr": mrr(ranks),
        "abstain": abstained / n_un if n_un else 0.0, "unanswerable": n_un,
        "by_kind": {k: {"n": len(v), "recall@3": recall(v, 3), "mrr": mrr(v)} for k, v in by_kind.items()}, "misses": misses,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["bm25", "hybrid"], help="evaluate one mode and list its misses (default: compare both)")
    ap.add_argument("--part", choices=["all", "dev", "heldout"], default="all", help="dev = odd ids (tuned on), heldout = even ids")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    _boot()
    golden = split(json.loads(GOLDEN.read_text()), args.part)
    db, uid = build_workspace()
    modes = [args.mode] if args.mode else ["bm25", "hybrid"]
    out = [evaluate(db, uid, m, golden) for m in modes]
    if args.json:
        print(json.dumps(out, indent=1))
        return 0
    print(f"{len(golden)} questions ({out[0]['answerable']} answerable, {out[0]['unanswerable']} unanswerable)\n")
    print(f"{'mode':8} {'R@1':>6} {'R@3':>6} {'R@5':>6} {'MRR':>6} {'abstain':>8}")
    for r in out:
        print(f"{r['mode']:8} {r['recall@1']:6.1%} {r['recall@3']:6.1%} {r['recall@5']:6.1%} {r['mrr']:6.3f} {r['abstain']:8.0%}")
    print("\nrecall@3 by question type")
    for r in out:
        print(f"  {r['mode']:8}", "  ".join(f"{k} {v['recall@3']:.0%} (n={v['n']})" for k, v in sorted(r["by_kind"].items())))
    if args.mode:
        print("\nmisses (rank>3 or none):")
        for m in out[0]["misses"]:
            print(f"  [{m['kind']}] {m['q']}\n      want {m['doc'][-18:]}:{m['fact']}  rank={m['rank']}  got {m['top']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
