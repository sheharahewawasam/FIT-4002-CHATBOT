"""
chunk_structure_metrics.py

Evaluates chunk construction and structural quality

It evaluates:
- chunk lengths
- parent-child containment
- parent-equals-child rate
- possible sentence cuts
- TOC leakage
- section-detection method
"""

import sys
import re

from pathlib import Path
from contextlib import redirect_stdout
from ingest import (
    extract_text_with_tables,
    build_section_based_chunks,
    section_toc,
    is_heading_line,
    _MIN_HEADINGS_FOR_STRUCTURE,
    _MIN_PARAGRAPHS_FOR_FALLBACK,
)

# Used to find:
# (a)
# (b)
# (i)
# (ii)
# (iv)

# a.
# b.
# i.
# ii.

# a)
# b)
# i)
# ii)
_LIST_MARKER_START_RE = re.compile(
    r"^\s*(\(([a-z]|[ivxlcdm]{1,5})\)|([a-z]|[ivxlcdm]{1,5})[.)])\s*"
)

# Used to find 
# Membership
# Trustee Powers
# Death Benefits
# Part 2 Administration
_LOOKS_LIKE_HEADING_RE = re.compile(
    r"^[A-Z][A-Za-z0-9\s\-/,]{0,60}$"
)

def looks_cut(text, next_text="", strict=False):
    """
    Heuristic for detecting likely mid-sentence / mid-clause cuts.

    This is only an evaluation metric.
    It does NOT change chunking behaviour.
    """

    if not text:
        return False

    t = text.strip()

    if not t:
        return False

    lines = [line.strip() for line in t.split("\n") if line.strip()]

    if not lines:
        return False

    last_line = lines[-1]
    first_line = lines[0]

    # -------------------------------------------------
    # 1. Ignore obvious headings
    # -------------------------------------------------

    if (
        len(lines) <= 2
        and len(t) < 120
        and (
            _LOOKS_LIKE_HEADING_RE.match(last_line)
            or last_line.isupper()
        )
    ):
        return False

    # -------------------------------------------------
    # 2. Ignore standalone page numbers
    # -------------------------------------------------

    if last_line.isdigit():
        return False

    # -------------------------------------------------
    # 3. Ignore signatures / document-ending labels
    # -------------------------------------------------

    signature_terms = {
        "yours faithfully",
        "yours sincerely",
        "signed",
        "signature",
        "name of witness",
    }

    if last_line.lower() in signature_terms:
        return False

    # -------------------------------------------------
    # 4. Ignore obvious table / financial rows
    # -------------------------------------------------

    # If the last line contains multiple numbers,
    # it is probably a table/financial row rather than prose.
    number_count = len(re.findall(r"\b[\d,.$%()-]+\b", last_line))

    if number_count >= 3:
        return False

    # -------------------------------------------------
    # 5. Ignore legal/list markers
    # -------------------------------------------------

    if _LIST_MARKER_START_RE.match(first_line):
        starts_lower = False
    else:
        starts_lower = (
            first_line[0].islower()
            if first_line and first_line[0].isalpha()
            else False
        )

    # -------------------------------------------------
    # 6. Check end punctuation
    # -------------------------------------------------

    ends_no_punct = t[-1] not in '.!?":);'

    # -------------------------------------------------
    # 7. Use next chunk to strengthen the decision
    # -------------------------------------------------

    if next_text:
        next_t = next_text.strip()

        if next_t:
            next_lines = [
                line.strip()
                for line in next_t.split("\n")
                if line.strip()
            ]

            if next_lines:
                next_first = next_lines[0]

                # If next chunk starts with a heading,
                # current chunk probably ended at a valid boundary.
                if (
                    len(next_first) < 100
                    and (
                        _LOOKS_LIKE_HEADING_RE.match(next_first)
                        or next_first.isupper()
                    )
                ):
                    return False

                # Strong evidence of a real continuation:
                # current chunk has no punctuation and next starts lowercase
                next_starts_lower = (
                    next_first[0].islower()
                    if next_first and next_first[0].isalpha()
                    else False
                )

                if ends_no_punct and next_starts_lower:
                    return True

    if strict:
        return starts_lower or ends_no_punct

    return starts_lower or ends_no_punct


