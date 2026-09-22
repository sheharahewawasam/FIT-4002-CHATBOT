"""Shared original TOC rules, used by text ingestion and offline layout tests."""
import re

_TOC_ENTRY_RE = re.compile(
    r"^\s*(?P<label>.*?[A-Za-z].*?)\s*\.{3,}\s*(?:[0-9]{1,4}|[ivxlcdm]{1,8})\s*$",
    re.IGNORECASE,
)


_TOC_DOTTED_LINE_RE = re.compile(
    r"^\s*(?P<label>.*?[A-Za-z].*?)\s*\.{3,}\s*(?:[0-9]{1,4}|[ivxlcdm]{1,8})?\s*$",
    re.IGNORECASE,
)


_TOC_TRAILING_PAGE_RE = re.compile(
    r"^\s*(?P<label>.*[A-Za-z].*?)\s+(?:[0-9]{1,4}|[ivxlcdm]{1,8})\s*$",
    re.IGNORECASE,
)


_TOC_TITLE_RE = re.compile(r"^(?:table\s+of\s+contents|contents)\s*:?$", re.IGNORECASE)


_TOC_PAGE_RE = re.compile(r"^(?:page\s+)?(?:[0-9]{1,4}|[ivxlcdm]{1,8})$", re.IGNORECASE)


def looks_like_toc_line(line):
    return bool(_TOC_ENTRY_RE.fullmatch(line.strip()))


def _normalise_toc_label(text):
    # Standardises words so small formattign differences do not prevnet a match
    text = re.sub(r"^#{1,6}\s+", "", text.strip())
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.rstrip(" .:").casefold()


def _toc_entry_label(line):
    """
    Return the label portion of a strong TOC entry, if present.
    E.g. For line: blablabla .......................... 2 
    would just return blablabla. Page number and dot leaders are excluded.
    """
    stripped = line.strip()
    dotted = _TOC_DOTTED_LINE_RE.fullmatch(stripped)
    if dotted:
        return dotted.group("label").strip()

    trailing_page = _TOC_TRAILING_PAGE_RE.fullmatch(stripped)
    if trailing_page:
        return trailing_page.group("label").strip()

    return None


def _has_body_text_after(lines, heading_index, max_nonempty_lines=8):
    """Check that a repeated heading is followed by ordinary body content."""
    checked = 0
    for line in lines[heading_index + 1:]:
        stripped = line.strip()
        if not stripped:
            continue

        checked += 1
        if _TOC_DOTTED_LINE_RE.fullmatch(stripped):
            return False

        if len(re.findall(r"\b\w+\b", stripped)) >= 7:
            return True

        if checked >= max_nonempty_lines:
            break

    return False


def _body_block_start(lines, toc_start, repeated_heading_index, max_backtrack=20):
    """Retain introductory body lines immediately before the repeated heading."""
    lower_bound = max(toc_start + 1, repeated_heading_index - max_backtrack)
    for index in range(repeated_heading_index - 1, lower_bound - 1, -1):
        if not lines[index].strip():
            return index + 1
    return repeated_heading_index


def _find_toc_region_end(lines, start, max_scan_lines=5000):
    """Locate the first real body heading following a standalone TOC title.

    A body boundary is accepted only after at least three strong TOC entries.
    It must repeat a label previously observed in a dotted or page-numbered
    TOC row and be followed by ordinary body text.
    """
    observed_labels = set()
    evidence_count = 0
    stop = min(len(lines), start + max_scan_lines)

    for index in range(start + 1, stop):
        line = lines[index].strip()
        if not line:
            continue

        if _TOC_TITLE_RE.fullmatch(line):
            continue

        label = _toc_entry_label(line)
        if label:
            normalised = _normalise_toc_label(label)
            if normalised:
                observed_labels.add(normalised)
                evidence_count += 1
            continue

        if evidence_count < 3:
            continue

        if (
            _normalise_toc_label(line) in observed_labels
            and _has_body_text_after(lines, index)
        ):
            return _body_block_start(lines, start, index)

    return None


def remove_toc_regions(text, rejected_chunks=None, source_url=""):
    """Remove complete, confidently detected TOC regions before chunking."""
    lines = text.splitlines()
    retained_lines = []
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if not _TOC_TITLE_RE.fullmatch(line):
            retained_lines.append(lines[index])
            index += 1
            continue

        end = _find_toc_region_end(lines, index)
        if end is None:
            # An isolated word "Contents" is not enough evidence for deletion.
            retained_lines.append(lines[index])
            index += 1
            continue

        removed_text = "\n".join(lines[index:end]).strip()
        if rejected_chunks is not None:
            rejected_chunks.append({
                "stage": "pre_chunk",
                "reason": "toc_region",
                "text": removed_text,
                "source_url": source_url,
                "line_start": index + 1,
                "line_end": end,
            })
        index = end

    return "\n".join(retained_lines).strip()


def section_toc(section_text, threshold=0.6, short_section_len=400):
    """Conservatively identify clear TOC-only blocks.

    Require two strong entries. Every other nonblank line must be a contents
    title or standalone page label. Mixed prose/TOC blocks are retained.
    short_section_len is accepted for compatibility; it no longer deletes text.
    This intentionally misses ambiguous, wrapped or undotted TOCs.
    """
    lines = [line.strip() for line in section_text.splitlines() if line.strip()]
    if not lines:
        return False
    entries = sum(looks_like_toc_line(line) for line in lines)
    if entries < 2 or entries / len(lines) < threshold:
        return False
    return all(
        looks_like_toc_line(line)
        or _TOC_TITLE_RE.fullmatch(line)
        or _TOC_PAGE_RE.fullmatch(line)
        for line in lines
    )
