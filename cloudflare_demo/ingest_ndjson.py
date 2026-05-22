import os
import json
import time
import requests
import pdfplumber
from dotenv import load_dotenv

from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

load_dotenv("../mvp_demo/.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CF_ACCOUNT_ID  = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CF_API_TOKEN   = os.getenv("CLOUDFLARE_API_TOKEN")
CF_INDEX_NAME  = os.getenv("CLOUDFLARE_VECTORIZE_INDEX", "triple_a_index")

CF_HEADERS   = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/x-ndjson"}
CF_BASE_URL  = (f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
                f"/vectorize/v2/indexes/{CF_INDEX_NAME}")
BATCH_SIZE   = 100
META_BYTE_LIMIT = 10_240  # Cloudflare hard limit per vector

# All PDFs to ingest into the Cloudflare Vectorize index.
# NOTE: after any change here you must clear the index (python ClearIndex) and re-run.
pdfs_to_process = [
    {"filepath": "../Trust_Deed_Sample_Superannuation_Fund.pdf", "fund_name": "Triple A Super",           "doc_type": "Trust Deed"},
    {"filepath": "../deed.pdf",                                   "fund_name": "Summers Family Super Fund", "doc_type": "Deed"},
    {"filepath": "../sample-smsf-trust-deed.pdf",                 "fund_name": "Triple A Super",           "doc_type": "Deed"},
    {"filepath": "../Project_26.pdf",                             "fund_name": "Triple A Super",           "doc_type": "Project Brief"},
    {"filepath": "../Proposal Document.pdf",                      "fund_name": "Triple A Super",           "doc_type": "Development Proposal"},
    {"filepath": "../SIS Act -1.pdf",                             "fund_name": "Triple A Super",           "doc_type": "SIS Act"},
    {"filepath": "../SIS Act Part 2-1.pdf",                       "fund_name": "Triple A Super",           "doc_type": "SIS Act"},
    {"filepath": "../Super-changes-timeline-1.pdf",               "fund_name": "Triple A Super",           "doc_type": "Changelog"},
]


# ── Retry helper ──────────────────────────────────────────────────────────────

def call_with_retry(fn, label, retries=5, base_wait=2):
    """
    Call fn() with exponential-backoff retry on rate-limits and transient errors.
    Raises immediately on 4xx client errors other than 429.
    """
    for attempt in range(retries):
        try:
            return fn()
        except requests.HTTPError as exc:
            code = exc.response.status_code
            if code in (429, 500, 502, 503, 504):
                wait = base_wait * (2 ** attempt)
                print(f"  [{label}] HTTP {code}, retry {attempt + 1}/{retries} in {wait}s...")
                time.sleep(wait)
                if attempt == retries - 1:
                    raise
            else:
                raise
        except (requests.ConnectionError, requests.Timeout):
            if attempt == retries - 1:
                raise
            wait = base_wait * (2 ** attempt)
            print(f"  [{label}] network error, retry {attempt + 1}/{retries} in {wait}s...")
            time.sleep(wait)


# ── Embedding ─────────────────────────────────────────────────────────────────

def get_embedding(text):
    def _call():
        r = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"input": text, "model": "text-embedding-3-small"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]

    return call_with_retry(_call, label="OpenAI embed")


# ── Metadata size guard ───────────────────────────────────────────────────────

def build_safe_metadata(parent_text, leaf_text, source_url, fund_name, doc_type):
    """
    Construct vector metadata that is guaranteed to fit within Cloudflare's
    10 240-byte compact-JSON limit. Progressively trims 'text' if needed.
    """
    meta = {
        "text":            parent_text,
        "child_match_text": leaf_text[:1500],
        "source_url":      source_url or "",
        "fund_name":       fund_name  or "",
        "doc_type":        doc_type   or "",
    }
    # Trim 'text' in 200-char steps until the whole metadata fits
    while len(json.dumps(meta).encode("utf-8")) > META_BYTE_LIMIT:
        cut = max(0, len(meta["text"]) - 200)
        meta["text"] = meta["text"][:cut]
        if cut == 0:
            break
    return meta


# ── Cloudflare upload ─────────────────────────────────────────────────────────

def _do_upsert(vectors):
    """POST a list of vector dicts to the Cloudflare upsert endpoint."""
    body = "\n".join(json.dumps(v) for v in vectors)
    r = requests.post(
        f"{CF_BASE_URL}/upsert",
        data=body.encode("utf-8"),
        headers=CF_HEADERS,
        timeout=60,
    )
    r.raise_for_status()
    resp = r.json()
    if not resp.get("success"):
        raise RuntimeError(f"Cloudflare error: {resp.get('errors')}")
    return len(vectors)


