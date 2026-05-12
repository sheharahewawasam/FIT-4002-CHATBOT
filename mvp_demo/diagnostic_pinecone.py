"""
diagnostic_pinecone.py  —  Pipeline debugger for the Pinecone RAG system
Run with:  python diagnostic_pinecone.py

Stages tested:
  1. Pinecone connectivity & index health
  2. Embedding sanity (correct dim, non-zero values)
  3. Raw vector search per query variant (what does each rewritten query retrieve?)
  4. Reranker scoring with visible reasoning per chunk
  5. Final summary — pinpoints which stage is likely causing wrong answers
"""

import os
import re
import hashlib
import requests
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv("secrets.env")

PINECONE_API_KEY    = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "fit4002-pinecone-index")

pc    = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

DIVIDER  = "=" * 70
DIVIDER2 = "-" * 50


# ── Helpers ────────────────────────────────────────────────────────────────

def get_embedding(text):
    url  = "http://localhost:11434/api/embed"
    data = {"model": "jina/jina-embeddings-v2-base-en", "input": text}
    r    = requests.post(url, json=data)
    r.raise_for_status()
    return r.json()["embeddings"][0]


def query_rewriter_hyde(query):
    system_prompt = (
        "You are a retrieval query expansion assistant for a superannuation chatbot knowledge base. "
        "Given a user question, correct any spelling or grammar. Then rewrite the question so it "
        "mentions specific technical terms, section headings, or strategies that would appear in "
        "the relevant documents ('Trust Deed', 'Establishment and Purpose', 'SIS Act'). "
        "But try not to randomly add those technical terms if you aren't sure that they are relevant. "
        "Output ONLY the single paragraph WHICH IS THE EXPANDED query, and NOTHING else."
    )
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": "qwen3",
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
        "stream": False,
        "options": {"temperature": 0.0},
    })
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def extract_keyphrase(query):
    prompt = (
        "Given a user question about a superannuation trust deed or SIS Act, "
        "output a short descriptive phrase or heading (2-6 words) that would very likely "
        "appear in the document's table of contents or as a section title. "
        "Output ONLY the phrase, nothing else.\n"
        f"Question: {query}\nPhrase:"
    )
    r = requests.post("http://localhost:11434/api/generate", json={
        "model": "qwen3",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    })
    r.raise_for_status()
    return r.json()["response"].strip()


def llm_score_with_reasoning(user_query, chunk_text):
    """Score a chunk and return (score, reasoning) so we can see WHY it passed or failed."""
    if len(chunk_text) > 1500:
        chunk_text = chunk_text[:1500] + "..."

    prompt = f"""You are evaluating if a document chunk ANSWERS the user's question.

Score from 0-10 where:
- 10 = Directly answers the specific question with relevant details
- 5-7 = Contains related information but doesn't directly answer
- 0-2 = Mentions keywords but provides no answer

Question: {user_query}

Document chunk:
{chunk_text}

Respond in this exact format:
SCORE: <number>
REASONING: <one sentence explaining why>"""

    r = requests.post("http://localhost:11434/api/generate", json={
        "model": "qwen3",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    })
    r.raise_for_status()
    text = r.json()["response"].strip()

    score_match     = re.search(r"SCORE:\s*(10|[0-9])", text)
    reasoning_match = re.search(r"REASONING:\s*(.+)", text, re.DOTALL)

    score     = float(score_match.group(1))     if score_match     else 0.0
    reasoning = reasoning_match.group(1).strip() if reasoning_match else text

    return score, reasoning


# ── Stage 1: Connectivity & index health ──────────────────────────────────

def stage1_index_health():
    print(f"\n{DIVIDER}")
    print("STAGE 1 — Pinecone connectivity & index health")
    print(DIVIDER)

    try:
        stats = index.describe_index_stats()
        print(f"Index name        : {PINECONE_INDEX_NAME}")
        print(f"Total vectors     : {stats['total_vector_count']}")
        print(f"Embedding dimension: {stats['dimension']}")

        if stats["total_vector_count"] == 0:
            print("⚠️  WARNING: Index is EMPTY — nothing has been ingested yet.")
            return False

        # Fetch one real vector to verify metadata fields are stored correctly.
        # Pinecone doesn't have a "get random" — we query with a zero vector as a dummy.
        test_embedding = get_embedding("test query")
        sample = index.query(
            vector=test_embedding,
            top_k=1,
            include_metadata=True,
        )

        if not sample["matches"]:
            print("⚠️  Query returned no matches.")
            return False

        hit      = sample["matches"][0]
        metadata = hit.get("metadata", {})

        print(f"\nSample vector ID  : {hit['id']}")
        print(f"Sample score      : {hit['score']:.4f}  (expected ~0 for zero-vector query)")
        print(f"Metadata fields   : {list(metadata.keys())}")

        # Check each expected field is present and non-empty
        expected_fields = ["text", "child_match_text", "source_url", "fund_name", "doc_type"]
        all_present = True
        for field in expected_fields:
            value   = metadata.get(field, "")
            status  = "✅" if value else "❌ MISSING"
            if not value:
                all_present = False
            print(f"  {field}: {status}")
            if value:
                preview = str(value)[:120]
                print(f"    → {preview}")

        if not all_present:
            print("\n⚠️  Some metadata fields are missing — ingestion may be incomplete.")

        print("\n✅ Stage 1 PASSED")
        return True

    except Exception as e:
        print(f"❌ Stage 1 FAILED: {e}")
        return False


