import os
import re
import hashlib
import pdfplumber
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from pinecone_text.sparse import BM25Encoder
from sentence_transformers import SentenceTransformer

from llama_index.core.node_parser import SentenceSplitter

from ocr_solution import OCR
from pathlib import Path

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

# Cleans extracted PDF text without destroying the document structure
def clean_preserve_structure(text):
    lines = text.split("\n")
    cleaned_lines = [" ".join(line.split()) for line in lines] 
    result_lines = []
    blank_run = 0
    # Removes excessive empty lines 
    for line in cleaned_lines:
        if line == "":
            blank_run += 1
            if blank_run <= 1:
                result_lines.append("")
        else:
            blank_run = 0
            result_lines.append(line)
    return "\n".join(result_lines).strip()

# Returns a unique set of words or numbers that are at least 3 characters long and converted to lowercase
def _extract_words(text):
    return set(re.findall(r"[A-Za-z0-9]{3,}", text.lower()))

# Check whether the table text has already been captured in the normal page text.
# If at least 60% of the table's words are found in the page text, treat it as redundant.
def _table_text_is_redundant(page_text, table_text, overlap_threshold=0.6):
    page_words = _extract_words(page_text)
    table_words = _extract_words(table_text)
    if not table_words:
        return True
    overlap = len(table_words & page_words) / len(table_words)
    return overlap >= overlap_threshold


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
                combined_tables = "\n\n".join(table_parts)
                if not _table_text_is_redundant(page_text, combined_tables):
                    page_text += "\n" + combined_tables
            if page_text.strip():
                all_pages.append(clean_preserve_structure(page_text))
    return "\n\n".join(all_pages)


_HEADING_STATUTE_RE = re.compile(r"^\s*(\d{1,4}[A-Z]{0,3})\s+([A-Z][A-Za-z0-9,'\-\u2013\u2014\s]{2,90})$")
_HEADING_CLAUSE_RE = re.compile(r"^\s*\d{1,3}\.\s+[A-Z][A-Za-z0-9,'\-\u2013\u2014\s]{2,90}:\s*$")

_MIN_HEADINGS_FOR_STRUCTURE = 3
_MIN_PARAGRAPHS_FOR_FALLBACK = 3

# Regex for lines of dots
_DOT_LEADER_RE = re.compile(r"\.{3,}")
# Regex for trailing page numbers (1-4 digits) at the end of a line
_TRAILING_PAGE_NUM_RE = re.compile(r"\b\d{1,4}\s*$")

# Searches for table of contents lines
def looks_like_toc_line(line):
    line = line.strip()
    if not line:
        return False
    if _DOT_LEADER_RE.search(line):
        return True
    if _TRAILING_PAGE_NUM_RE.search(line) and not line.endswith((".", "!", "?")):
        return True
    return False

# Check for uppercase headings with 1-6 words, all uppercase letters, and less than 60 characters 
def _is_all_caps_heading(line):
    words = line.strip().split()
    if not (1 <= len(words) <= 6):
        return False
    letters = [w for w in words if any(c.isalpha() for c in w)]
    if not letters:
        return False
    return all(w.isupper() for w in letters) and len(line.strip()) < 60


# Some TOC entries wrap across two physical lines: the descriptive text
# on one line (no dots, no trailing page number -- so it independently
# matches the heading regex), and the dot-leader + page number on the
# NEXT line. Checking only the current line misses this entirely, since
# the descriptive half genuinely looks like a valid heading in isolation.
# This peeks at the next line and, if IT looks like a TOC continuation,
# treats the current line as part of the same TOC entry rather than a
# real heading.
def _next_line_is_toc_continuation(lines, index):
    for j in range(index + 1, min(index + 2, len(lines))):
        nxt = lines[j].strip()
        if not nxt:
            continue
        return looks_like_toc_line(nxt)
    return False


def is_heading_line(lines, index):
    line = lines[index].strip()
    if not line or len(line) > 100:
        return False
    if line.endswith((",", ";")):
        return False
    if looks_like_toc_line(line):
        return False
    if _next_line_is_toc_continuation(lines, index):
        return False
    if _HEADING_STATUTE_RE.match(line):
        return True
    if _HEADING_CLAUSE_RE.match(line):
        return True
    if _is_all_caps_heading(line):
        return True
    return False


def section_toc(section_text, threshold=0.6, short_section_len=400):
    lines = [l for l in section_text.split("\n") if l.strip()]
    if not lines:
        return True
    toc_lines = sum(1 for l in lines if looks_like_toc_line(l))
    ratio = toc_lines / len(lines)
    if ratio >= threshold:
        return True
    if len(section_text) <= short_section_len and toc_lines >= 1:
        return True
    return False


def split_into_sections(text):
    lines = text.split("\n")
    boundaries = [i for i, line in enumerate(lines) if is_heading_line(lines, i)]

    if len(boundaries) >= _MIN_HEADINGS_FOR_STRUCTURE:
        sections = []
        if boundaries[0] > 0:
            preamble = "\n".join(lines[: boundaries[0]]).strip()
            if preamble:
                sections.append(preamble)
        for idx, start in enumerate(boundaries):
            end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(lines)
            section = "\n".join(lines[start:end]).strip()
            if section:
                sections.append(section)
        return sections

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) >= _MIN_PARAGRAPHS_FOR_FALLBACK:
        return paragraphs

    stripped = text.strip()
    return [stripped] if stripped else []


PARENT_MAX_CHARS = 1500          
PARENT_SUBSPLIT_TOKENS = 380     
PARENT_SUBSPLIT_OVERLAP = 40

LEAF_CHUNK_TOKENS = 130          
LEAF_OVERLAP_TOKENS = 20

_parent_splitter = SentenceSplitter(chunk_size=PARENT_SUBSPLIT_TOKENS, chunk_overlap=PARENT_SUBSPLIT_OVERLAP)
_leaf_splitter = SentenceSplitter(chunk_size=LEAF_CHUNK_TOKENS, chunk_overlap=LEAF_OVERLAP_TOKENS)


_SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]?\s")


def trim_to_sentence_boundary(text, max_len):
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    matches = list(_SENTENCE_END_RE.finditer(truncated))
    if matches:
        cut = matches[-1].end()
        if cut >= max_len * 0.5:  
            return truncated[:cut].strip()
    return truncated.strip()


def build_section_based_chunks(full_text, base_metadata):
    sections = split_into_sections(full_text)
    entries = []

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if section_toc(section):
            continue

        if len(section) <= PARENT_MAX_CHARS:
            parent_chunks = [section]
        else:
            parent_chunks = _parent_splitter.split_text(section)

        for parent_text in parent_chunks:
            parent_text = parent_text.strip()
            if not parent_text:
                continue

            if section_toc(parent_text):
                continue

            leaves = _leaf_splitter.split_text(parent_text)
            if not leaves:
                leaves = [parent_text]

            for leaf_text in leaves:
                leaf_text = leaf_text.strip()
                if not leaf_text:
                    continue
                if section_toc(leaf_text):
                    continue
                entries.append({
                    "leaf_text": leaf_text,
                    "parent_text": parent_text,
                    **base_metadata,
                })

    return entries


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