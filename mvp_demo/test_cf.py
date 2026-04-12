import os
import requests
import openai
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_INDEX_NAME = os.getenv("CLOUDFLARE_VECTORIZE_INDEX")

res = openai.embeddings.create(input="What are the core features?", model="text-embedding-3-small")
emb = res.data[0].embedding

url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/vectorize/v2/indexes/{CF_INDEX_NAME}/query"
headers = {
    "Authorization": f"Bearer {CF_API_TOKEN}",
    "Content-Type": "application/json"
}
payload = {
    "vector": emb,
    "topK": 5,
    "returnValues": False,
    "returnMetadata": "all"
}
print(f"Requesting {url}")
response = requests.post(url, json=payload, headers=headers)
print("Status Code:", response.status_code)
print("Response:", response.text)