# ── Stage 2: Query rewriting ───────────────────────────────────────────────

def stage2_query_rewriting(original_query):
    print(f"\n{DIVIDER}")
    print("STAGE 2 — Query rewriting")
    print(DIVIDER)
    print(f"Original query : {original_query}")

    try:
        hyde_rewrite = query_rewriter_hyde(original_query)
        keyphrase    = extract_keyphrase(original_query)

        print(f"\nHyDE rewrite   : {hyde_rewrite}")
        print(f"Keyphrase      : {keyphrase}")

        all_queries = [hyde_rewrite, keyphrase, original_query]

        print(f"\nAll query variants ({len(all_queries)} total):")
        for i, q in enumerate(all_queries, 1):
            print(f"  [{i}] {q}")

        # Sanity check: warn if HyDE rewrite is very long or contains unrelated terms
        if len(hyde_rewrite) > 500:
            print("\n⚠️  HyDE rewrite is very long — may be adding too much noise to retrieval.")

        print("\n✅ Stage 2 PASSED")
        return all_queries

    except Exception as e:
        print(f"❌ Stage 2 FAILED: {e}")
        return [original_query]


# ── Stage 3: Raw retrieval per query variant ──────────────────────────────

def stage3_raw_retrieval(all_queries):
    print(f"\n{DIVIDER}")
    print("STAGE 3 — Raw retrieval results per query variant")
    print(DIVIDER)

    all_hits = []
    seen_ids = set()

    for i, q in enumerate(all_queries, 1):
        print(f"\n--- Query variant [{i}]: {q[:80]}{'...' if len(q) > 80 else ''}")
        print(DIVIDER2)

        try:
            embedding = get_embedding(q)
            results   = index.query(
                vector=embedding,
                top_k=10,
                include_metadata=True,
            )
            hits = results.get("matches", [])

            if not hits:
                print("  ⚠️  No results returned for this query variant.")
                continue

            print(f"  Returned {len(hits)} hits")
            for j, hit in enumerate(hits, 1):
                metadata = hit.get("metadata", {})
                score    = hit["score"]
                # Show child_match_text preferentially — it's the precise matched chunk
                text     = metadata.get("child_match_text") or metadata.get("text", "")

                print(f"\n  Hit {j} | score={score:.4f} | source={metadata.get('source_url','?')} | fund={metadata.get('fund_name','?')}")
                print(f"  child_match_text : {metadata.get('child_match_text','')[:200].strip()}")
                print(f"  text (parent)    : {metadata.get('text','')[:200].strip()}")

                if hit["id"] not in seen_ids:
                    all_hits.append(hit)
                    seen_ids.add(hit["id"])

        except Exception as e:
            print(f"  ❌ Search failed for variant [{i}]: {e}")

    # Check if dedup is silently dropping useful results
    toc_filtered = 0
    deduped      = []
    seen_hashes  = set()
    for hit in all_hits:
        content   = hit.get("metadata", {}).get("text", "")
        if ".........." in content or "Table of Contents" in content:
            toc_filtered += 1
            continue
        h = hashlib.md5(content.encode()).hexdigest()
        if h not in seen_hashes:
            deduped.append(hit)
            seen_hashes.add(h)

    print(f"\n--- Deduplication summary ---")
    print(f"Total hits across all variants : {len(all_hits) + toc_filtered}")
    print(f"Filtered (ToC/dots)            : {toc_filtered}")
    print(f"Duplicates removed             : {len(all_hits) - len(deduped)}")
    print(f"Unique chunks passed forward   : {len(deduped)}")

    if len(deduped) == 0:
        print("❌ No chunks survived deduplication — nothing to rerank.")
    elif len(deduped) < 3:
        print("⚠️  Very few unique chunks — reranker has little to work with.")

    print(f"\n✅ Stage 3 complete — {len(deduped)} unique chunks ready for reranking")
    return deduped


# ── Stage 4: Reranker transparency ────────────────────────────────────────

