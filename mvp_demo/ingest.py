import os
import hashlib
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from pinecone_text.sparse import BM25Encoder
from sentence_transformers import SentenceTransformer


from ocr_solution import OCR
from chunking import (
    extract_text_with_tables,
    build_section_based_chunks,
    trim_to_sentence_boundary,
)
from pathlib import Path

load_dotenv("secrets.env")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "fit4002-pinecone-index")
EMBEDDING_DIM = 768
# Fitted BM25 encoder is saved here during ingest and loaded by views_pinecone.py at query time
BM25_ENCODER_PATH = os.getenv("BM25_ENCODER_PATH", "bm25_encoder.json")

pc = Pinecone(api_key=PINECONE_API_KEY)

pdfs_to_process = [
    {"filepath": "../Trust_Deed_Sample_Superannuation_Fund.pdf", "fund_name": "Sample Superannuation Fund",            "doc_type": "Trust Deed"},
    {"filepath": "../deed.pdf",                                   "fund_name": "Summers Family Super Fund", "doc_type": "Trust Deed"},
    {"filepath": "../sample-smsf-trust-deed.pdf",                 "fund_name": "Ausis Super Fund",            "doc_type": "Trust Deed"},
    {"filepath": "../Project_26.pdf",                             "fund_name": "Triple A Super",            "doc_type": "Project Brief"},
    {"filepath": "../Proposal Document.pdf",                      "fund_name": "Triple A Super",            "doc_type": "Development Proposal"},
    {"filepath": "../SIS Act -1.pdf",                             "fund_name": "General",            "doc_type": "legal"},
    {"filepath": "../SIS Act Part 2-1.pdf",                       "fund_name": "General",            "doc_type": "legal"},
    {"filepath": "../Super-changes-timeline-1.pdf",               "fund_name": "General",            "doc_type": "Changelog"},
]

# Cleans extracted PDF text without destroying the document structure


def main():
    print("Loading OCR model...")
    ocr = OCR()

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

    print("\nParsing + chunking PDFs...")
    all_entries = []
    for pdf_info in pdfs_to_process:
        print(f"  {pdf_info['filepath']}...", end=" ", flush=True)
        try:
            full_text = ocr.output_document(Path(pdf_info["filepath"]))
            if not full_text:
                full_text = extract_text_with_tables(pdf_info["filepath"])
        except Exception as e:
            print(f"ERROR: {e}")
            continue
        if not full_text.strip():
            print("WARNING: no text extracted, skipped.")
            continue

        base_metadata = {
            "source_url": pdf_info["filepath"].split("/")[-1],
            "fund_name":  pdf_info["fund_name"],
            "doc_type":   pdf_info["doc_type"],
        }
        entries = build_section_based_chunks(full_text, base_metadata)
        all_entries.extend(entries)
        print(f"{len(full_text):,} chars -> {len(entries)} leaf chunks")

    print(f"\nTotal leaf chunks across all documents: {len(all_entries)}")

    # Build metadata list and collect leaf texts for batch embedding
    print("\nPreparing metadata...")
    leaf_texts = []
    ids = []
    metadatas = []

    for entry in all_entries:
        leaf_text = entry["leaf_text"]
        parent_text = entry["parent_text"]

        doc_id = hashlib.md5(
            (entry["source_url"] + "::" + leaf_text[:120]).encode("utf-8")
        ).hexdigest()

        ids.append(doc_id)
        leaf_texts.append(leaf_text)
        metadatas.append({
            "text": trim_to_sentence_boundary(parent_text, 1500),
            "child_match_text": trim_to_sentence_boundary(leaf_text, 800),
            "source_url": entry["source_url"],
            "fund_name": entry["fund_name"],
            "doc_type": entry["doc_type"],
        })

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