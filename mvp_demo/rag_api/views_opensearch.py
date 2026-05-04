import json
import os
import requests
import boto3

from django.http import JsonResponse
from rest_framework.decorators import api_view
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

load_dotenv("secrets.env")

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "fit4002-opensearch-index")

credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, AWS_REGION, "es")

client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST.replace("https://", ""), "port": 443}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)

def get_embedding(text):
    #Use locally hosted Ollama to embed type shit 
    url = "http://localhost:11434/api/embed"
    data = {"model": "nomic-embed-text","input": text }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()["embeddings"][0]

def get_chat_response(systemPrompt, userQuery):
    #Use locally hosted Ollama to generate a response type shit 
    url = "http://localhost:11434/api/chat"
    data = {"model": "granite3-dense",
            "messages": [{"role": "system", "content":systemPrompt}, {"role": "user", "content":userQuery}],
            "stream": False,
            "options": {"temperature": 0.0}
            }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()["message"]["content"]

def perform_vector_search(query_embedding, user_query):
    # Build search request
    search_body = {
        "size": 5, # return top 5 results
        "query": {
            "hybrid": { # combine both keyword search and semantic search
                "queries": [
                    # Semantic search
                    {
                        "knn": {
                            "embedding": {
                                "vector": query_embedding, # user query embedding 
                                "k": 5 # number of nearest neighbors 
                            }
                        }
                    },
                    # Keyword search
                    {
                        "match": {
                            "text": {
                                "query": user_query # raw user input
                            }
                        }
                    }
                ]
            }
        }
    }
    
    # Send query to OpenSearch
    response = client.search(
        index=OPENSEARCH_INDEX,
        body=search_body
    )

    print("SEARCH BODY:", json.dumps(search_body, indent=2))

    for hit in response["hits"]["hits"]:
        print("Score:", hit["_score"])
        print("Source:", hit["_source"].get("source_url"))
        print("Text preview:", hit["_source"].get("text", "")[:200])
        print("-" * 50)

    return response["hits"]["hits"]

@api_view(['POST'])
def chat_with_advisor_bot(request):
    """API Endpoint to handle advisor queries via RAG."""
    user_query = request.data.get("query")
    
    if not user_query:
        return JsonResponse({"error": "Query is required"}, status=400)

    try:
        # 1. Embed the user query
        query_embedding = get_embedding(user_query)

        # 2. Retrieve relevant documents from Cloudflare Vectorize
        search_results = perform_vector_search(query_embedding, user_query)
        
        if not search_results:
            return JsonResponse({
                "answer": "I could not find any relevant information in the fund documents to answer your query.",
                "citations": []
            })

        # 3. Construct Context and Citations
        context_text = ""
        citations = []
        
        for i, res in enumerate(search_results):
            # OpenSearch stores data in "_source"
            source = res.get("_source", {})
            # Get text content
            chunk_text = source.get("text", "")
            # Add to context for LLM
            context_text += f"--- Document {i+1} ---\n{chunk_text}\n\n"
            
            # Store citation info
            citations.append({
                "source": source.get("source_url", "Unknown"),
                "fund": source.get("fund_name", "Unknown")
            })
        
        # 4. Generate Answer via LLM (Augmentation)
        system_prompt = f"""
        You are an expert AI assistant for financial advisors at Triple A Super.
        Answer the user's query STRICTLY based on the provided document context below. 
        If the answer is not in the context, say "I cannot answer this based on the provided documents."
        Do not provide general financial advice outside of these documents.
        
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
    
print("USING OPENSEARCH VECTOR SEARCH")