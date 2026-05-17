import os
import re
import hashlib
import requests
import boto3
 
from django.http import JsonResponse
from rest_framework.decorators import api_view
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
from sentence_transformers import SentenceTransformer, CrossEncoder

load_dotenv("secrets.env")

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "fit4002-opensearch-index")

credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, AWS_REGION, "es")

client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)

_embedder = SentenceTransformer("BAAI/bge-base-en-v1.5")
_embedder.max_seq_length = 512
_reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2", max_length=512)

_query_cache: dict = {}

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

def strip_think_tags(text: str) -> str:
    return _THINK_RE.sub("", text).strip()

def perform_vector_search(query_embedding, user_query, top_k=40):
    # Build search request
    search_body = {
        "size": top_k,
        "query": {
            "hybrid": { # combine both keyword search and semantic search
                "queries": [
                    # Semantic search
                    {
                        "knn": {
                            "embedding": {
                                "vector": query_embedding, # user query embedding 
                                "k": top_k
                            }
                        }
                    },
                    # Keyword search
                    {
                        "multi_match": {
                            "query": user_query, # raw user input
                            "fields": ["text", "child_match_text"]
                        }
                    }
                ]
            }
        }
    }
    
    response = client.search(
        index=OPENSEARCH_INDEX,
        body=search_body,
        params={"search_pipeline": "hybrid-search-pipeline"}
    )
    return response["hits"]["hits"]

def rerank(query, chunks, top_k=5):
    """
    Batch-score all chunks in ONE CrossEncoder forward pass.
    Replaces the old approach of one Ollama LLM call per chunk.
    """
    if not chunks:
        return []
 
    texts = [
        c.get("_source", {}).get("child_match_text", "")
        or c.get("_source", {}).get("text", "")
        for c in chunks
    ]
    # Truncate each text to 2000 chars to stay within CrossEncoder max_length
    texts  = [t[:2000] for t in texts]
    pairs  = [(query, t) for t in texts]
    scores = _reranker.predict(pairs, show_progress_bar=False)
 
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
 
    print("\n=== RERANKING RESULTS ===")
    for i, (score, chunk) in enumerate(ranked[:top_k]):
        print(f"\nRank {i+1}  CrossEncoder score: {score:.4f}")
        src = chunk.get("_source", {})
        print(src.get("child_match_text", src.get("text", ""))[:200])
 
    return [{"result": c, "rerank_score": float(s)} for s, c in ranked[:top_k]]

def get_chat_response(system_prompt, user_query):
    url  = "http://localhost:11434/api/chat"
    data = {
        "model": "qwen3",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_query},
        ],
        "stream":  False,
        "options": {
            "temperature": 0.0,
            "num_ctx":     8192,   # 5 parent chunks × ~500 tokens + system prompt overhead
        },
    }
    response = requests.post(url, json=data, timeout=120)
    response.raise_for_status()
    return strip_think_tags(response.json()["message"]["content"])

@api_view(["POST"])
def chat_with_advisor_bot(request):
    """API endpoint to handle advisor queries via RAG."""
    user_query = request.data.get("query")
 
    if not user_query:
        return JsonResponse({"error": "Query is required"}, status=400)
 
    # Return cached result for repeated identical queries
    cache_key = user_query.strip().lower()
    if cache_key in _query_cache:
        print(f"Cache hit for: {cache_key}")
        return JsonResponse(_query_cache[cache_key])
 
    try:
        # 1. Embed query with BGE prefix (required for BGE retrieval quality)
        query_embedding = _embedder.encode(
            "Represent this sentence for searching relevant passages: " + user_query
        ).tolist()
 
        # 2. Hybrid vector + keyword search
        raw_results = perform_vector_search(query_embedding, user_query, top_k=40)
 
        # 3. Deduplicate — keep highest-scoring copy of each unique chunk
        best_by_hash = {}
        for res in raw_results:
            src     = res.get("_source", {})
            content = src.get("child_match_text", "") or src.get("text", "")
 
            if ".........." in content or "Table of Contents" in content:
                continue
 
            text_hash = hashlib.md5(content.encode()).hexdigest()
            score     = res.get("_score", 0)
 
            if text_hash not in best_by_hash or score > best_by_hash[text_hash][0]:
                best_by_hash[text_hash] = (score, res)
 
        deduped = [res for _, res in best_by_hash.values()]
 
        # 4. Batch-rerank all deduped chunks, keep top 5
        reranked = rerank(user_query, deduped, top_k=5)
 
        if not reranked:
            return JsonResponse({
                "answer":    "I could not find any relevant information in the fund documents to answer your query.",
                "citations": [],
            })
 
        # 5. Build context — cap each chunk at 1500 chars to stay within num_ctx=8192
        context_text = ""
        citations    = []
 
        for i, item in enumerate(reranked):
            src        = item["result"].get("_source", {})
            chunk_text = (src.get("text", "") or src.get("child_match_text", ""))[:1500]
            context_text += f"--- Document {i+1} ---\n{chunk_text}\n\n"
            citations.append({
                "source": src.get("source_url", "Unknown"),
                "fund":   src.get("fund_name",  "Unknown"),
            })
 
        print("\n=== RETRIEVED CHUNKS ===")
        for i, item in enumerate(reranked):
            src = item["result"].get("_source", {})
            print(f"\nChunk {i+1}  score={item['rerank_score']:.4f}")
            print(src.get("text", "")[:500])
            print("=" * 50)
 
        # 6. Generate answer
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
    
print("USING OPENSEARCH VECTOR SEARCH")