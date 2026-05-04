import os
import json
import requests

from dotenv import load_dotenv

# Import LlamaIndex components
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.env"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN") # Needs Vectorize:Edit perms
CF_INDEX_NAME = os.getenv("CLOUDFLARE_VECTORIZE_INDEX", "triple_a_index")

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

pdfs_to_process = [
    {"filepath": os.path.join(_BASE_DIR, "..", "Project_26.pdf"), "fund_name": "Triple A Super", "doc_type": "Project Brief"},
    {"filepath": os.path.join(_BASE_DIR, "..", "Proposal Document.pdf"), "fund_name": "Triple A Super", "doc_type": "Development Proposal"}
]

# def get_embedding(text):
#     """Fetch vector embedding using OpenAI API."""
#     url = "https://api.openai.com/v1/embeddings"
#     headers = {
#         "Authorization": f"Bearer {OPENAI_API_KEY}",
#         "Content-Type": "application/json"
#     }
#     data = {"input": text, "model": "text-embedding-3-small"}
#     response = requests.post(url, json=data, headers=headers)
#     response.raise_for_status()
#     return response.json()["data"][0]["embedding"]

def get_embedding(text):
    """Use locally hosted Ollama to embed type shit """
    url = "http://localhost:11434/api/embed"
    data = {"model": "nomic-embed-text","input": text }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()["embeddings"][0]

def main():
    print("Reading documents using LlamaIndex...")
    documents = []
    
    # We will manually construct Document objects to preserve custom metadata 
    # and map accurately to our specific files.
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
    
    # We only embed the smallest, most precise sub-chunks (leaf nodes)
    leaf_nodes = get_leaf_nodes(nodes)
    print(f"Generated {len(leaf_nodes)} high-precision child nodes for embedding.")

    # We need a map of all nodes to look up parent texts quickly
    node_map = {n.node_id: n for n in nodes}

    print("Generating Vector Embeddings and constructing payload...")
    documents_to_insert = []
    
    for i, leaf in enumerate(leaf_nodes):
        print(f"Embedding leaf node {i+1}/{len(leaf_nodes)}...")
        embedding = get_embedding(leaf.text)
        
        # Look up parent text for expanded generation context
        parent_id = leaf.parent_node.node_id if leaf.parent_node else None
        parent_node = node_map.get(parent_id)
        
        # The trick: We index the granular child context, but we provide the LLM the broad parent context!
        expanded_context = parent_node.text if parent_node else leaf.text
        
        documents_to_insert.append({
            "id": leaf.node_id.replace("-", ""), # Cloudflare likes clean alphanumeric string IDs
            "values": embedding,
            "metadata": {
                "text": expanded_context, # Returning Parent context!
                "child_match_text": leaf.text, # Storing what strictly matched
                "source_url": leaf.metadata.get("source_url"),
                "fund_name": leaf.metadata.get("fund_name"),
                "doc_type": leaf.metadata.get("doc_type")
            }
        })
        
    if documents_to_insert:
        batch_size = 50
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/vectorize/v2/indexes/{CF_INDEX_NAME}/insert"
        headers = {
            "Authorization": f"Bearer {CF_API_TOKEN}",
            "Content-Type": "application/json"
        }
        
        for i in range(0, len(documents_to_insert), batch_size):
            batch = documents_to_insert[i:i+batch_size]
            payload = {"vectors": batch}
            
            print(f"Inserting batch {i//batch_size + 1} to Cloudflare Vectorize (Hierarchical Vectors)...")
            res = requests.post(url, json=payload, headers=headers)
            
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    print(f"Successfully inserted {len(batch)} parent-linked nodes.")
                else:
                    print(f"Error inserting: {data}")
            else:
                print(f"HTTP Error: {res.status_code}")
                print(res.text)

if __name__ == "__main__":
    main()
