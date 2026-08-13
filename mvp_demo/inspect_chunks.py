"""
inspect_chunks.py

Quick diagnostic to sanity-check the parent-child chunking relationship
already stored in Pinecone, BEFORE deciding whether to change chunking
strategy.

What it checks, per sample vector:
  1. Does the leaf (child_match_text) look like a sensible small fragment,
     or a mid-sentence/mid-clause cut?
  2. Does the parent (text) actually CONTAIN the child text? (sanity check
     that parent/child were paired correctly during ingest)
  3. Is the parent meaningfully larger and more contextual than the child,
     or did it silently fall back to leaf.text (i.e. parent == child)?
  4. For a specific query (e.g. "basis for supervision"), which chunks
     actually get retrieved, and at what rank/score?

Run:
    python inspect_chunks.py                     # random sample inspection
    python inspect_chunks.py --query "basis for supervision"
    python inspect_chunks.py --doc-type "SIS Act" --sample 10
"""

import os
import argparse
import textwrap

from dotenv import load_dotenv
from pinecone import Pinecone
from pinecone_text.sparse import BM25Encoder
from sentence_transformers import SentenceTransformer

load_dotenv("secrets.env")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "fit4002-pinecone-index")
BM25_ENCODER_PATH = os.getenv("BM25_ENCODER_PATH", "bm25_encoder.json")

WRAP = 100


def wrap(text, prefix="    "):
    return "\n".join(
        textwrap.wrap(text or "", width=WRAP, initial_indent=prefix, subsequent_indent=prefix)
    )


def print_chunk_pair(match, idx=None, score=None):
    meta = match.get("metadata", {})
    parent_text = meta.get("text", "") or ""
    child_text = meta.get("child_match_text", "") or ""

    header = f"--- Vector id={match.get('id')} "
    if idx is not None:
        header += f"(rank {idx}) "
    if score is not None:
        header += f"score={score:.4f} "
    print(header + "-" * max(0, 100 - len(header)))
    print(f"  source: {meta.get('source_url')}  |  fund: {meta.get('fund_name')}  |  doc_type: {meta.get('doc_type')}")
    print()

    print(f"  [CHILD]  len={len(child_text)} chars")
    print(wrap(child_text[:600]))
    print()

    print(f"  [PARENT] len={len(parent_text)} chars")
    print(wrap(parent_text[:900]))
    print()

    # --- Sanity checks ---
    issues = []

    if not parent_text or not child_text:
        issues.append("MISSING parent or child text entirely.")
    else:
        if parent_text.strip() == child_text.strip():
            issues.append("Parent == Child (parent likely fell back to leaf.text — no real parent was found).")
        elif child_text.strip()[:80] not in parent_text:
            # loose containment check on the first chunk of the child text
            issues.append("Child text does NOT appear to be contained in parent text — "
                           "possible mismatch in parent/child pairing.")
        if len(parent_text) < len(child_text) * 1.2:
            issues.append("Parent is not meaningfully larger than child — hierarchy may not be adding context.")

    # crude mid-sentence cut check: does chunk start/end oddly?
    def looks_cut(t):
        if not t:
            return False
        t = t.strip()
        starts_lower = t[0].islower() if t[0].isalpha() else False
        ends_no_punct = t[-1] not in ".!?\":)"
        return starts_lower or ends_no_punct

    if looks_cut(child_text):
        issues.append("Child text looks like it may start/end mid-sentence (lowercase start or no closing punctuation).")

    if issues:
        print("  ⚠️  ISSUES FOUND:")
        for iss in issues:
            print(f"      - {iss}")
    else:
        print("  ✅ No obvious issues detected.")
    print()


def random_sample_inspection(index, sample_size, doc_type_filter=None):
    """
    Pinecone doesn't support a true 'random sample' natively, so we query
    with a neutral/generic vector and just look at whatever comes back —
    good enough for a spot check, not a statistical sample.
    """
    print(f"\n=== RANDOM-ISH SAMPLE INSPECTION (n={sample_size}) ===\n")

    embedder = SentenceTransformer("BAAI/bge-base-en-v1.5")
    # neutral-ish probe query just to pull back a spread of vectors
    probe_vec = embedder.encode("superannuation fund trust deed provisions").tolist()

    query_kwargs = dict(vector=probe_vec, top_k=sample_size, include_metadata=True)
    if doc_type_filter:
        query_kwargs["filter"] = {"doc_type": {"$eq": doc_type_filter}}

    results = index.query(**query_kwargs)
    matches = results.get("matches", [])

    if not matches:
        print("No vectors returned — check your index name / filter / that ingest has run.")
        return

    for i, m in enumerate(matches, start=1):
        print_chunk_pair(m, idx=i)


def query_inspection(index, query_text, top_k=10):
    print(f"\n=== RETRIEVAL INSPECTION FOR QUERY: \"{query_text}\" ===\n")

    embedder = SentenceTransformer("BAAI/bge-base-en-v1.5")
    embedder.max_seq_length = 512
    bm25 = BM25Encoder().load(BM25_ENCODER_PATH)

    query_embedding = embedder.encode(
        "Represent this sentence for searching relevant passages: " + query_text
    ).tolist()
    sparse_vector = bm25.encode_queries(query_text)

    results = index.query(
        vector=query_embedding,
        sparse_vector=sparse_vector,
        top_k=top_k,
        include_metadata=True,
    )
    matches = results.get("matches", [])

    if not matches:
        print("No matches returned for this query at all — retrieval-level miss.")
        return

    for i, m in enumerate(matches, start=1):
        print_chunk_pair(m, idx=i, score=m.get("score", 0.0))

    print(f"\nSummary: {len(matches)} matches returned for top_k={top_k}.")
    print("If you expected a specific known section (e.g. 'Basis for supervision')")
    print("and it's not shown above at all, that's a RETRIEVAL miss (not a chunking/prompt issue).")
    print("If it IS shown but ranked low or its child text looks cut off, that points to a CHUNKING issue.")


def main():
    parser = argparse.ArgumentParser(description="Inspect parent-child chunk quality in Pinecone.")
    parser.add_argument("--query", type=str, default=None,
                         help="Run a specific retrieval query and show ranked results.")
    parser.add_argument("--doc-type", type=str, default=None,
                         help="Filter random sample inspection to a specific doc_type metadata value.")
    parser.add_argument("--sample", type=int, default=8,
                         help="Number of chunks to inspect in random-sample mode.")
    parser.add_argument("--top-k", type=int, default=10,
                         help="Number of results to show in query mode.")
    args = parser.parse_args()

    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)

    if args.query:
        query_inspection(index, args.query, top_k=args.top_k)
    else:
        random_sample_inspection(index, args.sample, doc_type_filter=args.doc_type)


if __name__ == "__main__":
    main()