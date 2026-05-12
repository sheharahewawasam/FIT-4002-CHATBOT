import os
import pdfplumber
import requests
import boto3

from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

# Import LlamaIndex components
from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

load_dotenv("secrets.env")

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "fit4002-opensearch-index")

credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, AWS_REGION, "es")

# Create OpenSearch client (connection to the OpenSearch Domain)
client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)

pdfs_to_process = [
    {"filepath": "../Project_26.pdf", "fund_name": "Triple A Super", "doc_type": "Project Brief"},
    {"filepath": "../Proposal Document.pdf", "fund_name": "Triple A Super", "doc_type": "Development Proposal"},
    {"filepath": "../deed.pdf", "fund_name": "Summers Family Super Fund", "doc_type": "Deed"},
    {"filepath": "../sample-smsf-trust-deed.pdf", "fund_name": "Triple A Super", "doc_type": "Deed"},
    {"filepath": "../SIS Act -1.pdf", "fund_name": "Triple A Super", "doc_type": "Project Brief"},
    {"filepath": "../SIS Act Part 2-1.pdf", "fund_name": "Triple A Super", "doc_type": "Development Proposal"},
    {"filepath": "../Super-changes-timeline-1.pdf", "fund_name": "Triple A Super", "doc_type": "Changelog"},
]

def get_embedding(text):
    """Use locally hosted Ollama to embed type shit """
    url = "http://localhost:11434/api/embed"
    data = {"model": "jina/jina-embeddings-v2-base-en","input": text }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()["embeddings"][0]

def clean_text(text):
    return " ".join(text.split())

def create_index_if_needed():
    # Check if index already exists
    if client.indices.exists(index=OPENSEARCH_INDEX):
        print("OpenSearch index already exists.")
        return

    # Define index structure (schema)
    index_body = {
        "settings": {
            "index": {
                "knn": True # enable semantic search
            }
        },
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "knn_vector", # stores embeddings
                    "dimension": 768, # match with the embeddign model
                    "method": {
                        "name": "hnsw", # fast search algorithm
                        "space_type": "cosinesimil", # cosine similarity
                        "engine": "faiss" # vector search engine
                    }
                },
                "text": {"type": "text"}, # used for keyword search 
                "child_match_text": {"type": "text"},
                "source_url": {"type": "keyword"}, # exact match field
                "fund_name": {"type": "keyword"}, # filtering
                "doc_type": {"type": "keyword"} # filtering
            }
        }
    }
    
    # create index in OpenSearch
    client.indices.create(index=OPENSEARCH_INDEX, body=index_body)
    print("Created OpenSearch index.")

def main():
    create_index_if_needed()
    
    print("Reading documents using LlamaIndex...")
    documents = []
    
    for pdf_info in pdfs_to_process:
        print(f"Parsing {pdf_info['filepath']}...")
        
        full_pages = []
        
        with pdfplumber.open(pdf_info['filepath']) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_pages.append(clean_text(text))

        full_text = "\\n".join(full_pages)

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
    # Parent nodes = 2048 tokens, leaf nodes = 256 tokens
    node_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=[2048, 256])
    nodes = node_parser.get_nodes_from_documents(documents)
    
    # We only embed the smallest, most precise sub-chunks (leaf nodes)
    leaf_nodes = get_leaf_nodes(nodes)
    print(f"Generated {len(leaf_nodes)} high-precision child nodes for embedding.")

    # We need a map of all nodes to look up parent texts quickly
    node_map = {n.node_id: n for n in nodes}

    print("Generating Vector Embeddings and constructing payload...")
    documents_to_insert = []
    
    # Store embeddings into OpenSearch
    for i, leaf in enumerate(leaf_nodes):
        print(f"Embedding leaf node {i+1}/{len(leaf_nodes)}...")

        # Generating embedding for this chunk
        embedding = get_embedding(leaf.text)
        
        # Get parent node to provide a broader context
        parent_id = leaf.parent_node.node_id if leaf.parent_node else None
        parent_node = node_map.get(parent_id)
        
        # Use parent content for better LLM response
        expanded_context = parent_node.text if parent_node else leaf.text
        
        # Create document to store in OpenSearch
        doc_body = {
            "embedding": embedding, # semantic search vector
            "text": expanded_context[:1500], # full context for answering 
            "child_match_text": leaf.text[:800], # smaller chunk 
            "child_id": leaf.node_id.replace("-", ""),
            "source_url": leaf.metadata.get("source_url"),
            "fund_name": leaf.metadata.get("fund_name"),
            "doc_type": leaf.metadata.get("doc_type")
        }

        # Insert document into OpenSearch index
        client.index(
            index=OPENSEARCH_INDEX,
            id=leaf.node_id.replace("-", ""),
            body=doc_body
        )

    client.indices.refresh(index=OPENSEARCH_INDEX)
        
if __name__ == "__main__":
    main()