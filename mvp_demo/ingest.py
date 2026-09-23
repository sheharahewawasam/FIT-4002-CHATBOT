from chunking.toc_filter import (
    _TOC_ENTRY_RE,
    _TOC_DOTTED_LINE_RE,
    _TOC_TRAILING_PAGE_RE,
    _TOC_TITLE_RE,
    _TOC_PAGE_RE,
    _body_block_start,
    _find_toc_region_end,
    _has_body_text_after,
    _normalise_toc_label,
    _toc_entry_label,
    looks_like_toc_line,
    remove_toc_regions
)
import os
import re
import hashlib
import pdfplumber
import json
import warnings
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from pinecone_text.sparse import BM25Encoder
from sentence_transformers import SentenceTransformer
from datetime import datetime


from ocr_solution import OCR
from chunking.extraction import (
    clean_preserve_structure, extract_text_with_tables, _table_text_is_redundant,
)
from pathlib import Path
from chunking.header_chunking import (
    build_header_based_chunks, build_section_based_chunks,
    split_into_sections, is_heading_line, trim_to_sentence_boundary,
    _MIN_HEADINGS_FOR_STRUCTURE, _MIN_PARAGRAPHS_FOR_FALLBACK,
)
from chunking.toc_filter import section_toc
from chunking.layout_chunking import (
    is_layout_output, normalise_ocr_output, build_layout_snapshot,
    build_layout_aware_chunks,
)

load_dotenv("secrets.env")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "fit4002-pinecone-index")
EMBEDDING_DIM = 768
# Fitted BM25 encoder is saved here during ingest and loaded by views_pinecone.py at query time
BM25_ENCODER_PATH = os.getenv("BM25_ENCODER_PATH", "bm25_encoder.json")

# Pinecone is constructed in main(), never while importing chunking functions.

def parse_document_date(date_str, fmt="%d %B %Y"):
    """
    Return (display, numeric) for a document date, or (None, None) if unknown.

    Most entries below have no verified date yet. An unknown date must stay
    unknown: stamping a placeholder makes every document look like it was
    written on the same day, and a date-range filter built on that silently
    returns the wrong documents rather than none.
    """
    if not date_str:
        return None, None
    dt = datetime.strptime(date_str, fmt)
    return dt.strftime("%Y-%m-%d"), int(dt.strftime("%Y%m%d"))