def compute_metrics(entries):
    n = len(entries)

    if n == 0:
        return {
            "total_chunks": 0
        }

    leaf_lengths = [
        len(entry["leaf_text"])
        for entry in entries
    ]

    parent_lengths = [
        len(entry["parent_text"])
        for entry in entries
    ]

    # Remove whitespace and get 80 characters from the leaf and check whether they exist in parent 
    contained = sum(
        1
        for entry in entries
        if entry["leaf_text"].strip()[:80]
        in entry["parent_text"]
    )

    # Check whether the parent and child have the exact same text
    parent_equals_child = sum(
        1
        for entry in entries
        if entry["parent_text"].strip()
        == entry["leaf_text"].strip()
    )

    cut_leaves = 0

    for i, entry in enumerate(entries):
        next_text = ""

        if i + 1 < len(entries):
            next_text = entries[i + 1]["leaf_text"]

        if looks_cut(entry["leaf_text"], next_text):
            cut_leaves += 1

    # Compare the leaf to check whether there are any that looks like a TOC
    toc_leaves = sum(
        1
        for entry in entries
        if section_toc(entry["leaf_text"])
    )

    return {
        "total_chunks": n,

        "leaf_len_avg":
            sum(leaf_lengths) / n,

        "leaf_len_min":
            min(leaf_lengths),

        "leaf_len_max":
            max(leaf_lengths),

        "parent_len_avg":
            sum(parent_lengths) / n,

        "containment_rate":
            contained / n,

        "parent_equals_child_rate":
            parent_equals_child / n,

        "cut_leaf_rate":
            cut_leaves / n,

        "toc_leaf_rate":
            toc_leaves / n,
    }

def print_cut_points(entries):
    cut_count = 0

    print("\n" + "-" * 90)
    print("POSSIBLE CUT POINTS")
    print("-" * 90)

    for i, entry in enumerate(entries):
        leaf = entry["leaf_text"]

        next_leaf = ""

        if i + 1 < len(entries):
            next_leaf = entries[i + 1]["leaf_text"]

        if not looks_cut(leaf, next_leaf):
            continue

        cut_count += 1

        print(f"\nCut #{cut_count} — Chunk {i + 1}")

        print("\nCurrent chunk ending:")
        print(leaf[-250:])

        if next_leaf:
            print("\nNext chunk beginning:")
            print(next_leaf[:250])

        print("\n" + "." * 60)

    if cut_count == 0:
        print("\nNo possible cut points detected.")

def compute_section_detection_stats(full_text):
    lines = full_text.split("\n")

    boundaries = [
        i
        for i, _ in enumerate(lines)
        if is_heading_line(lines, i)
    ]

    if len(boundaries) >= _MIN_HEADINGS_FOR_STRUCTURE:
        method = "heading-based"

    else:
        paragraphs = [
            p.strip()
            for p in full_text.split("\n\n")
            if p.strip()
        ]

        if len(paragraphs) >= _MIN_PARAGRAPHS_FOR_FALLBACK:
            method = "paragraph-fallback"
        else:
            method = "whole-document-fallback"

    return method, len(boundaries)


def report_for_document(
    pdf_path,
    fund_name="Test",
    doc_type="Unknown"
):
    print("\n" + "=" * 90)
    print(pdf_path)
    print("=" * 90)

    full_text = extract_text_with_tables(pdf_path)

    method, heading_count = (
        compute_section_detection_stats(full_text)
    )

    entries = build_section_based_chunks(
        full_text,
        {
            "source_url": pdf_path.split("/")[-1],
            "fund_name": fund_name,
            "doc_type": doc_type,
        }
    )

    metrics = compute_metrics(entries)

    print(
        f"Extracted text: "
        f"{len(full_text):,} chars"
    )

    print(
        f"Detection method: "
        f"{method} "
        f"(headings found: {heading_count})"
    )

    print()

    print(
        f"Total chunks:            "
        f"{metrics['total_chunks']}"
    )

    if metrics["total_chunks"] > 0:

        print(
            "Leaf length avg/min/max: "
            f"{metrics['leaf_len_avg']:.0f} / "
            f"{metrics['leaf_len_min']} / "
            f"{metrics['leaf_len_max']} chars"
        )

        print(
            "Parent length avg:       "
            f"{metrics['parent_len_avg']:.0f} chars"
        )

        print()

        print(
            "Parent-contains-child rate:  "
            f"{metrics['containment_rate'] * 100:.1f}%"
        )

        print(
            "Parent == child rate:        "
            f"{metrics['parent_equals_child_rate'] * 100:.1f}%"
        )

        print(
            "Possible mid-sentence cuts:  "
            f"{metrics['cut_leaf_rate'] * 100:.1f}%"
        )

        print(
            "TOC-noise-leaked rate:       "
            f"{metrics['toc_leaf_rate'] * 100:.1f}%"
        )

        print_cut_points(entries)

    return metrics

def main():
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  python3 chunk_structure_metrics.py <pdf1> <pdf2> ...")
        print("  python3 chunk_structure_metrics.py --all")
        return

    if "--all" in args:
        pdf_paths = sorted(Path("../pdfs").glob("*.pdf"))
    else:
        pdf_paths = [Path(arg) for arg in args]

    for pdf_path in pdf_paths:
        output_dir = Path("test_chunking_output")
        output_dir.mkdir(exist_ok=True)

        output_name = output_dir / f"test_{pdf_path.stem}_output.txt"

        print(f"Processing: {pdf_path.name}")

        try:
            with open(output_name, "w", encoding="utf-8") as f:
                with redirect_stdout(f):
                    report_for_document(str(pdf_path))

            print(f"Saved: {output_name}")

        except Exception as e:
            print(f"ERROR processing {pdf_path.name}: {e}")

if __name__ == "__main__":
    main()