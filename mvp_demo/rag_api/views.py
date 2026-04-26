import os
import requests
# import openai
from django.http import JsonResponse
from rest_framework.decorators import api_view
from dotenv import load_dotenv

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
        "topK": 5,
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

# @api_view(['POST'])
# def chat_with_advisor_bot(request):
#     """API Endpoint to handle advisor queries via RAG."""
#     user_query = request.data.get("query")
    
#     if not user_query:
#         return JsonResponse({"error": "Query is required"}, status=400)

#     try:
#         # 1. Embed the user query
#         query_response = openai.embeddings.create(
#             input=user_query,
#             model="text-embedding-3-small"
#         )
#         query_embedding = query_response.data[0].embedding

#         # 2. Retrieve relevant documents from Cloudflare Vectorize
#         search_results = perform_vector_search(query_embedding)
        
#         if not search_results:
#             return JsonResponse({
#                 "answer": "I could not find any relevant information in the fund documents to answer your query.",
#                 "citations": []
#             })

#         # 3. Construct Context and Citations
#         context_text = ""
#         citations = []
        
#         for i, res in enumerate(search_results):
#             metadata = res.get("metadata", {})
#             chunk_text = metadata.get("text", "")
#             context_text += f"--- Document {i+1} ---\n{chunk_text}\n\n"
#             citations.append({
#                 "source": metadata.get('source_url', 'Unknown'),
#                 "fund": metadata.get('fund_name', 'Unknown')
#             })

#         # 4. Generate Answer via LLM (Augmentation)
#         system_prompt = f"""
#         You are an expert AI assistant for financial advisors at Triple A Super.
#         Answer the user's query STRICTLY based on the provided document context below. 
#         If the answer is not in the context, say "I cannot answer this based on the provided documents."
#         Do not provide general financial advice outside of these documents.
        
#         CONTEXT:
#         {context_text}
#         """

#         llm_response = openai.chat.completions.create(
#             model="gpt-4o",
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": user_query}
#             ],
#             temperature=0.0
#         )

#         answer = llm_response.choices[0].message.content

#         # 5. Return response to UI
#         return JsonResponse({
#             "answer": answer,
#             "citations": citations 
#         })

#     except Exception as e:
#         return JsonResponse({"error": str(e)}, status=500)


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
        search_results = perform_vector_search(query_embedding)
        
        if not search_results:
            return JsonResponse({
                "answer": "I could not find any relevant information in the fund documents to answer your query.",
                "citations": []
            })

        # 3. Construct Context and Citations
        context_text = ""
        citations = []
        
        for i, res in enumerate(search_results):
            metadata = res.get("metadata", {})
            chunk_text = metadata.get("text", "")
            context_text += f"--- Document {i+1} ---\n{chunk_text}\n\n"
            citations.append({
                "source": metadata.get('source_url', 'Unknown'),
                "fund": metadata.get('fund_name', 'Unknown')
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
