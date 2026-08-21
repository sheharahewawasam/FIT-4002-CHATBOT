import os
import re
import hashlib
import requests
import datetime
import textwrap

from django.http import JsonResponse
from dotenv import load_dotenv
from pinecone import Pinecone
from pinecone_text.sparse import BM25Encoder
from sentence_transformers import SentenceTransformer, CrossEncoder
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.throttling import AnonRateThrottle

load_dotenv("secrets.env")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

BM25_ENCODER_PATH = os.getenv("BM25_ENCODER_PATH", "bm25_encoder.json")

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

_bm25 = BM25Encoder().load(BM25_ENCODER_PATH)

# Both models loaded once at startup — reused across all requests
_embedder = SentenceTransformer("BAAI/bge-base-en-v1.5")
_embedder.max_seq_length = 512
_reranker = CrossEncoder("BAAI/bge-reranker-base", max_length=512)

class ChatbotRateThrottle(AnonRateThrottle):
    scope = "chatbot"

# Simple in-memory cache — repeated identical queries return instantly
_query_cache: dict = {}

# Strip Qwen3 <think>...</think> tokens that sometimes leak into output
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think_tags(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


def perform_vector_search(query_embedding, user_query, filters, top_k=40):
    """
    Pure vector search against Pinecone.
    Returns Pinecone match dicts: {"id", "score", "metadata": {...}}
    """
    sparse_vector = _bm25.encode_queries(user_query)

    results = index.query(
        vector=query_embedding,
        sparse_vector=sparse_vector,
        top_k=top_k,
        include_metadata=True,
        filter={
             "fund_name": {"$in": filters}
        }
    )
    return results.get("matches", [])


def rerank(query, chunks, top_k=5, score_threshold=0.0):
    """
    Batch-score all chunks in ONE CrossEncoder forward pass.
    Replaces the old approach of one Ollama LLM call per chunk.
    """
    if not chunks:
        return []

    texts  = [
        (c.get("metadata", {}).get("child_match_text", "")
         or c.get("metadata", {}).get("text", ""))[:1000]
        for c in chunks
    ]
    pairs = [(query, t) for t in texts]
    scores = _reranker.predict(pairs, show_progress_bar=False)

    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)

    # print("\n=== RERANKING RESULTS ===")
    # for i, (score, chunk) in enumerate(ranked[:top_k]):
    #     meta = chunk.get("metadata", {})
    #     print(f"\nRank {i+1}  CrossEncoder score: {score:.4f}")
    #     print((meta.get("child_match_text") or meta.get("text", ""))[:200])

    filtered = [(s, c) for s, c in ranked[:top_k] if s >= score_threshold]

    if not filtered:
        print(f"WARNING: all top-{top_k} chunks scored below threshold {score_threshold:.1f} — returning top-1 anyway")
        filtered = ranked[:1]
    

    return [{"result": c, "rerank_score": float(s)} for s, c in filtered]

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

