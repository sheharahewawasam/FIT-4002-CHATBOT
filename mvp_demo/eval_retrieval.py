"""
Retrieval recall harness.

Asks realistic adviser questions and checks whether the fact that answers them
actually reaches the model. Every expected value below was read by hand from the
source PDF, so these are ground truth rather than model output.

This is deliberately a script rather than a Django test: it needs the live
Pinecone index and loads the BGE models, so it is far too slow and too
network-dependent to sit in `manage.py test`.

    python eval_retrieval.py            # summary
    python eval_retrieval.py --verbose  # plus the top-ranked chunk per question

Run it before and after any change to chunking, ingestion or retrieval. A
chunking change can silently make a fifth of the corpus unreachable while every
unit test still passes - which is exactly what happened once already.
"""
import argparse
import hashlib
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from rag_api import resources  # noqa: E402
from rag_api import views as V  # noqa: E402


# (fund label, funds the asker can see, question, string that must reach the model)
CASES = [
    # Trust_Deed_Sample_Superannuation_Fund.pdf, Schedule 3
    ("Sample",  ["Sample Superannuation Fund", "General"],
     "What is the deed date for this fund?", "09/10/2020"),
    ("Sample",  ["Sample Superannuation Fund", "General"],
     "What is the ACN of the trustee?", "123 456 789"),
    ("Sample",  ["Sample Superannuation Fund", "General"],
     "Who is the trustee of the fund?", "Sample Company Pty Ltd"),

    # deed.pdf, execution schedule
    ("Summers", ["Summers Family Super Fund", "General"],
     "What is the deed date for this fund?", "21 January 2012"),
    ("Summers", ["Summers Family Super Fund", "General"],
     "Who are the trustees of the fund?", "John Summers"),
    ("Summers", ["Summers Family Super Fund", "General"],
     "What is the address of the trustees?", "9 Summers Road"),

    # sample-smsf-trust-deed.pdf, Schedule to this deed
    ("Ausis",   ["Ausis Super Fund", "General"],
     "What is the deed date for this fund?", "27 May 2022"),
    ("Ausis",   ["Ausis Super Fund", "General"],
     "What is the ACN of the trustee?", "600790154"),
    ("Ausis",   ["Ausis Super Fund", "General"],
     "Who are the members of the fund?", "Peter Parker"),
    ("Ausis",   ["Ausis Super Fund", "General"],
     "Who established the fund?", "James Parker"),
]

TOP_K_SEARCH = 60
TOP_K_CONTEXT = 5


def retrieve(question, funds):
    """Mirror what chat_with_advisor_bot does, up to the point of calling the LLM."""
    embedding = resources.embedder.encode(resources.QUERY_PREFIX + question).tolist()
    access_filter = V.build_access_filter(funds, None)
    raw = V.perform_vector_search(embedding, question, access_filter, top_k=TOP_K_SEARCH)

    best = {}
    for res in raw:
        meta = res.get("metadata", {})
        content = meta.get("text", "") or meta.get("child_match_text", "")
        if ".........." in content or "Table of Contents" in content:
            continue
        digest = hashlib.md5(content.encode()).hexdigest()
        score = res.get("score", 0)
        if digest not in best or score > best[digest][0]:
            best[digest] = (score, res)

    reranked = V.rerank(question, [r for _, r in best.values()], top_k=TOP_K_CONTEXT)
    context = " ".join((i["result"]["metadata"].get("text", "") or "") for i in reranked)
    candidates = " ".join((r["metadata"].get("text", "") or "") for r in raw)
    return context, candidates, reranked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    print()
    print(f"  {'fund':9} {'question':40} {'top-5':>7} {'top-60':>8}")
    print("  " + "-" * 70)

    in_context = in_candidates = 0
    failures = []
    for fund, funds, question, expected in CASES:
        context, candidates, reranked = retrieve(question, funds)
        reached = expected in context
        retrieved = expected in candidates
        in_context += reached
        in_candidates += retrieved
        if not reached:
            failures.append((fund, question, expected, retrieved))
        print(f"  {fund:9} {question[:40]:40} "
              f"{('PASS' if reached else 'fail'):>7} {('yes' if retrieved else 'NO'):>8}")
        if args.verbose and reranked:
            meta = reranked[0]["result"]["metadata"]
            snippet = (meta.get("child_match_text") or meta.get("text", ""))[:110]
            print(f"            top hit: {meta.get('source_url')} :: {snippet!r}")

    total = len(CASES)
    print()
    print(f"  recall@{TOP_K_CONTEXT}  (reached the model)  : {in_context}/{total}")
    print(f"  recall@{TOP_K_SEARCH} (retrieved at all)   : {in_candidates}/{total}")

    if failures:
        print()
        print("  failures:")
        for fund, question, expected, retrieved in failures:
            why = ("ranked below the top 5, but in the candidate pool"
                   if retrieved else
                   "not in the top-60 candidate pool for this phrasing")
            print(f"    {fund}: {question}")
            print(f"      expected {expected!r} - {why}")

    # Non-zero exit so this can gate a pipeline later.
    return 0 if in_context == total else 1


if __name__ == "__main__":
    sys.exit(main())