def stage4_reranking(original_query, deduped_hits):
    print(f"\n{DIVIDER}")
    print("STAGE 4 — Reranker scoring (with reasoning)")
    print(DIVIDER)

    # Mirror the pipeline: only pass top 10 to reranker
    candidates = deduped_hits[:10]
    print(f"Scoring {len(candidates)} chunks (capped at 10 like the real pipeline)...\n")

    scored = []
    for i, hit in enumerate(candidates, 1):
        metadata   = hit.get("metadata", {})
        chunk_text = metadata.get("child_match_text") or metadata.get("text", "")
        source_url = metadata.get("source_url", "?")
        fund       = metadata.get("fund_name", "?")

        print(f"Chunk {i}/{len(candidates)} — {source_url} ({fund})")
        print(f"  Pinecone score : {hit['score']:.4f}")

        try:
            score, reasoning = llm_score_with_reasoning(original_query, chunk_text)
            print(f"  Rerank score   : {score}/10")
            print(f"  Reasoning      : {reasoning}")
            print(f"  Text preview   : {chunk_text[:250].strip()}")
        except Exception as e:
            print(f"  ❌ Scoring failed: {e}")
            score, reasoning = 0.0, "error"

        scored.append({"hit": hit, "score": score, "reasoning": reasoning})
        print()

    scored.sort(key=lambda x: x["score"], reverse=True)

    print(DIVIDER)
    print("FINAL RERANKED ORDER:")
    print(DIVIDER)
    for i, item in enumerate(scored, 1):
        meta = item["hit"].get("metadata", {})
        text = (meta.get("child_match_text") or meta.get("text", ""))[:150].strip()
        print(f"\nRank {i} | rerank={item['score']}/10 | pinecone={item['hit']['score']:.4f} | source={meta.get('source_url','?')}")
        print(f"  {text}")

    quality = [x for x in scored if x["score"] >= 4]
    print(f"\n{'✅' if quality else '❌'} {len(quality)}/{len(scored)} chunks passed quality threshold (score >= 4)")

    if not quality:
        print("\n⚠️  DIAGNOSIS: All chunks scored below 4.")
        print("   → Check Stage 3: do the retrieved chunks look visually relevant to your query?")
        print("   → If no:  retrieval is wrong — check HyDE rewrite in Stage 2")
        print("   → If yes: reranker is too strict — consider lowering threshold from 4 to 3")
        print("   → Also check: is child_match_text populated? Reranker uses it preferentially.")

    return scored


# ── Stage 5: Summary ───────────────────────────────────────────────────────

def stage5_summary(original_query, all_queries, deduped_hits, scored):
    print(f"\n{DIVIDER}")
    print("STAGE 5 — Diagnostic summary")
    print(DIVIDER)

    quality      = [x for x in scored if x["score"] >= 4]
    top_sources  = [x["hit"]["metadata"].get("source_url", "?") for x in scored[:3]]
    top_scores   = [x["score"] for x in scored[:3]]

    print(f"Original query        : {original_query}")
    print(f"Query variants        : {len(all_queries)}")
    print(f"Unique chunks after dedup : {len(deduped_hits)}")
    print(f"Chunks scored         : {len(scored)}")
    print(f"Passed rerank (≥4)    : {len(quality)}")
    print(f"Top 3 sources         : {top_sources}")
    print(f"Top 3 rerank scores   : {top_scores}")

    print("\n── Where is the pipeline likely failing? ──")

    if len(deduped_hits) == 0:
        print("❌ RETRIEVAL: Nothing came back from Pinecone at all.")
        print("   → Check PINECONE_INDEX_NAME in secrets.env")
        print("   → Confirm ingestion ran successfully (Stage 1 vector count)")
        print("   → Confirm embedding model matches what was used during ingestion")

    elif len(quality) == 0:
        print("❌ RERANKING: Chunks were retrieved but all scored below 4.")
        print("   → Look at Stage 3 output — do the chunks look relevant to you visually?")
        print("   → If yes: reranker prompt is too strict. Lower threshold to 3.")
        print("   → If no:  retrieval is pulling wrong content. Review HyDE output in Stage 2.")

    elif len(quality) < 2:
        print("⚠️  RERANKING: Only 1 chunk passed. Answer may be thin or incomplete.")
        print("   → Consider lowering threshold from 4 to 3 to allow more context.")

    else:
        print("✅ Pipeline looks healthy through reranking.")
        print("   → If the final answer is still wrong, the issue is likely in the system prompt")
        print("      or the LLM is ignoring context. Check get_chat_response() inputs.")


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # ── Change this to whichever query is giving wrong answers ──
    TEST_QUERY = "What is the basis for supervision of the SIS act?"

    print(f"\n{'#' * 70}")
    print(f"  PINECONE RAG PIPELINE DIAGNOSTIC")
    print(f"  Test query: {TEST_QUERY}")
    print(f"{'#' * 70}")

    ok = stage1_index_health()
    if not ok:
        print("\nAborting — fix index issues before continuing.")
        exit(1)

    all_queries  = stage2_query_rewriting(TEST_QUERY)
    deduped_hits = stage3_raw_retrieval(all_queries)
    scored       = stage4_reranking(TEST_QUERY, deduped_hits)
    stage5_summary(TEST_QUERY, all_queries, deduped_hits, scored)