import os
import json
import requests
import fitz  # PyMuPDF
from dotenv import load_dotenv

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter

load_dotenv("../mvp_demo/.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

pdfs_to_process = [
    {"filepath": "../Trust_Deed_Sample_Superannuation_Fund.pdf", "fund_name": "Triple A Super", "doc_type": "Trust Deed"}
]

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

def main():
    print("Reading documents using PyMuPDF (fitz)...")
    documents = []
    
    for pdf_info in pdfs_to_process:
        filepath = pdf_info['filepath']
        print(f"Parsing {filepath}...")
        
        doc_fitz = fitz.open(filepath)
        for page_num in range(len(doc_fitz)):
            page = doc_fitz[page_num]
            blocks = page.get_text("blocks")
            
            for block in blocks:
                text = block[4].strip()
                if not text or len(text) < 10:
                    continue
                bbox = block[:4] # (x0, y0, x1, y1)
                
                doc = Document(
                    text=text,
                    metadata={
                        "source_url": filepath.split('/')[-1],
                        "fund_name": pdf_info['fund_name'],
                        "doc_type": pdf_info['doc_type'],
                        "page": page_num + 1, # 1-indexed
                        "bbox": list(bbox)
                    }
                )
                documents.append(doc)

    print("Executing SentenceSplitter Chunking...")
    # By using SentenceSplitter on each block `Document`, we ensure child nodes stay within their bbox
    splitter = SentenceSplitter(chunk_size=256, chunk_overlap=20)
    nodes = splitter.get_nodes_from_documents(documents)
    
    print(f"Generated {len(nodes)} high-precision nodes for embedding.")

    print("Generating Vector Embeddings and constructing payload...")
    
    doc_map = {doc.doc_id: doc for doc in documents}
    
    with open("vectors.ndjson", "w") as f:
        for i, node in enumerate(nodes):
            print(f"Embedding node {i+1}/{len(nodes)}...")
            embedding = get_embedding(node.text)
            
            expanded_context = node.text
            if node.source_node and node.source_node.node_id in doc_map:
                expanded_context = doc_map[node.source_node.node_id].text
            
            # Truncate text to forcefully respect Cloudflare Vectorize's metadata limit
            if len(expanded_context) > 7000:
                expanded_context = expanded_context[:7000] + "... [Text Truncated]"
                
            record = {
                "id": node.node_id.replace("-", ""),
                "values": embedding,
                "metadata": {
                    "text": expanded_context,
                    "child_match_text": node.text,
                    "source_url": node.metadata.get("source_url"),
                    "fund_name": node.metadata.get("fund_name"),
                    "doc_type": node.metadata.get("doc_type"),
                    "page": node.metadata.get("page"),
                    "bbox": json.dumps(node.metadata.get("bbox")) # stringify list for metadata
                }
            }
            f.write(json.dumps(record) + "\n")

    print("Successfully created vectors.ndjson.")
            
if __name__ == "__main__":
    main()
