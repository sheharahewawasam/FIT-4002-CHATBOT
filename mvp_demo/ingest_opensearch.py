import os
import pdfplumber
import boto3
 
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
from sentence_transformers import SentenceTransformer
 
# Import LlamaIndex components
from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

load_dotenv("secrets.env")

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "fit4002-opensearch-index")
EMBEDDING_DIM = 768

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
    {"filepath": "../Trust_Deed_Sample_Superannuation_Fund.pdf", "fund_name": "Triple A Super",            "doc_type": "Trust Deed"},
    {"filepath": "../deed.pdf",                                   "fund_name": "Summers Family Super Fund", "doc_type": "Deed"},
    {"filepath": "../sample-smsf-trust-deed.pdf",                 "fund_name": "Triple A Super",            "doc_type": "Deed"},
    {"filepath": "../Project_26.pdf",                             "fund_name": "Triple A Super",            "doc_type": "Project Brief"},
    {"filepath": "../Proposal Document.pdf",                      "fund_name": "Triple A Super",            "doc_type": "Development Proposal"},
    {"filepath": "../SIS Act -1.pdf",                             "fund_name": "Triple A Super",            "doc_type": "SIS Act"},
    {"filepath": "../SIS Act Part 2-1.pdf",                       "fund_name": "Triple A Super",            "doc_type": "SIS Act"},
    {"filepath": "../Super-changes-timeline-1.pdf",               "fund_name": "Triple A Super",            "doc_type": "Changelog"},
]

def clean_text(text):
    return " ".join(text.split())

def extract_text_with_tables(pdf_path):
    all_pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            table_parts = []
            for table in (page.extract_tables() or []):
                rows = []
                for row in (table or []):
                    if row:
                        cells = [str(c).strip() if c is not None else "" for c in row]
                        if any(cells):
                            rows.append(" | ".join(cells))
                if rows:
                    table_parts.append("\n".join(rows))
            if table_parts:
                page_text += "\n" + "\n\n".join(table_parts)
            if page_text.strip():
                all_pages.append(clean_text(page_text))
    return "\n".join(all_pages)

