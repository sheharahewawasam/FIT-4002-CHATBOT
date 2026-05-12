"""
diagnostic.py  —  Pipeline debugger for the RAG system
Run with:  python diagnostic.py

Stages tested:
  1. OpenSearch connectivity & index health
  2. Embedding sanity (are stored vectors non-zero / correct dim?)
  3. Raw vector search per query variant (what does each rewritten query actually retrieve?)
  4. Hybrid search output (knn + keyword combined)
  5. Reranker scoring transparency (score each chunk and show reasoning)
"""

import os
import re
import json
import requests
import boto3
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

load_dotenv("secrets.env")

AWS_REGION       = os.getenv("AWS_REGION", "ap-southeast-2")
OPENSEARCH_HOST  = os.getenv("OPENSEARCH_HOST")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "fit4002-opensearch-index")

credentials = boto3.Session().get_credentials()
auth        = AWSV4SignerAuth(credentials, AWS_REGION, "es")

client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
)

DIVIDER  = "=" * 70
DIVIDER2 = "-" * 50

# ── helpers ────────────────────────────────────────────────────────────────

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
    url  = "http://localhost:11434/api/chat"
    data = {
        "model": "qwen3",
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
        "stream": False,
        "options": {"temperature": 0.0},
    }
    r = requests.post(url, json=data)
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
    """
    Ask the LLM to score a chunk AND explain its reasoning.
    Returns (score: float, reasoning: str)
    """
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
    response_text = r.json()["response"].strip()

    score_match     = re.search(r"SCORE:\s*(\d+)", response_text)
    reasoning_match = re.search(r"REASONING:\s*(.+)", response_text, re.DOTALL)

    score     = float(score_match.group(1))     if score_match     else 0.0
    reasoning = reasoning_match.group(1).strip() if reasoning_match else response_text

    return score, reasoning

# ── Stage 1: Connectivity & index health ──────────────────────────────────

def stage1_index_health():
    print(f"\n{DIVIDER}")
    print("STAGE 1 — OpenSearch connectivity & index health")
    print(DIVIDER)

    try:
        health = client.cluster.health(index=OPENSEARCH_INDEX)
        print(f"Cluster status : {health['status']}")
        print(f"Active shards  : {health['active_shards']}")

        stats = client.indices.stats(index=OPENSEARCH_INDEX)
        doc_count = stats["indices"][OPENSEARCH_INDEX]["primaries"]["docs"]["count"]
        print(f"Documents in index: {doc_count}")

        if doc_count == 0:
            print("⚠️  WARNING: Index is EMPTY — nothing has been ingested yet.")
            return False

        # Fetch one sample document to check its structure
        sample = client.search(
            index=OPENSEARCH_INDEX,
            body={"size": 1, "query": {"match_all": {}}},
        )
        hit    = sample["hits"]["hits"][0]["_source"]
        fields = list(hit.keys())
        print(f"\nSample document fields: {fields}")

        embedding = hit.get("embedding", [])
        print(f"Embedding dimension : {len(embedding)}")
        print(f"Embedding non-zero  : {any(v != 0 for v in embedding)}")

        # Show a snippet of stored metadata
        print(f"\nSample metadata:")
        for field in ["source_url", "fund_name", "doc_type"]:
            print(f"  {field}: {hit.get(field, 'MISSING ⚠️')}")
        print(f"  text (first 200 chars): {hit.get('text','')[:200]}")
        print(f"  child_match_text (first 200 chars): {hit.get('child_match_text','')[:200]}")

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

    all_hits  = []
    seen_ids  = set()

    for i, q in enumerate(all_queries, 1):
        print(f"\n--- Query variant [{i}]: {q[:80]}{'...' if len(q) > 80 else ''}")
        print(DIVIDER2)

        try:
            embedding   = get_embedding(q)
            search_body = {
                "size": 10,
                "query": {
                    "hybrid": {
                        "queries": [
                            {"knn": {"embedding": {"vector": embedding, "k": 10}}},
                            {
                                "multi_match": {
                                    "query": q,
                                    "fields": ["text", "child_match_text"]
                                }
                            }
                        ]
                    }
                },
                "_source": ["text", "child_match_text", "source_url", "fund_name", "doc_type"],
            }

            response = client.search(index=OPENSEARCH_INDEX, body=search_body)
            hits     = response["hits"]["hits"]

            if not hits:
                print("  ⚠️  No results returned for this query variant.")
                continue

            print(f"  Returned {len(hits)} hits")
            for j, hit in enumerate(hits, 1):
                src   = hit["_source"]
                score = hit["_score"]
                text  = src.get("child_match_text") or src.get("text", "")

                print(f"\n  Hit {j} | score={score:.4f} | source={src.get('source_url','?')} | fund={src.get('fund_name','?')}")
                print(f"  Text preview: {text[:300].strip()}")

                # Collect unique hits for stage 4
                if hit["_id"] not in seen_ids:
                    all_hits.append(hit)
                    seen_ids.add(hit["_id"])

        except Exception as e:
            print(f"  ❌ Search failed for variant [{i}]: {e}")

    print(f"\n✅ Stage 3 complete — {len(all_hits)} unique chunks retrieved across all variants")
    return all_hits

