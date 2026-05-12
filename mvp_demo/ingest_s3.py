import os
import json
import requests
import boto3
import pypdf

from dotenv import load_dotenv

# Import LlamaIndex components
from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

load_dotenv("secrets.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
# CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN") # Needs Vectorize:Edit perms
# CF_INDEX_NAME = os.getenv("CLOUDFLARE_VECTORIZE_INDEX", "triple_a_index")

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
S3_VECTOR_INDEX_ARN = os.getenv("S3_VECTOR_INDEX_ARN")

s3vectors = boto3.client("s3vectors", region_name=AWS_REGION)

pdfs_to_process = [
    {"filepath": "../Project_26.pdf", "fund_name": "Triple A Super", "doc_type": "Project Brief"},
    {"filepath": "../Proposal Document.pdf", "fund_name": "Triple A Super", "doc_type": "Development Proposal"},
]

def get_embedding(text):
    """Use locally hosted Ollama to embed type shit """
    url = "http://localhost:11434/api/embed"
    data = {"model": "jina/jina-embeddings-v2-base-en","input": text }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()["embeddings"][0]

def main():
    print("Reading documents using LlamaIndex...")
    documents = []
    
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
    
    # We only embed the smallest, most precise sub-chunks (leaf nodes)
    leaf_nodes = get_leaf_nodes(nodes)
    print(f"Generated {len(leaf_nodes)} high-precision child nodes for embedding.")

    # We need a map of all nodes to look up parent texts quickly
    node_map = {n.node_id: n for n in nodes}

    print("Generating Vector Embeddings and constructing payload...")
    documents_to_insert = []

    parent_context_store = {}
    
    for i, leaf in enumerate(leaf_nodes):
        print(f"Embedding leaf node {i+1}/{len(leaf_nodes)}...")
        embedding = get_embedding(leaf.text)
        
        # Look up parent text for expanded generation context
        parent_id = leaf.parent_node.node_id if leaf.parent_node else None
        parent_node = node_map.get(parent_id)

        if parent_node:
            parent_context_store[parent_id] = parent_node.text  
        
        expanded_context = parent_node.text if parent_node else leaf.text
        
        documents_to_insert.append({
            "id": leaf.node_id.replace("-", ""), # Cloudflare likes clean alphanumeric string IDs
            "values": embedding,
            "metadata": {
                "text": leaf.text,  # use smaller chunk instead of parent
                "parent_id": parent_id,
                "source_url": leaf.metadata.get("source_url"),
                "fund_name": leaf.metadata.get("fund_name"),
                "doc_type": leaf.metadata.get("doc_type")
            }
        })

    with open("parent_contexts.json", "w") as f:
        json.dump(parent_context_store, f)

    if documents_to_insert:
        batch_size = 50

        for i in range(0, len(documents_to_insert), batch_size):
            batch = documents_to_insert[i:i+batch_size]

            vectors = []
            for doc in batch:
                vectors.append({
                    "key": doc["id"],
                    "data": {
                        "float32": doc["values"] # S3 Vector Index expects "float32" format for embeddings
                    },
                    "metadata": doc["metadata"]
                })
            
            print(f"Inserting batch {i//batch_size + 1} to Amazon S3 Vector Index ...")

            response = s3vectors.put_vectors(
                indexArn=S3_VECTOR_INDEX_ARN,
                vectors=vectors
            )

            print(f"Inserted {len(vectors)} vectors")

if __name__ == "__main__":
    main()