def create_index_if_needed():
    # Check if index already exists
    if client.indices.exists(index=OPENSEARCH_INDEX):
        print("OpenSearch index already exists.")
        return

    # Define index structure (schema)
    index_body = {
        "settings": {
            "index": {
                "knn": True, # enable semantic search
                "knn.algo_param.ef_search": 100,
            }
        },
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "knn_vector", # stores embeddings
                    "dimension": EMBEDDING_DIM, # match with the embeddign model
                    "method": {
                        "name": "hnsw", # fast search algorithm
                        "space_type": "cosinesimil", # cosine similarity
                        "engine": "faiss", # vector search engine
                        "parameters": {"ef_construction": 128, "m": 24},
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

def setup_hybrid_pipeline():
    """
    Create the hybrid search pipeline on the OpenSearch cluster (once only).
    This tells OpenSearch how to normalise and combine BM25 + KNN scores
    so that the hybrid query in views_opensearch.py returns meaningful rankings.

    Weights: [knn=0.7, bm25=0.3] — matches the query order (knn first, multi_match second).
    Adjust weights here if retrieval quality needs tuning.
    """
    pipeline_id = "hybrid-search-pipeline"

    # Check if already exists to avoid overwriting a production pipeline
    try:
        existing = client.transport.perform_request("GET", f"/_search/pipeline/{pipeline_id}")
        print(f"Hybrid search pipeline '{pipeline_id}' already exists — skipping.")
        return
    except Exception:
        pass  # 404 means it doesn't exist yet — proceed to create

    pipeline_body = {
        "description": "Normalise and combine KNN (semantic) + BM25 (keyword) scores",
        "phase_results_processors": [
            {
                "normalization-processor": {
                    "normalization": {
                        "technique": "min_max"   # scale each leg's scores to [0, 1]
                    },
                    "combination": {
                        "technique": "arithmetic_mean",
                        "parameters": {
                            # Order must match hybrid query: [knn_weight, bm25_weight]
                            "weights": [0.7, 0.3]
                        }
                    }
                }
            }
        ]
    }

    client.transport.perform_request(
        "PUT",
        f"/_search/pipeline/{pipeline_id}",
        body=pipeline_body
    )
    print(f"Created hybrid search pipeline '{pipeline_id}'.")


def main():
    create_index_if_needed()
    setup_hybrid_pipeline()

    print("Loading embedding model (BAAI/bge-base-en-v1.5)...")
    embedder = SentenceTransformer("BAAI/bge-base-en-v1.5")
    embedder.max_seq_length = 512
    
    print("\nParsing PDFs...")
    documents = []

    for pdf_info in pdfs_to_process:
        print(f"  {pdf_info['filepath']}...", end=" ", flush=True)
        try:
            full_text = extract_text_with_tables(pdf_info["filepath"])
        except Exception as e:
            print(f"ERROR: {e}")
            continue
        if not full_text.strip():
            print("WARNING: no text extracted, skipped.")
            continue
        print(f"{len(full_text):,} chars")
        documents.append(Document(
            text=full_text,
            metadata={
                "source_url": pdf_info["filepath"].split("/")[-1],
                "fund_name": pdf_info["fund_name"],
                "doc_type": pdf_info["doc_type"],
            },
        ))

    print(f"\nChunking {len(documents)} documents...")
    node_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=[2048, 512])
    nodes       = node_parser.get_nodes_from_documents(documents)
    leaf_nodes  = get_leaf_nodes(nodes)
    node_map    = {n.node_id: n for n in nodes}
    print(f"  {len(leaf_nodes)} leaf nodes generated.")

    print("\nPreparing metadata...")
    ids         = []
    leaf_texts  = []
    metadatas   = []
    
    # Store embeddings into OpenSearch
    for leaf in leaf_nodes:
        parent_id   = leaf.parent_node.node_id if leaf.parent_node else None
        parent_node = node_map.get(parent_id)
        parent_text = parent_node.text if parent_node else leaf.text
 
        ids.append(leaf.node_id.replace("-", ""))
        leaf_texts.append(leaf.text)
        metadatas.append({
            "text":             parent_text[:1500],
            "child_match_text": leaf.text[:800],
            "source_url":       leaf.metadata.get("source_url", ""),
            "fund_name":        leaf.metadata.get("fund_name", ""),
            "doc_type":         leaf.metadata.get("doc_type", ""),
        })

    print(f"\nBatch-embedding {len(leaf_texts)} leaf nodes...")
    embeddings = embedder.encode(
        leaf_texts,
        batch_size=32,
        show_progress_bar=True,
    ).tolist()

    print("\nUploading to OpenSearch...")
    batch_size = 100
    for start in range(0, len(ids), batch_size):
        end   = start + batch_size
        batch_ids   = ids[start:end]
        batch_embs  = embeddings[start:end]
        batch_metas = metadatas[start:end]
 
        # Build bulk request body
        bulk_body = []
        for doc_id, emb, meta in zip(batch_ids, batch_embs, batch_metas):
            bulk_body.append({"index": {"_index": OPENSEARCH_INDEX, "_id": doc_id}})
            bulk_body.append({
                "embedding":        emb,
                "text":             meta["text"],
                "child_match_text": meta["child_match_text"],
                "source_url":       meta["source_url"],
                "fund_name":        meta["fund_name"],
                "doc_type":         meta["doc_type"],
            })
 
        response = client.bulk(body=bulk_body)
        if response.get("errors"):
            print(f"  ⚠️  Some errors in batch {start // batch_size + 1} — check OpenSearch logs.")
        else:
            print(f"  Upserted {min(end, len(ids))}/{len(ids)}")
 
    client.indices.refresh(index=OPENSEARCH_INDEX)
    print(f"\nIngestion complete — {len(ids)} vectors in '{OPENSEARCH_INDEX}'.")
        
if __name__ == "__main__":
    main()