import os
import pdfplumber
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from pinecone_text.sparse import BM25Encoder
from sentence_transformers import SentenceTransformer

from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

from ocr_solution import OCR
from pathlib import Path

CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "triple_a_docs"
load_dotenv("secrets.env")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "fit4002-pinecone-index")
EMBEDDING_DIM = 768
# Fitted BM25 encoder is saved here during ingest and loaded by views_pinecone.py at query time
BM25_ENCODER_PATH = os.getenv("BM25_ENCODER_PATH", "bm25_encoder.json")

pc = Pinecone(api_key=PINECONE_API_KEY)

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


def main():
    # Create index if it doesn't exist
    if not pc.has_index(PINECONE_INDEX_NAME):
        print(f"Creating Pinecone index '{PINECONE_INDEX_NAME}'...")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBEDDING_DIM,
            metric="dotproduct",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    else:
        print(f"Index '{PINECONE_INDEX_NAME}' already exists, skipping creation.")
 
    index = pc.Index(PINECONE_INDEX_NAME)
 
    # Load BGE model once — used for all embeddings
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
                "fund_name":  pdf_info["fund_name"],
                "doc_type":   pdf_info["doc_type"],
            },
        ))

    print(f"\nChunking {len(documents)} documents...")
    node_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=[2048, 512])
    nodes      = node_parser.get_nodes_from_documents(documents)
    leaf_nodes = get_leaf_nodes(nodes)
    node_map   = {n.node_id: n for n in nodes}
    print(f"  {len(leaf_nodes)} leaf nodes generated.")

    # Build metadata list and collect leaf texts for batch embedding
    print("\nPreparing metadata...")
    leaf_texts  = []
    ids         = []
    metadatas   = []

    for leaf in leaf_nodes:
        parent_id   = leaf.parent_node.node_id if leaf.parent_node else None
        parent_node = node_map.get(parent_id)
        parent_text = parent_node.text if parent_node else leaf.text
 
        ids.append(leaf.node_id.replace("-", ""))
        leaf_texts.append(leaf.text)
        metadatas.append({
            "text": parent_text[:1500], # broad parent context for the LLM
            "child_match_text": leaf.text[:800], # precise leaf chunk for reranking
            "source_url": leaf.metadata.get("source_url", ""),
            "fund_name": leaf.metadata.get("fund_name", ""),
            "doc_type": leaf.metadata.get("doc_type", ""),
        })
 
    # Batch-embed all leaf nodes in one call — much faster than one-by-one 
    print(f"\nBatch-embedding {len(leaf_texts)} leaf nodes...")
    embeddings = embedder.encode(
        leaf_texts,
        batch_size=32,
        show_progress_bar=True,
    ).tolist()

    # Fit BM25 encoder on the same leaf texts used for dense embeddings.
    print(f"\nFitting BM25 encoder on {len(leaf_texts)} documents...")
    bm25 = BM25Encoder()
    bm25.fit(leaf_texts)
    bm25.dump(BM25_ENCODER_PATH)
    print(f"BM25 encoder saved to '{BM25_ENCODER_PATH}'.")

    # Encode sparse vectors for all leaf texts in one pass
    print("Encoding sparse vectors...")
    sparse_embeddings = bm25.encode_documents(leaf_texts)
 
    # Upsert into Pinecone in batches of 100
    # Each vector carries both dense (semantic) and sparse (BM25 keyword) representations.
    print("\nUploading to Pinecone...")
    batch_size = 100
    vectors = [
        {"id": doc_id, "values": emb, "sparse_values": sparse, "metadata": meta}
        for doc_id, emb, sparse, meta in zip(ids, embeddings, sparse_embeddings, metadatas)
    ]
 
    for start in range(0, len(vectors), batch_size):
        batch = vectors[start : start + batch_size]
        index.upsert(vectors=batch)
        print(f"Upserted {min(start + batch_size, len(vectors))}/{len(vectors)}")
 
    print(f"\nIngestion complete — {len(vectors)} vectors in '{PINECONE_INDEX_NAME}'.")

if __name__ == "__main__":
    main()