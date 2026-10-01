"""
Per-document ingestion for user uploads.

Mirrors the bulk pipeline in ingest.py (extract -> section chunk -> embed ->
BM25 -> upsert) but for a single uploaded file, and records progress on the
Document row so the UI can poll it.

Two deliberate differences from the bulk script:

* BM25 is not refit. A refit needs every chunk in the corpus, which is not
  stored anywhere, and would require reloading the encoder in the running
  process. The already-fitted encoder can still encode new documents, so it is
  reused. Terms unique to uploaded documents therefore carry no IDF weight
  until someone reruns ingest.py for a full refit.
* Vector ids are namespaced by document id, so two advisors uploading the same
  file do not collide, and deleting a document can remove exactly its vectors.
"""
import hashlib
import logging
import threading
import traceback

from django.db import connection

from chunking.extraction import extract_text_with_tables
from chunking.header_chunking import build_section_based_chunks, trim_to_sentence_boundary

from . import resources
from .models import Document

logger = logging.getLogger(__name__)

UPSERT_BATCH_SIZE = 100
PARENT_METADATA_CHARS = 1500
LEAF_METADATA_CHARS = 800


# A page yielding less than this is treated as having no usable text layer.
# Matches the threshold the OCR module used before its rewrite.
MIN_CHARS_PER_PAGE = 50


def _text_is_adequate(text, page_count):
    """Whether pdfplumber got enough out of the PDF to be worth keeping."""
    if page_count <= 0:
        return bool(text and text.strip())
    return len((text or "").strip()) >= MIN_CHARS_PER_PAGE * page_count * 0.1


def _extract_text(pdf_path):
    """
    Get text out of a PDF, using OCR only when the text layer is inadequate.

    Extraction runs first and OCR is the fallback, rather than the other way
    round. That ordering matters on two counts: OCR costs minutes per document
    on this hardware, and it replaces the whole document, so running it on a
    file that is 90% cleanly extractable trades good text for OCR output to
    recover one page.

    ocr_solution imports paddleocr, pymupdf, chonkie and ollama at module level,
    none of which are guaranteed to be installed, so OCR stays optional and a
    missing package means pdfplumber alone.
    """
    plain = extract_text_with_tables(str(pdf_path))

    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            page_count = len(pdf.pages)
    except Exception:
        page_count = 0

    if _text_is_adequate(plain, page_count):
        return plain

    logger.info("Text layer is thin (%d chars over %d pages); trying OCR",
                len((plain or "").strip()), page_count)

    try:
        from ocr_solution import OCR
    except Exception as exc:
        logger.info("OCR unavailable (%s); using what pdfplumber found",
                    exc.__class__.__name__)
        return plain

    try:
        from pathlib import Path
        ocr = OCR()
        # cleanup=False: the cleanup pass sends every chunk to a language model,
        # which on a CPU-only host costs minutes per chunk for a tidier result
        # that retrieval does not need.
        text = ocr.output_document(Path(pdf_path), False)
        if text and text.strip():
            logger.info("OCR produced %d characters for %s",
                        len(text.strip()), getattr(pdf_path, "name", pdf_path))
            return text
        logger.warning("OCR returned nothing; using what pdfplumber found")
        return plain
    except Exception:
        logger.warning("OCR failed, using what pdfplumber found:\n%s",
                       traceback.format_exc())
        return plain


def ingest_document(document_id):
    """Run the full pipeline for one Document, recording progress on the row."""
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("ingest_document: no Document with id %s", document_id)
        return

    try:
        doc.status = Document.PROCESSING
        doc.error = ""
        doc.save(update_fields=["status", "error"])

        full_text = _extract_text(doc.stored_path)
        if not full_text or not full_text.strip():
            raise ValueError("No text could be extracted from this PDF.")

        entries = build_section_based_chunks(full_text, {
            "source_url": doc.original_filename,
            "fund_name": doc.fund.name if doc.fund else "",
            "doc_type": doc.doc_type,
        })
        if not entries:
            raise ValueError("Text was extracted but produced no usable chunks.")

        leaf_texts = [e["leaf_text"] for e in entries]

        embeddings = resources.embedder.encode(
            leaf_texts, batch_size=32, show_progress_bar=False
        ).tolist()

        sparse = resources.bm25.encode_documents(leaf_texts)
        if isinstance(sparse, dict):
            sparse = [sparse]

        vectors = []
        for entry, dense, sp in zip(entries, embeddings, sparse):
            vec_id = hashlib.md5(
                f"{doc.pk}::{entry['leaf_text'][:120]}".encode("utf-8")
            ).hexdigest()
            vectors.append({
                "id": vec_id,
                "values": dense,
                "sparse_values": sp,
                "metadata": {
                    "text": trim_to_sentence_boundary(entry["parent_text"], PARENT_METADATA_CHARS),
                    "child_match_text": trim_to_sentence_boundary(entry["leaf_text"], LEAF_METADATA_CHARS),
                    "source_url": entry["source_url"],
                    "fund_name": entry["fund_name"],
                    "doc_type": entry["doc_type"],
                    # Set on uploads only; documents from the bulk script have
                    # no owner, which is what makes them shared.
                    "owner": doc.owner.name,
                },
            })

        for start in range(0, len(vectors), UPSERT_BATCH_SIZE):
            resources.index.upsert(vectors=vectors[start:start + UPSERT_BATCH_SIZE])

        doc.vector_ids = [v["id"] for v in vectors]
        doc.chunk_count = len(vectors)
        doc.status = Document.READY
        doc.save(update_fields=["vector_ids", "chunk_count", "status"])
        logger.info("Ingested %s: %d chunks", doc.original_filename, len(vectors))

    except Exception as exc:
        logger.error("Ingestion failed for document %s:\n%s", document_id, traceback.format_exc())
        doc.status = Document.FAILED
        doc.error = f"{exc.__class__.__name__}: {exc}"
        doc.save(update_fields=["status", "error"])
    finally:
        # This runs in a worker thread, which Django will not clean up for us.
        connection.close()


def start_ingestion(document):
    """Kick off ingestion in the background so the upload request can return."""
    thread = threading.Thread(
        target=ingest_document,
        args=(document.pk,),
        name=f"ingest-doc-{document.pk}",
        daemon=True,
    )
    thread.start()
    return thread


def delete_document_vectors(document):
    """Remove a document's vectors from Pinecone. Safe to call repeatedly."""
    if not document.vector_ids:
        return 0
    for start in range(0, len(document.vector_ids), UPSERT_BATCH_SIZE):
        resources.index.delete(ids=document.vector_ids[start:start + UPSERT_BATCH_SIZE])
    return len(document.vector_ids)
