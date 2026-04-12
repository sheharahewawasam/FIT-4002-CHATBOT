import os
import json
import requests
from dotenv import load_dotenv

from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

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
    print("Reading documents using LlamaIndex...")
    documents = []
    
    from llama_index.core import Document
    import pypdf
    
    for pdf_info in pdfs_to_process:
        print(f"Parsing {pdf_info['filepath']}...")
        reader = pypdf.PdfReader(pdf_info['filepath'])
        full_text = "\\n".join(page.extract_text() for page in reader.pages if page.extract_text())
        
        doc = Document(
            text=full_text, 
            metadata={
                "source_url": pdf_info['filepath'].split('/')[-1],
                "fund_name": pdf_info['fund_name'],
                "doc_type": pdf_info['doc_type']
            }
        )
        documents.append(doc)

    print("Executing Hierarchical Node Chunking...")
    # This creates a structure where parent nodes encompass 256-token child nodes
    node_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=[1024, 256])
    nodes = node_parser.get_nodes_from_documents(documents)
    
    leaf_nodes = get_leaf_nodes(nodes)
    print(f"Generated {len(leaf_nodes)} high-precision child nodes for embedding.")

    node_map = {n.node_id: n for n in nodes}
    print("Generating Vector Embeddings and constructing payload...")
    
    with open("vectors.ndjson", "w") as f:
        for i, leaf in enumerate(leaf_nodes):
            print(f"Embedding leaf node {i+1}/{len(leaf_nodes)}...")
            embedding = get_embedding(leaf.text)
            
            parent_id = leaf.parent_node.node_id if leaf.parent_node else None
            parent_node = node_map.get(parent_id)
            
            expanded_context = parent_node.text if parent_node else leaf.text
            
            # Truncate text to forcefully respect Cloudflare Vectorize's 10KB metadata limit
            if len(expanded_context) > 7000:
                expanded_context = expanded_context[:7000] + "... [Text Truncated]"
                
            record = {
                "id": leaf.node_id.replace("-", ""),
                "values": embedding,
                "metadata": {
                    "text": expanded_context,
                    "child_match_text": leaf.text,
                    "source_url": leaf.metadata.get("source_url"),
                    "fund_name": leaf.metadata.get("fund_name"),
                    "doc_type": leaf.metadata.get("doc_type")
                }
            }
            f.write(json.dumps(record) + "\n")
            
if __name__ == "__main__":
    main()
