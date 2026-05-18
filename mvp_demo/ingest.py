import pdfplumber
import chromadb
from sentence_transformers import SentenceTransformer

from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "triple_a_docs"

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
    print("Loading embedding model...")
    embedder = SentenceTransformer("BAAI/bge-base-en-v1.5")
    embedder.max_seq_length = 512

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing collection '{COLLECTION_NAME}'.")
    except Exception:
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    print(f"Created collection '{COLLECTION_NAME}'.")

    print("\nParsing PDFs with pdfplumber...")
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
            "text":             parent_text,
            "child_match_text": leaf.text[:1500],
            "source_url":       leaf.metadata.get("source_url", ""),
            "fund_name":        leaf.metadata.get("fund_name", ""),
            "doc_type":         leaf.metadata.get("doc_type", ""),
        })

    # Batch-embed all leaf nodes in one call — much faster than one-by-one
    print(f"Batch-embedding {len(leaf_texts)} leaf nodes...")
    embeddings = embedder.encode(leaf_texts, batch_size=32, show_progress_bar=True).tolist()

    # Upload to ChromaDB in batches
    print("\nUploading to ChromaDB...")
    batch_size = 100
    for start in range(0, len(ids), batch_size):
        end = start + batch_size
        collection.upsert(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            metadatas=metadatas[start:end]
        )
        print(f"  Upserted {min(end, len(ids))}/{len(ids)}")

    total = collection.count()
    print(f"\n{'=' * 50}")
    print(f"  Leaf nodes:  {len(leaf_nodes)}")
    print(f"  In ChromaDB: {total}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
