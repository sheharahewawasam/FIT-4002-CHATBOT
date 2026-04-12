import os
import requests
from dotenv import load_dotenv

load_dotenv("../mvp_demo/.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN") # Needs Vectorize:Read perms
CF_INDEX_NAME = os.getenv("CLOUDFLARE_VECTORIZE_INDEX", "triple_a_index")

def get_embedding(text):
    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {"input": text, "model": "text-embedding-3-small"}
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]

query = "Tell me about the various query optimization techniques"
query_vector = get_embedding(query)

url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/vectorize/v2/indexes/{CF_INDEX_NAME}/query"
headers = {
    "Authorization": f"Bearer {CF_API_TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "vector": query_vector,
    "topK": 3,
    "returnMetadata": "all"
}

res = requests.post(url, json=payload, headers=headers)
data = res.json()

for match in data.get("result", {}).get("matches", []):
    print("MATCH SCORE:", match["score"])
    print("METADATA TEXT LENGTH:", len(match.get("metadata", {}).get("text", "")))
    print("METADATA TEXT HAS CONTENT:", bool(match.get("metadata", {}).get("text")))
    print("---")
    print(match.get("metadata", {}).get("text", ""))
    print("="*40)
