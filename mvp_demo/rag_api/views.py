import os
import re
import hashlib
import requests
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from django.http import JsonResponse
from rest_framework.decorators import api_view

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
COLLECTION_NAME = "triple_a_docs"

_chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
_collection = _chroma_client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
)

# Both models loaded once at startup — no Ollama HTTP calls for embedding or reranking
_embedder = SentenceTransformer("BAAI/bge-base-en-v1.5")
_embedder.max_seq_length = 512
_reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2", max_length=512)

# Simple in-memory cache keyed on normalised query string
_query_cache: dict = {}

_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL)

def strip_think_tags(text):
    return _THINK_RE.sub('', text).strip()


def perform_vector_search(query_embedding, top_k=40):
    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["metadatas", "distances"]
    )
    matches = []
    for vec_id, meta, dist in zip(results["ids"][0], results["metadatas"][0], results["distances"][0]):
        score = 1.0 - (dist / 2.0)
        matches.append({"id": vec_id, "score": score, "metadata": meta})
    return matches


def rerank(query, chunks, top_k=5):
    """Batch-score all chunks in one cross-encoder forward pass."""
    if not chunks:
        return []
    texts = [c.get("metadata", {}).get("text", "")[:2000] for c in chunks]
    pairs = [(query, t) for t in texts]
    scores = _reranker.predict(pairs, show_progress_bar=False)

    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)

    print("\n=== RERANKING RESULTS ===")
    for i, (score, chunk) in enumerate(ranked[:top_k]):
        print(f"\nRank {i+1}  CrossEncoder score: {score:.4f}")
        print(chunk.get("metadata", {}).get("text", "")[:200])

    return [{"result": c, "rerank_score": float(s)} for s, c in ranked[:top_k]]


def get_chat_response(system_prompt, user_query):
    url = "http://localhost:11434/api/chat"
    data = {
        "model": "qwen3",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,
            # 5 parent chunks × ~500 tokens each + system prompt overhead — 8192 avoids silent truncation
            "num_ctx": 8192
        }
    }
    response = requests.post(url, json=data, timeout=120)
    response.raise_for_status()
    return strip_think_tags(response.json()["message"]["content"])


@api_view(['POST'])
def chat_with_advisor_bot(request):
    user_query = request.data.get("query")

    if not user_query:
        return JsonResponse({"error": "Query is required"}, status=400)

    cache_key = user_query.strip().lower()
    if cache_key in _query_cache:
        print(f"Cache hit for: {cache_key}")
        return JsonResponse(_query_cache[cache_key])

    try:
        # BGE models require this prefix on queries (not on indexed documents)
        query_embedding = _embedder.encode(
            "Represent this sentence for searching relevant passages: " + user_query
        ).tolist()
        raw_results = perform_vector_search(query_embedding, top_k=40)

        # 2. Deduplicate — keep highest-scoring copy of each unique chunk
        best_by_hash = {}
        for res in raw_results:
            content = res.get("metadata", {}).get("text", "")
            if ".........." in content or "Table of Contents" in content:
                continue
            text_hash = hashlib.md5(content.encode()).hexdigest()
            score = res.get("score", 0)
            if text_hash not in best_by_hash or score > best_by_hash[text_hash][0]:
                best_by_hash[text_hash] = (score, res)

        deduped = [res for _, res in best_by_hash.values()]

        # 3. Batch-rerank all deduped chunks, keep top 5
        reranked = rerank(user_query, deduped, top_k=5)

        if not reranked:
            return JsonResponse({
                "answer": "I could not find any relevant information in the fund documents to answer your query.",
                "citations": []
            })

        # 4. Build context — cap each chunk at 1500 chars to stay within num_ctx=8192
        context_text = ""
        citations = []

        for i, item in enumerate(reranked):
            res = item["result"]
            metadata = res.get("metadata", {})
            chunk_text = metadata.get("text", "")[:1500]
            context_text += f"--- Document {i+1} ---\n{chunk_text}\n\n"
            citations.append({
                "source": metadata.get("source_url", "Unknown"),
                "fund": metadata.get("fund_name", "Unknown")
            })

        print("\n=== RETRIEVED CHUNKS ===")
        for i, item in enumerate(reranked):
            print(f"\nChunk {i+1}  score={item['rerank_score']:.4f}")
            print(item["result"].get("metadata", {}).get("text", "")[:500])
            print("=" * 50)

        # 5. Generate answer with Qwen3
        system_prompt = f"""
        You are an expert AI assistant for financial advisors at Triple A Super.
        Answer the user's query using ONLY the provided document context below.
        Do not use any outside knowledge — only what appears in the context.

        If the context contains relevant information, share ALL of it even if it is brief or partial.
        Do not refuse to answer just because the information is incomplete — report what is there.
        Only say "I cannot find information about this in the provided documents" if the context contains
        absolutely nothing related to the query.

        If the query asks about methods, techniques, strategies, or types:
        - enumerate ALL methods found in the context
        - do not omit any
        - use bullet points

        CONTEXT:
        {context_text}
        """

        answer = get_chat_response(system_prompt, user_query)

        result = {"answer": answer, "citations": citations}
        _query_cache[cache_key] = result
        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)