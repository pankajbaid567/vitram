# Retrieval evaluation

Document questions ("what is my pre-existing disease waiting period?") are answered by `services/retrieval.py`, then the assistant narrates what was
found. If retrieval picks the wrong passage the answer is wrong however good the model is, so retrieval has its own measured quality bar.

## The golden set

`backend/evals/retrieval_golden.json`: **125 questions** over the five fictional sample documents (three insurance policies, a loan key-facts statement,
a bank statement), written the way people ask:

| Type | Count | Example |
|---|---|---|
| direct (names the field) | 50 | "What is the room rent limit in the family health policy?" |
| paraphrase (never uses the document's words) | 51 | "How long before existing illnesses get covered under the family floater?" |
| Hinglish | 12 | "mummy ki policy mein kitna copay lagta hai" |
| typo | 2 | "pre existng disease waitng period family health" |
| unanswerable (should return nothing) | 10 | "What is the price of gold today?" |

A question is a **hit at k** when one of the first k results is the expected *fact of the expected document*. Questions are searched across all five
documents, which is harder than the assistant's usual per-document scope. Odd ids are the **dev** half (what synonyms and thresholds were tuned
against); even ids are the **held-out** half, reported separately so tuning cannot flatter the headline number.

```bash
cd backend && uv run python -m evals.retrieval_eval                    # compare bm25 and hybrid
uv run python -m evals.retrieval_eval --mode bm25 --part heldout      # one mode, held-out half, lists the misses
```

`tests/test_retrieval_eval.py` fails CI if the held-out half drops below recall@3 80%, MRR 0.70 or abstention 80%.

## Results

| | recall@1 | recall@3 | recall@5 | MRR | abstains on unanswerable |
|---|---|---|---|---|---|
| BM25 as first measured (no domain synonyms) | 46.1% | 61.7% | 67.0% | 0.545 | 90% |
| **BM25 + domain synonym lexicon (current default)** | **66.1%** | **85.2%** | **87.8%** | **0.758** | **90%** |
| Hybrid (BM25 + trigram TF-IDF, rank-fused) | 62.6% | 87.0% | 89.6% | 0.743 | 90% |

Held-out half only (not used for tuning), BM25 + lexicon: recall@3 **87.7%**, MRR 0.782, abstention 100%. Dev half: 82.8% / 0.734 / 80%.

By question type (recall@3), BM25 before to after: paraphrase **33% to 73%**, Hinglish 58% to 83%, direct 92% to 100%.

## What the numbers say

- **The biggest win was vocabulary, not a fancier ranker.** Adding ~60 everyday-wording entries ("expire"/"valid" to *end date*, "mother's plan" to *senior
  care*, "share of the bill" to *co-payment*, "cheque bounces" to *bounce charge*) lifted recall@3 by 23.5 points and paraphrase recall from 33% to 73%.
  The corpus is small and in one domain, so a curated lexicon is the right tool.
- **Hybrid ranking is roughly a tie.** It gains a little recall@3/@5 and handles typos (50% to 100% on two questions), but its MRR is slightly lower, and
  it needed a threshold sweep to stop answering unanswerable questions (it first abstained only 40 to 60% of the time). Because the gain is within
  noise and it costs complexity, **BM25 stays the default** (`RETRIEVAL_MODE=bm25`); `hybrid` is there for corpora where typos matter.
- **Not done, deliberately:** dense embeddings. They need a model (an API call per chunk and per query, or a local model), which breaks the "documents
  never leave the device unless you opt in" promise for the default path. The `mode` seam in `search()` is where a pgvector or embedding ranker would be
  fused in; the golden set is what would show whether it earns its cost.
- **Known weak spots** (see the misses list): questions that need two facts at once, and multi-hop phrasing like "how many days after buying can I
  claim" (initial waiting period). They are listed rather than hidden.

## Assistant faithfulness

Separate from retrieval, the assistant can only narrate tool output: an amount in a reply that does not match a tool result to the paise is replaced
(`tests/test_saathi.py`, `tests/test_gemini_edges.py`); when retrieval returns `found: false` the assistant says it could not find it rather than guess;
instructions inside uploaded documents are treated as content (`tests/test_documents.py`, prompt-injection cases).
