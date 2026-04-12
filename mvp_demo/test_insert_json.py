import requests, os, json
from dotenv import load_dotenv
load_dotenv()
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_INDEX_NAME = os.getenv("CLOUDFLARE_VECTORIZE_INDEX")
url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/vectorize/v2/indexes/{CF_INDEX_NAME}/insert"
headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/x-ndjson"}

# NDJSON mode actually accepts ndjson natively in vectorize directly? Let's check ordinary application/json with {"vectors": [...]}
doc = {"vectors": [{"id": "test_2", "values": [0.1]*1536, "metadata": {"test": "ingest"}}]}
headers_json = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}
res = requests.post(url, json=doc, headers=headers_json)
print("status json:", res.status_code)
print("response json:", res.text)
