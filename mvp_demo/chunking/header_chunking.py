import re
from llama_index.core.node_parser import SentenceSplitter
from mvp_demo.chunking.toc_filter import looks_like_toc_line, remove_toc_regions, section_toc
# Heading patterns and fallback settings stay with the text chunker.
_HEADING_STATUTE_RE = re.compile(r"^\s*(\d{1,4}[A-Z]{0,3})\s+([A-Z][A-Za-z0-9,'\-\u2013\u2014\s]{2,90})$")
_HEADING_CLAUSE_RE = re.compile(r"^\s*\d{1,3}\.\s+[A-Z][A-Za-z0-9,'\-\u2013\u2014\s]{2,90}:\s*$")
_MARKDOWN_HEADING_RE = re.compile(r"^\s*#{1,6}\s+\S.*$")
_MIN_HEADINGS_FOR_STRUCTURE = 3
_MIN_PARAGRAPHS_FOR_FALLBACK = 3

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
    if _MARKDOWN_HEADING_RE.match(line):
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
def build_section_based_chunks(full_text, base_metadata, rejected_chunks=None):
    chunking_text = remove_toc_regions(
        full_text,
        rejected_chunks=rejected_chunks,
        source_url=base_metadata.get("source_url", ""),
    )
    sections = split_into_sections(chunking_text)
    entries = []

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if section_toc(section):
            if rejected_chunks is not None:
                rejected_chunks.append({
                    "stage": "section",
                    "reason": "clear_toc_block",
                    "text": section,
                    "source_url": base_metadata.get("source_url", ""),
                })
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
                if rejected_chunks is not None:
                    rejected_chunks.append({
                        "stage": "parent",
                        "reason": "clear_toc_block",
                        "text": parent_text,
                        "source_url": base_metadata.get("source_url", ""),
                    })
                continue

            leaves = _leaf_splitter.split_text(parent_text)
            if not leaves:
                leaves = [parent_text]

            for leaf_text in leaves:
                leaf_text = leaf_text.strip()
                if not leaf_text:
                    continue
                if section_toc(leaf_text):
                    if rejected_chunks is not None:
                        rejected_chunks.append({
                            "stage": "child",
                            "reason": "clear_toc_block",
                            "text": leaf_text,
                            "source_url": base_metadata.get("source_url", ""),
                        })
                    continue
                entries.append({
                    "leaf_text": leaf_text,
                    "parent_text": parent_text,
                    **base_metadata,
                })

    return entries

def build_header_based_chunks(full_text, base_metadata, rejected_chunks=None):
    """Descriptive name; the original API remains for existing metrics."""
    return build_section_based_chunks(full_text, base_metadata, rejected_chunks)
