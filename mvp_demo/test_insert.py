import requests, os, json
from dotenv import load_dotenv
load_dotenv()
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_INDEX_NAME = os.getenv("CLOUDFLARE_VECTORIZE_INDEX")
url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/vectorize/v2/indexes/{CF_INDEX_NAME}/insert"
headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/x-ndjson"}
doc = {"id": "test_1", "values": [0.1]*1536, "metadata": {"test": "ingest"}}
res = requests.post(url, data=json.dumps(doc), headers=headers)
print("status:", res.status_code)
print("response:", res.text)
