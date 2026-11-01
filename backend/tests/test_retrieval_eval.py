"""Retrieval quality gate: the golden set (evals/retrieval_golden.json) must not regress below these floors.

The floors sit a little under the measured numbers (see docs/RETRIEVAL_EVAL.md) so ordinary changes pass and a real loss of quality fails.
Only the held-out half is gated: the dev half was used to choose the synonym list, so it would flatter the result.
"""

import json

import pytest

from evals import retrieval_eval as ev
from tests.conftest import signup  # noqa: F401  (ensures the app/test environment is initialised)


@pytest.fixture(scope="module")
def workspace(sample):
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    uid = db.query(User).filter(User.is_sample.is_(True)).order_by(User.created_at.desc()).first().id
    yield db, uid
    db.close()


@pytest.mark.parametrize("mode", ["bm25", "hybrid"])
def test_heldout_quality_floor(workspace, mode):
    db, uid = workspace
    golden = ev.split(json.loads(ev.GOLDEN.read_text()), "heldout")
    r = ev.evaluate(db, uid, mode, golden)
    assert r["recall@3"] >= 0.80, f"{mode} recall@3 {r['recall@3']:.1%}"
    assert r["mrr"] >= 0.70, f"{mode} MRR {r['mrr']:.3f}"
    assert r["abstain"] >= 0.80, f"{mode} abstains on only {r['abstain']:.0%} of unanswerable questions"
    direct = r["by_kind"]["direct"]
    assert direct["recall@3"] >= 0.90, "questions that name the field must almost always find it"


def test_the_assistant_scope_is_the_users_own_documents(workspace):
    from app.services import retrieval

    db, uid = workspace
    assert retrieval.search(db, "someone-else", "sum insured")["found"] is False