# ── Stage 4: Reranker transparency ────────────────────────────────────────

def stage4_reranking(original_query, all_hits):
    print(f"\n{DIVIDER}")
    print("STAGE 4 — Reranker scoring (with reasoning)")
    print(DIVIDER)
    print(f"Scoring {len(all_hits)} unique chunks...\n")

    scored = []
    for i, hit in enumerate(all_hits, 1):
        src        = hit["_source"]
        chunk_text = src.get("child_match_text") or src.get("text", "")
        source_url = src.get("source_url", "?")

        print(f"Chunk {i}/{len(all_hits)} — {source_url}")
        try:
            score, reasoning = llm_score_with_reasoning(original_query, chunk_text)
            print(f"  Score    : {score}/10")
            print(f"  Reasoning: {reasoning}")
            print(f"  Text     : {chunk_text[:200].strip()}")
        except Exception as e:
            print(f"  ❌ Scoring failed: {e}")
            score, reasoning = 0.0, "error"

        scored.append({
            "hit": hit, "score": score, "reasoning": reasoning
        })
        print()

    scored.sort(key=lambda x: x["score"], reverse=True)

    print(DIVIDER)
    print("RERANKING FINAL ORDER:")
    print(DIVIDER)
    for i, item in enumerate(scored, 1):
        src  = item["hit"]["_source"]
        text = (src.get("child_match_text") or src.get("text", ""))[:150].strip()
        print(f"\nRank {i} | score={item['score']}/10 | source={src.get('source_url','?')}")
        print(f"  {text}")

    quality = [x for x in scored if x["score"] >= 4]
    print(f"\n{'✅' if quality else '❌'} {len(quality)}/{len(scored)} chunks passed the quality threshold (score >= 4)")

    if not quality:
        print("\n⚠️  DIAGNOSIS: All chunks scored below 4.")
        print("   Possible causes:")
        print("   → Wrong chunks being retrieved (embedding/index issue)")
        print("   → Rewriter is drifting the query away from relevant content")
        print("   → Reranker LLM prompt is too strict — consider lowering threshold to 3")

    return scored

# ── Stage 5: Final summary ─────────────────────────────────────────────────

def stage5_summary(original_query, all_queries, all_hits, scored):
    print(f"\n{DIVIDER}")
    print("STAGE 5 — Diagnostic summary")
    print(DIVIDER)

    quality     = [x for x in scored if x["score"] >= 4]
    top_sources = [x["hit"]["_source"].get("source_url", "?") for x in scored[:3]]

    print(f"Original query       : {original_query}")
    print(f"Query variants       : {len(all_queries)}")
    print(f"Total unique chunks  : {len(all_hits)}")
    print(f"Passed rerank (≥4)   : {len(quality)}")
    print(f"Top 3 sources        : {top_sources}")

    print("\n── Where is the pipeline likely failing? ──")

    if len(all_hits) == 0:
        print("❌ RETRIEVAL: Nothing came back from OpenSearch at all.")
        print("   → Check index has documents (Stage 1)")
        print("   → Check embedding model matches what was used during ingestion")

    elif len(quality) == 0:
        print("❌ RERANKING: Chunks were retrieved but all scored below 4.")
        print("   → Review Stage 3 output — do the retrieved chunks look relevant to you visually?")
        print("   → If yes: reranker is too strict. Lower threshold or improve prompt.")
        print("   → If no: retrieval is returning wrong chunks. Check HyDE rewrite in Stage 2.")

    elif len(quality) < 3:
        print("⚠️  RERANKING: Only a few chunks passed. Answer may be incomplete.")
        print("   → Consider lowering threshold from 4 to 3")

    else:
        print("✅ Pipeline looks healthy up to reranking.")
        print("   → If answers are still wrong, check the system prompt passed to the final LLM.")


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # ── Change this to whichever query is giving wrong answers ──
    TEST_QUERY = "What is Discretion to register?"

    print(f"\n{'#' * 70}")
    print(f"  RAG PIPELINE DIAGNOSTIC")
    print(f"  Test query: {TEST_QUERY}")
    print(f"{'#' * 70}")

    ok = stage1_index_health()
    if not ok:
        print("\nAborting — fix index issues before continuing.")
        exit(1)

    all_queries = stage2_query_rewriting(TEST_QUERY)
    all_hits    = stage3_raw_retrieval(all_queries)
    scored      = stage4_reranking(TEST_QUERY, all_hits)
    stage5_summary(TEST_QUERY, all_queries, all_hits, scored)