def upload_batch(vectors):
    """
    Upload a batch to Cloudflare with retry.
    If the whole batch is rejected (e.g. one bad record kills it), fall back to
    uploading one vector at a time so the rest of the batch is not lost.
    Returns the count of successfully upserted vectors.
    """
    try:
        return call_with_retry(lambda: _do_upsert(vectors), label="CF batch", base_wait=5)
    except Exception as batch_err:
        print(f"\n    Batch rejected ({batch_err}). Falling back to single-vector uploads...")
        ok = 0
        for vec in vectors:
            try:
                call_with_retry(lambda: _do_upsert([vec]), label="CF single", base_wait=5)
                ok += 1
            except Exception as single_err:
                print(f"    SKIP {vec['id']}: {single_err}")
        return ok


# ── PDF parsing ───────────────────────────────────────────────────────────────

def clean_text(text):
    return " ".join(text.split())


def extract_text_with_tables(pdf_path):
    """
    Extract all text from a PDF using pdfplumber.
    Tables are extracted explicitly and appended in pipe-separated format so
    that tabular values (ages, dates, thresholds) are never silently dropped.
    """
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Parsing PDFs with pdfplumber...")
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
    # 512-token children keep complete legal clauses together;
    # 2048-token parents give the LLM rich surrounding context.
    node_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=[2048, 512])
    nodes      = node_parser.get_nodes_from_documents(documents)
    leaf_nodes = get_leaf_nodes(nodes)
    node_map   = {n.node_id: n for n in nodes}
    print(f"  {len(leaf_nodes)} leaf nodes generated.")

    print("\nEmbedding and uploading vectors...")
    all_vectors = []
    skipped     = 0

    # Write the NDJSON backup file incrementally so partial progress is preserved
    # if the script is interrupted mid-run.
    with open("vectors.ndjson", "w") as ndjson_file:
        for i, leaf in enumerate(leaf_nodes):
            src = leaf.metadata.get("source_url", "?")
            print(f"  [{i + 1}/{len(leaf_nodes)}] {src}...", end=" ", flush=True)

            try:
                embedding = get_embedding(leaf.text)
            except Exception as e:
                print(f"SKIP (embed failed after retries: {e})")
                skipped += 1
                continue

            parent_id  = leaf.parent_node.node_id if leaf.parent_node else None
            parent_node = node_map.get(parent_id)
            parent_text = parent_node.text if parent_node else leaf.text

            metadata = build_safe_metadata(
                parent_text=parent_text,
                leaf_text=leaf.text,
                source_url=leaf.metadata.get("source_url"),
                fund_name=leaf.metadata.get("fund_name"),
                doc_type=leaf.metadata.get("doc_type"),
            )

            vec = {
                "id":     leaf.node_id.replace("-", ""),
                "values": embedding,
                "metadata": metadata,
            }
            all_vectors.append(vec)
            ndjson_file.write(json.dumps(vec) + "\n")
            print("OK")

    print(f"\nEmbedded {len(all_vectors)}/{len(leaf_nodes)} vectors "
          f"({skipped} skipped). Backup saved to vectors.ndjson.")

    # ── Upload to Cloudflare in batches ───────────────────────────────────────
    print(f"\nUploading to Cloudflare Vectorize ({CF_INDEX_NAME})...")
    total_ok = 0
    total_batches = (len(all_vectors) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_start in range(0, len(all_vectors), BATCH_SIZE):
        batch = all_vectors[batch_start : batch_start + BATCH_SIZE]
        bn    = batch_start // BATCH_SIZE + 1
        print(f"  Batch {bn}/{total_batches} ({len(batch)} vectors)...", end=" ", flush=True)
        n = upload_batch(batch)
        total_ok += n
        print(f"OK ({n} upserted)" if n == len(batch) else f"PARTIAL ({n}/{len(batch)} upserted)")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    print(f"  Leaf nodes:       {len(leaf_nodes)}")
    print(f"  Embedded:         {len(all_vectors)}")
    print(f"  In Vectorize:     {total_ok}")
    print(f"  Skipped (errors): {len(leaf_nodes) - len(all_vectors)}")
    if total_ok < len(all_vectors):
        missing = len(all_vectors) - total_ok
        print(f"  WARNING: {missing} vectors failed to upload. "
              f"vectors.ndjson contains all embedded vectors — "
              f"re-run or use: wrangler vectorize insert vectors.ndjson")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