pdfs_to_process = [
    {"filepath": "../pdfs/Trust_Deed_Sample_Superannuation_Fund.pdf",                                                                        "fund_name": "Sample Superannuation Fund",         "doc_type": "Trust Deed",                            "date": None},
    {"filepath": "../pdfs/deed.pdf",                                                                                                         "fund_name": "Summers Family Super Fund",          "doc_type": "Trust Deed",                            "date": None},
    {"filepath": "../pdfs/sample-smsf-trust-deed.pdf",                                                                                       "fund_name": "Ausis Super Fund",                   "doc_type": "Trust Deed",                            "date": None},
    {"filepath": "../pdfs/Project_26.pdf",                                                                                                   "fund_name": "Triple A Super",                     "doc_type": "Project Brief",                         "date": None},
    {"filepath": "../pdfs/Proposal Document.pdf",                                                                                             "fund_name": "Triple A Super",                     "doc_type": "Development Proposal",                  "date": None},
    {"filepath": "../pdfs/SIS Act -1.pdf",                                                                                                   "fund_name": "General",                            "doc_type": "legal",                                 "date": None},
    {"filepath": "../pdfs/SIS Act Part 2-1.pdf",                                                                                              "fund_name": "General",                            "doc_type": "legal",                                 "date": None},
    {"filepath": "../pdfs/Super-changes-timeline-1.pdf",                                                                                     "fund_name": "General",                            "doc_type": "Changelog",                             "date": None},
    {"filepath": "../pdfs/Investment Strategy.pdf",                                                                                          "fund_name": "A and C Super Fund",                 "doc_type": "Investment Strategy",                   "date": None},
    {"filepath": "../pdfs/A and C SF  - FY2024 Audit Report_unlocked.pdf",                                                                   "fund_name": "A and C Super Fund",                 "doc_type": "Signed Financials and Tax Returns",     "date": None},
    {"filepath": "../pdfs/A and C SF - FY2024 Management Letter_unlocked.pdf",                                                               "fund_name": "A and C Super Fund",                 "doc_type": "Signed Financials and Tax Returns",     "date": None},
    {"filepath": "../pdfs/A and C SF - Signed 2024 Financials_unlocked.pdf",                                                                 "fund_name": "A and C Super Fund",                 "doc_type": "Signed Financials and Tax Returns",     "date": None},
    {"filepath": "../pdfs/A and C Super Fund - Deed of Amendment & Consolidation (signed) 23.07.2017_unlocked.pdf",                          "fund_name": "A and C Super Fund",                 "doc_type": "Trust Deed",                            "date": "23 July 2017"},
    {"filepath": "../pdfs/A and C Super Fund Trust Deed 14.11.2016_unlocked.pdf",                                                            "fund_name": "A and C Super Fund",                 "doc_type": "Trust Deed",                            "date": "14 November 2016"},
    {"filepath": "../pdfs/3_0 Investment Strategy and Trustee Minutes 2015.pdf",                                                             "fund_name": "Andres Family Superannuation Fund",  "doc_type": "Investment Strategy",                   "date": None},
    {"filepath": "../pdfs/Andres Family Superannuation Fund Trust Deed 09.07.2015.pdf",                                                      "fund_name": "Andres Family Superannuation Fund",  "doc_type": "Trust Deed",                            "date": "9 July 2015"},
    {"filepath": "../pdfs/Bellenger Family Superannuation Fund (VIC400BELLEN) - 2023 Signed AUDITED Financials & Annual Return.pdf",    "fund_name": "Bell Family Superannuation Fund",    "doc_type": "Signed Financials and Tax Returns",     "date": None},
    {"filepath": "../pdfs/1. SMSF Deed of Variation.pdf",                                                                                    "fund_name": "Bell Family Superannuation Fund",    "doc_type": "Trust Deed",                            "date": None},
    {"filepath": "../pdfs/Signed_2023_Annual_Return_NOT_AUDITED[1]_unlocked.pdf",                                                            "fund_name": "Bell Family Superannuation Fund",    "doc_type": "SMSF Annual Return",                    "date": None},
    {"filepath": "../pdfs/DARTO Super Fund (NSW400DART) - 2023 Signed AUDITED Financials & Annual Return.pdf",                               "fund_name": "Darto Super Fund",                   "doc_type": "Signed Financials and Tax Returns",     "date": None},
    {"filepath": "../pdfs/DARTO Super Fund (NSW400DART) - 2024 Signed AUDITED Financials & Annual Return.pdf",                               "fund_name": "Darto Super Fund",                   "doc_type": "Signed Financials and Tax Returns",     "date": None},
    {"filepath": "../pdfs/20111122 - Original Trust Deed.pdf",                                                                               "fund_name": "Darto Super Fund",                   "doc_type": "Trust Deed",                            "date": "22 November 2011"},
    {"filepath": "../pdfs/20111122 - Trust Deed (Signed Pages Only).pdf",                                                                    "fund_name": "Darto Super Fund",                   "doc_type": "Trust Deed",                            "date": "22 November 2011"},
    {"filepath": "../pdfs/Unsigned 2024 Annual Return.pdf",                                                                                  "fund_name": "Darto Super Fund",                   "doc_type": "SMSF Annual Return",                    "date": None},
    {"filepath": "../pdfs/Powell - SMSF Investment Strategy 2020.pdf",                                                                       "fund_name": "Powell Superannuation Fund",         "doc_type": "Investment Strategy",                   "date": None},
    {"filepath": "../pdfs/Powell SF - Amended Trust Deed 27.04.2020.pdf",                                                                    "fund_name": "Powell Superannuation Fund",         "doc_type": "Trust Deed",                            "date": "27 April 2020"},
]