@api_view(["POST"])
@throttle_classes([ChatbotRateThrottle])
def chat_with_advisor_bot(request):
    user_query = request.data.get("query")
    funds = request.data.get("funds", [])
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

        # 2. Vector search
        raw_results = perform_vector_search(query_embedding, user_query, funds, top_k=60)

        # 3. Deduplicate — keep highest-scoring copy of each unique chunk
        best_by_hash = {}
        for res in raw_results:
            metadata = res.get("metadata", {})
            content = metadata.get("text", "") or metadata.get("child_match_text", "")

            if ".........." in content or "Table of Contents" in content:
                continue

            text_hash = hashlib.md5(content.encode()).hexdigest()
            score = res.get("score", 0)
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
        citations = []

        for i, item in enumerate(reranked):
            metadata = item["result"].get("metadata", {})
            chunk_text = (metadata.get("text", "") or metadata.get("child_match_text", ""))[:1500]
            source_name = metadata.get("source_url", "Unknown")
            fund_name = metadata.get("fund_name", "Unknown")
            context_text += f"--- Source: {source_name} ({fund_name}) ---\n{chunk_text}\n\n"
            citations.append({
                "source": source_name,
                "fund": fund_name
            })

        # print("\n=== RETRIEVED CHUNKS ===")
        # for i, item in enumerate(reranked):
        #     metadata = item["result"].get("metadata", {})
        #     print(f"\nChunk {i+1}  score={item['rerank_score']:.4f}")
        #     print(metadata.get("text", "")[:500])
        #     print("=" * 50)

        # 6. Generate answer
        system_prompt = f"""
        You are an expert AI assistant for financial advisors at Triple A Super.
        Answer the user's query using ONLY the provided document context below.
        Do not use any outside knowledge — only what appears in the context.

        If the context contains relevant information, share ALL of it even if it is brief or partial.
        Do not refuse to answer just because the information is incomplete — report what is there.
        Only say "I cannot find information about this in the provided documents" if the context contains
        absolutely nothing related to the query.

        When referencing where information came from, cite the actual source document name shown in the
        context (e.g. "SIS Act -1.pdf") and, if a specific section or clause number is visible in the
        context, include that too (e.g. "Section 4(2) of SIS Act -1.pdf"). Never refer to a source by a
        generic label like "Document 1" or invent a document name or number that isn't shown in the context.

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
        write_audit_log(request.data.get("user"), user_query, answer)
        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


print("USING PINECONE VECTOR STORE (BGE + CrossEncoder)")


def write_audit_log(user, message, response):
    now = datetime.datetime.now()
    currentDate = now.strftime("%Y-%m-%d")
    currentTime = now.strftime("%X")
    
    user_dir = os.path.join("audit_logs", user)
    os.makedirs(user_dir, exist_ok=True)
    fileName = os.path.join(user_dir, f"{user}-{currentDate}_log.txt")

    try:    
        with open(fileName, "a", encoding="utf-8") as f:
            template = textwrap.dedent("""
            ----------------------------------------------------------
            
            At {time}, user asked:
            {message2} 
            
            Chatbot responded with:
            {response2}
            
            -----------------------------------------------------------
            """)
            
            string = template.format(time=currentTime, message2=message, response2=response)
            f.write(string)
    except Exception as e:
        print(f"Audit Logging has failed, please diagnose, error: {e}")
    
    
#a copy of the rag logic just for testing purposes, kindly change this also when you are making any changes to the chat with advisor bot funciton, or we should seperate logic better
#but I cba do that 
def rag_logic(test_questions:str):
    user_query = test_questions

    # 1. Embed query with BGE prefix (required for BGE retrieval quality)
    query_embedding = _embedder.encode(
        "Represent this sentence for searching relevant passages: " + user_query
    ).tolist()

    # 2. Vector search
    raw_results = perform_vector_search(query_embedding, user_query, ["Summers Family Super Fund"], top_k=60)

    # 3. Deduplicate — keep highest-scoring copy of each unique chunk
    best_by_hash = {}
    for res in raw_results:
        metadata = res.get("metadata", {})
        content = metadata.get("text", "") or metadata.get("child_match_text", "")

        if ".........." in content or "Table of Contents" in content:
            continue

        text_hash = hashlib.md5(content.encode()).hexdigest()
        score = res.get("score", 0)
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
    citations = []

    for i, item in enumerate(reranked):
        metadata = item["result"].get("metadata", {})
        chunk_text = (metadata.get("text", "") or metadata.get("child_match_text", ""))[:1500]
        source_name = metadata.get("source_url", "Unknown")
        fund_name = metadata.get("fund_name", "Unknown")
        context_text += f"--- Source: {source_name} ({fund_name}) ---\n{chunk_text}\n\n"
        citations.append({
            "source": source_name,
            "fund": fund_name
        })

    # print("\n=== RETRIEVED CHUNKS ===")
    # for i, item in enumerate(reranked):
    #     metadata = item["result"].get("metadata", {})
    #     print(f"\nChunk {i+1}  score={item['rerank_score']:.4f}")
    #     print(metadata.get("text", "")[:500])
    #     print("=" * 50)

    # 6. Generate answer
    system_prompt = f"""
    You are an expert AI assistant for financial advisors at Triple A Super.
    Answer the user's query using ONLY the provided document context below.
    Do not use any outside knowledge — only what appears in the context.

    If the context contains relevant information, share ALL of it even if it is brief or partial.
    Do not refuse to answer just because the information is incomplete — report what is there.
    Only say "I cannot find information about this in the provided documents" if the context contains
    absolutely nothing related to the query.

    When referencing where information came from, cite the actual source document name shown in the
    context (e.g. "SIS Act -1.pdf") and, if a specific section or clause number is visible in the
    context, include that too (e.g. "Section 4(2) of SIS Act -1.pdf"). Never refer to a source by a
    generic label like "Document 1" or invent a document name or number that isn't shown in the context.

    If the query asks about methods, techniques, strategies, or types:
    - enumerate ALL methods found in the context
    - do not omit any
    - use bullet points

    CONTEXT:
    {context_text}
    """

    answer = get_chat_response(system_prompt, user_query)

    result = {"answer": answer, "citations": citations, "context": context_text}
    return JsonResponse(result)

