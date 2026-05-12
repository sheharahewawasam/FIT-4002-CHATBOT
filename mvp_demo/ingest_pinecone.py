import os
import json
import requests
import pdfplumber
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

# Import LlamaIndex components
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

load_dotenv("secrets.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "fit4002-pinecone-index")

pc = Pinecone(api_key=PINECONE_API_KEY)

pdfs_to_process = [
    {"filepath": "../Project_26.pdf", "fund_name": "Triple A Super", "doc_type": "Project Brief"},
    {"filepath": "../Proposal Document.pdf", "fund_name": "Triple A Super", "doc_type": "Development Proposal"},
    {"filepath": "../deed.pdf", "fund_name": "Summers Family Super Fund", "doc_type": "Deed"},
    {"filepath": "../sample-smsf-trust-deed.pdf", "fund_name": "Triple A Super", "doc_type": "Deed"},
    {"filepath": "../SIS Act -1.pdf", "fund_name": "Triple A Super", "doc_type": "Project Brief"},
    {"filepath": "../SIS Act Part 2-1.pdf", "fund_name": "Triple A Super", "doc_type": "Development Proposal"},
    {"filepath": "../Super-changes-timeline-1.pdf", "fund_name": "Triple A Super", "doc_type": "Changelog"},
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
    data = {"model": "jina/jina-embeddings-v2-base-en","input": text }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()["embeddings"][0]

def clean_text(text):
    return " ".join(text.split())


def main():
    # Create Pinecone Index
    if not pc.has_index(PINECONE_INDEX_NAME):
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=768,  
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )

    index = pc.Index(PINECONE_INDEX_NAME)
    
    print("Reading documents using LlamaIndex...")
    documents = []
    
    # We will manually construct Document objects to preserve custom metadata 
    # and map accurately to our specific files.
    from llama_index.core import Document

    
    for pdf_info in pdfs_to_process:
        print(f"Parsing {pdf_info['filepath']}...")

        full_pages = []

        with pdfplumber.open(pdf_info['filepath']) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_pages.append(clean_text(text))

        full_text = "\n".join(full_pages)

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
    # This creates a structure where parent nodes encompass 512-token child nodes
    node_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=[2048, 256])
    nodes = node_parser.get_nodes_from_documents(documents)
    
    # We only embed the smallest, most precise sub-chunks (leaf nodes)
    leaf_nodes = get_leaf_nodes(nodes)
    print(f"Generated {len(leaf_nodes)} high-precision child nodes for embedding.")

    # We need a map of all nodes to look up parent texts quickly
    node_map = {n.node_id: n for n in nodes}

    print("Generating Vector Embeddings and constructing payload...")
    # documents_to_insert = []
            
    vectors = []

    for i, leaf in enumerate(leaf_nodes):
        print(f"Embedding leaf node {i+1}/{len(leaf_nodes)}...")
        embedding = get_embedding(leaf.text)

        parent_id = leaf.parent_node.node_id if leaf.parent_node else None
        parent_node = node_map.get(parent_id)
        expanded_context = parent_node.text if parent_node else leaf.text

        vectors.append({
            "id": leaf.node_id.replace("-", ""),
            "values": embedding,
            "metadata": {
                "text": expanded_context[:1500],
                "child_match_text": leaf.text[:800],
                "child_id": leaf.node_id.replace("-", ""),
                "source_url": leaf.metadata.get("source_url"),
                "fund_name": leaf.metadata.get("fund_name"),
                "doc_type": leaf.metadata.get("doc_type")
            }
        })

    batch_size = 100
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i+batch_size]
        index.upsert(vectors=batch)
        print(f"Inserted batch {i//batch_size + 1}")

if __name__ == "__main__":
    main()