# Cleans extracted PDF text without destroying the document structure
def extract_document_content(pdf_path, ocr=None):
    """Accept existing text output or a validated layout JSON response.

    The teammate's adapter should return one page dict, a list of page dicts,
    or {"pages": [...]}. No assumed new OCR method is required.
    """
    try:
        if ocr is None:
            ocr = OCR()
        result = ocr.output_document(Path(pdf_path))
    except Exception as exc:
        warnings.warn(f"OCR failed for {pdf_path}: {exc}; trying PDF text extraction.")
        return extract_text_with_tables(pdf_path)
    if isinstance(result, str):
        if not result.strip():
            return extract_text_with_tables(pdf_path)
        if result.lstrip().startswith(("{", "[")):
            # Do not accidentally embed JSON keys/coordinates or silently flatten
            # a malformed structured response. The offline CLI reports bad JSON too.
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                if 'parsing_res_list' in result or '"pages"' in result:
                    raise ValueError("OCR returned malformed/truncated layout JSON")
            else:
                if is_layout_output(parsed):
                    return parsed
        return result
    if is_layout_output(result):
        return result
    raise ValueError("Unsupported OCR output type; update the OCR adapter before ingestion")


def extract_document_text(pdf_path, ocr=None):
    """Compatibility for existing PDF-based metrics; layout evaluation uses snapshots."""
    result = extract_document_content(pdf_path, ocr)
    if isinstance(result, str):
        return result
    return "\n\n".join(b.text for b in normalise_ocr_output(result))


