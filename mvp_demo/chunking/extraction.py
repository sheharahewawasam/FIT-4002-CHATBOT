"""
PDF text extraction, shared by the two ingestion entry points.

ingest.py (the bulk command-line run) and rag_api/ingestion.py (a single
uploaded document) both need this, and neither can import the other: ingest.py
builds a Pinecone client at import time, and rag_api needs Django configured.
So it lives here, alongside the chunking rules it feeds.
"""
import re

import pdfplumber


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
