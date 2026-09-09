"""
Shared PDF text extraction and section-aware chunking.

Extracted from ingest.py so the same logic backs both the bulk CLI ingest
and per-user uploads through the API. Pure text in, chunks out - no Pinecone,
no Django, no side effects on import.
"""
import re

import pdfplumber
from llama_index.core.node_parser import SentenceSplitter


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

# Detects statute-style numbered headings, for example:
# "1 Short title"
# "17A Definition of self managed superannuation fund"
_HEADING_STATUTE_RE = re.compile(r"^\s*(\d{1,4}[A-Z]{0,3})\s+([A-Z][A-Za-z0-9,'\-\u2013\u2014\s]{2,90})$")

# Detects numbered clause-style headings that end with a colon, for example:
# "1. Membership:"
# "12. Trustee Powers:"
_HEADING_CLAUSE_RE = re.compile(r"^\s*\d{1,3}\.\s+[A-Z][A-Za-z0-9,'\-\u2013\u2014\s]{2,90}:\s*$")

# Minimum number of detected headings required before heading-based section splitting is considered reliable.
_MIN_HEADINGS_FOR_STRUCTURE = 3

# Minimum number of paragraphs required before using paragraph-based splitting as the fallback method.
_MIN_PARAGRAPHS_FOR_FALLBACK = 3

# Detects dot leaders commonly used in Table of Contents entries.
_DOT_LEADER_RE = re.compile(r"\.{3,}")

# Detects a possible page number at the end of a line.
_TRAILING_PAGE_NUM_RE = re.compile(r"\b\d{1,4}\s*$")

# Check whether a line appears to be part of a Table of Contents.
# A real TOC entry is a short, title-like line, usually with dot leaders or a
# page number. The naive version of this test breaks on legal text: clause
# numbers, ACNs, dates and dollar amounts all leave a line ending in digits, so
# "ends in a number" describes most lines in a trust deed rather than a table of
# contents. Requiring the line to be short as well restores the distinction.
_TOC_LINE_MAX_CHARS = 80


def looks_like_toc_line(line):
    line = line.strip()
    if not line:
        return False
    if _DOT_LEADER_RE.search(line):
        return True
    if (len(line) <= _TOC_LINE_MAX_CHARS
            and _TRAILING_PAGE_NUM_RE.search(line)
            and not line.endswith((".", "!", "?"))):
        return True
    return False
# Detect short headings written entirely in uppercase.
def _is_all_caps_heading(line):
    words = line.strip().split()
    if not (1 <= len(words) <= 6):
        return False
    letters = [w for w in words if any(c.isalpha() for c in w)]
    if not letters:
        return False
    return all(w.isupper() for w in letters) and len(line.strip()) < 60

# Check whether the next physical line continues a Table of Contents entry.
# Some PDF TOC entries wrap onto two lines. The first line may look like a real heading, 
# while the next line contains dot leaders or a page number.
def _next_line_is_toc_continuation(lines, index):
    for j in range(index + 1, min(index + 2, len(lines))):
        nxt = lines[j].strip()
        if not nxt:
            continue
        return looks_like_toc_line(nxt)
    return False

# Decide whether a particular line should be treated as a section heading.
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

# Check whether an entire detected section is mostly Table of Contents text.
# Individual TOC entries may still be grouped into a section even after
# heading detection. This provides a second filtering stage.
# Content a table of contents never carries. A chunk holding any of these is
# real content whatever its line endings look like. This is what keeps deed
# schedules - deed date, trustee ACN, member names - in the index.
_SUBSTANTIVE_RE = re.compile(
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August"
    r"|September|October|November|December)\s+\d{4}\b"   # 21 January 2012
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"                      # 09/10/2020
    r"|\bA[CB]N\b"                                       # ACN / ABN
    r"|\$\s?\d",                                         # $1,000
    re.IGNORECASE,
)


def section_toc(section_text, threshold=0.6):
    """
    True when a chunk is table-of-contents noise and should not be indexed.

    This previously also discarded any chunk under 400 characters that contained
    even one suspect line. That single rule caused 96% of all deletions and cost
    18% of the corpus - 23% of the SIS Act - because it fires on exactly the
    short, dense, number-heavy blocks that deed schedules are made of. A deed
    date, a trustee ACN and a fund name were all being deleted before indexing.
    """
    lines = [l for l in section_text.split("\n") if l.strip()]
    if not lines:
        return True
    if _SUBSTANTIVE_RE.search(section_text):
        return False
    toc_lines = sum(1 for l in lines if looks_like_toc_line(l))
    return (toc_lines / len(lines)) >= threshold
# Split extracted document text into structural sections.
def split_into_sections(text):
    lines = text.split("\n")
    
    # Record the line position of every detected heading.
    boundaries = [i for i, line in enumerate(lines) if is_heading_line(lines, i)]

    # Use heading-based splitting only when enough headings were found to suggest that the
    # document has a reliable structural pattern.
    if len(boundaries) >= _MIN_HEADINGS_FOR_STRUCTURE:
        sections = []

        # Preserve any text appearing before the first detected heading.
        if boundaries[0] > 0:
            preamble = "\n".join(lines[: boundaries[0]]).strip()
            if preamble:
                sections.append(preamble)

        # Each heading starts a section and the next heading ends it.
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

# If a detected section is too large, divide it into smaller parent chunks.
PARENT_SUBSPLIT_TOKENS = 380     
PARENT_SUBSPLIT_OVERLAP = 40

# Smaller leaf chunks are used for dense and BM25 retrieval.
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

# Convert the document into parent/leaf chunk pairs.
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

            leaves = _leaf_splitter.split_text(parent_text) or [parent_text]
            kept = [l.strip() for l in leaves
                    if l.strip() and not section_toc(l.strip())]

            # Only the leaf is embedded, but the parent is what the model reads.
            # Filtering away every leaf therefore left the parent sitting in the
            # index with nothing pointing at it: present, but reachable by no
            # query at all. Index the parent as its own leaf rather than lose it.
            if not kept:
                kept = [parent_text.strip()]

            for leaf_text in kept:
                entries.append({
                    "leaf_text": leaf_text,
                    "parent_text": parent_text,
                    **base_metadata,
                })
    return entries