def save_chunk_snapshot(pdf_path, full_text, entries, rejected_chunks, layout_snapshot=None):
    """Save the exact pre-upload text and entries for reproducible evaluation."""
    directory = Path("test_chunking_output") / "snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    suffix = hashlib.sha256(str(Path(pdf_path).resolve()).encode()).hexdigest()[:10]
    target = directory / f"{Path(pdf_path).stem}_{suffix}_chunks.json"
    target.write_text(json.dumps({
        **(layout_snapshot or {}),
        "schema_version": 2 if layout_snapshot else 1,
        "source_path": str(pdf_path),
        "full_text": full_text,
        "entries": entries,
        "rejected_chunks": rejected_chunks,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main():
    pc = Pinecone(api_key=PINECONE_API_KEY)

    print("Loading OCR model...")
    try:
        ocr = OCR()
    except Exception as exc:
        warnings.warn(f"OCR initialization failed: {exc}; PDF extraction will be attempted.")
        ocr = None

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
            # Optional sidecar lets you test/use saved OCR without changing OCR().
            if pdf_info.get("ocr_json_path"):
                document_content = json.loads(Path(pdf_info["ocr_json_path"]).read_text(encoding="utf-8-sig"))
            else:
                document_content = extract_document_content(pdf_info["filepath"], ocr=ocr)
        except Exception as e:
            print(f"ERROR: {e}")
            continue
        if isinstance(document_content, str) and not document_content.strip():
            print("WARNING: no text extracted, skipped.")
            continue

        date_display, date_numeric = parse_document_date(pdf_info["date"])

        base_metadata = {
            "source_url":   pdf_info["filepath"].split("/")[-1],
            "fund_name":    pdf_info["fund_name"],
            "doc_type":     pdf_info["doc_type"],
        }
        # Omitted when unknown. A vector with no date_numeric is excluded by a
        # date-range filter, which is the honest answer for an undated document.
        if date_display is not None:
            base_metadata["date"] = date_display
            base_metadata["date_numeric"] = date_numeric
        rejected_chunks = []
        layout_snapshot = None
        try:
            if is_layout_output(document_content):
                layout_snapshot = build_layout_snapshot(
                    document_content, base_metadata,
                    toc_filter=remove_toc_regions,
                )
                full_text = layout_snapshot["full_text"]
                entries = layout_snapshot["entries"]
                rejected_chunks = layout_snapshot["rejected_chunks"]
                for note in layout_snapshot["layout_diagnostics"]:
                    print(f"\n  Layout review: {note}")
            elif isinstance(document_content, str):
                full_text = document_content
                entries = build_header_based_chunks(full_text, base_metadata, rejected_chunks)
            else:
                raise ValueError("Unsupported OCR JSON schema")
        except (ValueError, TypeError) as exc:
            # Invalid/incomplete structured OCR must not silently ingest only page 1.
            raise RuntimeError(f"Layout ingestion failed for {pdf_info['filepath']}: {exc}") from exc
        snapshot = save_chunk_snapshot(pdf_info["filepath"], full_text, entries, rejected_chunks, layout_snapshot)
        print(f"\n  Audit snapshot: {snapshot} ({len(rejected_chunks)} blocks removed)")
        all_entries.extend(entries)
        print(f"{len(full_text):,} chars -> {len(entries)} leaf chunks")

    print(f"\nTotal leaf chunks across all documents: {len(all_entries)}")

    if not all_entries:
        raise RuntimeError("No chunks produced; embedding and BM25 fitting aborted.")

    # Build metadata list and collect leaf texts for batch embedding
    print("\nPreparing metadata...")
    leaf_texts = []
    ids = []
    metadatas = []

    for entry in all_entries:
        leaf_text = entry["leaf_text"]
        parent_text = entry["parent_text"]

        # Layout IDs include block occurrence: identical answers on different pages
        # must not overwrite each other. Retain legacy IDs for existing text chunks.
        if entry.get("chunking_method") == "layout_aware":
            doc_id = hashlib.sha256(
                (entry["source_url"] + "::" + entry["chunk_id"]).encode("utf-8")
            ).hexdigest()
        else:
            doc_id = hashlib.md5(
                (entry["source_url"] + "::" + leaf_text[:120]).encode("utf-8")
            ).hexdigest()

        ids.append(doc_id)
        leaf_texts.append(leaf_text)
        metadatas.append({
            "text": parent_text,
            "child_match_text": leaf_text,
            "source_url": entry["source_url"],
            "fund_name": entry["fund_name"],
            "doc_type": entry["doc_type"],
        })
        if entry.get("date") is not None:
            metadatas[-1]["date"] = entry["date"]
            metadatas[-1]["date_numeric"] = entry["date_numeric"]
        if entry.get("chunking_method") == "layout_aware":
            # Keep only scalar/list-of-string metadata in Pinecone. Full bbox
            # objects remain in snapshots; they are not embedding input.
            for key in ("chunking_method", "section_title", "parent_id", "chunk_id",
                        "page_start", "page_end", "parent_page_start", "parent_page_end",
                        "block_ids", "oversized_child"):
                metadatas[-1][key] = entry[key]
            metadatas[-1]["layout_sources_json"] = json.dumps(entry["layout_sources"])


    # Atomic form/table units can exceed the soft character budget. Fail explicitly
    # instead of letting the embedding model silently truncate important values.
    for entry in all_entries:
        if entry.get("chunking_method") == "layout_aware":
            token_ids = embedder.tokenizer(entry["leaf_text"], truncation=False)["input_ids"]
            if len(token_ids) > embedder.max_seq_length:
                raise ValueError(
                    f"Layout chunk {entry['chunk_id']} exceeds the embedding limit "
                    f"({len(token_ids)} > {embedder.max_seq_length} tokens). "
                    "Review/split the oversized field or table row before upload."
                )

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
    vectors = []

    for doc_id, emb, sparse, meta in zip(
        ids, 
        embeddings,
        sparse_embeddings,
        metadatas
    ):
        vector = {
            "id": doc_id,
            "values": emb,
            "metadata": meta
        }

        if (sparse and sparse.get("indices") and sparse.get("values")):
            vector["sparse_values"] = sparse

        vectors.append(vector)

    empty_sparse_count = 0
    
    for i, sparse in enumerate(sparse_embeddings):
        if not sparse.get("values"):
            empty_sparse_count += 1
            print(f"\nEmpty sparse vector #{empty_sparse_count}")
            print(f"Source: {metadatas[i]['source_url']}")
            print(f"Leaf: {leaf_texts[i]!r}")

    print(f"\nTotal empty sparse vectors: {empty_sparse_count}")

    for start in range(0, len(vectors), batch_size):
        batch = vectors[start : start + batch_size]
        index.upsert(vectors=batch)
        print(f"Upserted {min(start + batch_size, len(vectors))}/{len(vectors)}")

    print(f"\nIngestion complete — {len(vectors)} vectors in '{PINECONE_INDEX_NAME}'.")

if __name__ == "__main__":
    main()