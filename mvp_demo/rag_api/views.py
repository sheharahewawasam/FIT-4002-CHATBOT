import os
import requests
# import openai
from django.http import JsonResponse
from rest_framework.decorators import api_view
from dotenv import load_dotenv
import json
import re
import hashlib

load_dotenv("secrets.env")

# openai.api_key = os.getenv("OPENAI_API_KEY")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_INDEX_NAME = os.getenv("CLOUDFLARE_VECTORIZE_INDEX")


def perform_vector_search(query_embedding):
    """Executes a vector search in Cloudflare Vectorize."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/vectorize/v2/indexes/{CF_INDEX_NAME}/query"
    
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "vector": query_embedding,
        "topK": 15,
        "returnValues": False,
        "returnMetadata": "all"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        print("Vectorize Error:", response.text)
        return []
        
    data = response.json()
    if data.get("success"):
        return data["result"]["matches"]
    return []


def query_rewriter_hyde(query):
    systemPrompt = (
    "You are a retrieval query expansion assistant for a superannuation chatbot knowledge base. "
    "Given a user question, correct any spelling or grammar. Then rewrite the question so it "
    "mentions specific technical terms, section headings, or strategies that would appear in "
    "the relevant documents Trust Deed', 'Establishment and Purpose', 'SIS Act'). "
    "But try not to randomly add those technical terms if you aren't sure that they are relevant"
    "Output ONLY the single paragraph WHICH IS THE EXPANDED the query, and NOTHING else, WHEN I SAY NOTHING I MEAN NOTHING,"
    "NO need to state what you have done to the query or what problems there were with the query please."
    )
    
    url = "http://localhost:11434/api/chat"
    data = {"model": "qwen3",
            "messages": [{"role": "system", "content": systemPrompt}, {"role": "user", "content": query}],
            "stream": False,
            "options": {"temperature": 0.0}
            }
    response = requests.post(url, json=data)
    response.raise_for_status()
    
    rewritten = response.json()["message"]["content"].strip()
    # Remove any potential quotes or extraneous formatting
    return [rewritten]

def extract_keyphrase(query):
    prompt = (
        "Given a user question about a superannuation trust deed or SIS Act, "
        "output a short descriptive phrase or heading (2-6 words) that would very likely "
        "appear in the document's table of contents or as a section title. "
        "Examples: 'Auto-Pension Commencement', 'Establishment and Purpose', "
        "'Trustee meetings', 'Preservation Age'. "
        "Do NOT output a bare section number like 'Section 56(1)' unless that number "
        "is part of a full heading. Output ONLY the phrase, nothing else NO NEED FOR ANY NOTES OR ANYTHING EXTRA PLEASE.\n"
        f"Question: {query}\nPhrase:"
    )
    response = requests.post("http://localhost:11434/api/generate", json={
        "model": "qwen3",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0}
    })
    response.raise_for_status()
    return response.json()["response"].strip()

def rerank_results(user_query, search_results, top_k=10):
    """
    Rerank search results by computing relevance scores.
    Uses Ollama to score each chunk's relevance to the query.
    """
    scored_results = []
    
    for res in search_results:
        chunk_text = res.get("metadata", {}).get("text", "")
        
        # Truncate chunk if too long (Llama context limit)
        max_chunk_length = 1500
        if len(chunk_text) > max_chunk_length:
            chunk_text = chunk_text[:max_chunk_length] + "..."
        
        # Prompt Llama to score relevance
        scoring_prompt = f"""You are evaluating if a document chunk ANSWERS the user's question.

            Score from 0-10 where:
            - 10 = Directly answers the specific question with relevant details
            - 5-7 = Contains related information but doesn't directly answer
            - 0-2 = Mentions keywords but provides no answer

            CRITICAL: Just mentioning the same words as the query does NOT mean it answers the question.
            A title page that says "Summers Trust Fund" but provides no details about its purpose scores LOW.

            Question: {user_query}

            Document chunk:
            {chunk_text}

            Think: Does this chunk actually ANSWER the question, or just mention the same words?

            Score (0-10):"""
        
        url = "http://localhost:11434/api/generate"
        data = {
            "model": "qwen3",
            "prompt": scoring_prompt,
            "stream": False,
            "options": {"temperature": 0.0}
        }
        
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            score_text = response.json()["response"].strip()
            
            # Extract numeric score (handle cases like "8/10" or "8.")
            import re
            match = re.search(r'(\d+)', score_text)
            rerank_score = float(match.group(1)) if match else 0.0
            
        except Exception as e:
            print(f"Reranking error: {e}")
            rerank_score = res.get("score", 0.5)  # Fallback to vector score
        
        scored_results.append({
            "result": res,
            "rerank_score": rerank_score,
            "original_score": res.get("score", 0)
        })
    
    # Sort by rerank score (descending) and return top_k
    scored_results.sort(key=lambda x: x["rerank_score"], reverse=True)
    
    print("\n=== RERANKING RESULTS ===")
    for i, item in enumerate(scored_results[:top_k]):
        print(f"\nRank {i+1}")
        print(f"Rerank Score: {item['rerank_score']}/10")
        print(f"Original Vector Score: {item['original_score']:.4f}")
        print(item['result'].get('metadata', {}).get('text', '')[:200])
    
    return scored_results[:top_k]


def get_embedding(text):
    #Use locally hosted Ollama to embed type shit 
    url = "http://localhost:11434/api/embed"
    data = {"model": "jina/jina-embeddings-v2-base-en","input": text }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()["embeddings"][0]

def get_chat_response(systemPrompt, userQuery):
    #Use locally hosted Ollama to generate a response type shit 
    url = "http://localhost:11434/api/chat"
    data = {"model": "qwen3",
            "messages": [{"role": "system", "content":systemPrompt}, {"role": "user", "content":userQuery}],
            "stream": False,
            "options": {"temperature": 0.0}
            }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()["message"]["content"]


@api_view(['POST'])
def chat_with_advisor_bot(request):
    """API Endpoint to handle advisor queries via RAG."""
    user_query = request.data.get("query")
    
    if not user_query:
        return JsonResponse({"error": "Query is required"}, status=400)

    try:
        #1. Rewrite and embed queries
        rewritten_queries = query_rewriter_hyde(user_query)
        keyphrase = extract_keyphrase(user_query)
        rewritten_queries.append(keyphrase)

        # Always include the original phrasing – it may contain the exact technical terms needed
        if user_query not in rewritten_queries:
            rewritten_queries.append(user_query)
            
        print(rewritten_queries)
        
        all_results = []
        for q in rewritten_queries:
            query_embedding = get_embedding(q)
            results = perform_vector_search(query_embedding)
            all_results.extend(results)
        
        # 2. Deduplicate chunks (keep highest score
        seen_texts = set()
        deduped_results = []

        for res in all_results:
            content = res.get("metadata", {}).get("text", "")
            # FILTER: Ignore Table of Contents chunks (usually lots of dots)
            if ".........." in content or "Table of Contents" in content:
                continue
            text_hash = hashlib.md5(content.encode()).hexdigest()

            if text_hash not in seen_texts:
                deduped_results.append(res)
                seen_texts.add(text_hash)
                
        search_results = rerank_results(user_query, deduped_results, top_k=len(deduped_results))
        
        quality_results = [
            item for item in search_results
            if item["rerank_score"] >= 4
        ]

        if not quality_results:
            return JsonResponse({
                "answer": "I could not find any relevant information in the fund documents to answer your query.",
                "citations": []
            })
                
        search_results = quality_results
            

        # 4. Construct Context and Citations
        context_text = ""
        citations = []
        
        for i, item in enumerate(search_results):
            res = item["result"]
            metadata = res.get("metadata", {})
            chunk_text = metadata.get("text", "")
            context_text += f"--- Document {i+1} ---\n{chunk_text}\n\n"
            citations.append({
                "source": metadata.get('source_url', 'Unknown'),
                "fund": metadata.get('fund_name', 'Unknown')
            })
            
        print("\n=== RETRIEVED CHUNKS ===")

        for i, item in enumerate(search_results):
            res = item["result"]
            score = res.get("score")
            text = res.get("metadata", {}).get("text", "")

            print(f"\nChunk {i+1}")
            print(f"Score: {score}")
            print(text[:500])
            print("=" * 50)
            
        # 5. Generate Answer via LLM (Augmentation)
        system_prompt = f"""
        You are an expert AI assistant for financial advisors at Triple A Super.
        Answer the user's query STRICTLY based on the provided document context below. 
        If the answer is not in the context, say "I cannot answer this based on the provided documents."
        Answer only with what the document gives you, do not infer or try to answer questiont aht were not asked.
        
        If the query asks about methods, techniques, strategies, or types:
        - enumerate ALL methods found in the context
        - do not omit any
        - use bullet points

        If the answer is absent from context, say so.
        
        Do not provide general financial advice outside of these documents.
        DO NOT PROVIDE ANY INFORMATION IN GENERAL IF ITS NOT IN THE DOCUMENTS, DONT MAKE STUFF UP
        
        CONTEXT:
        {context_text}
        """

        answer = get_chat_response(system_prompt,user_query)
        
        response_data = {
            "answer": answer,
            "citations": citations 
        }

        # 5. Return response to UI
        return JsonResponse({
            "answer": answer,
            "citations": citations 
        })
        

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)