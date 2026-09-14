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

def looks_cut(text, strict=False):
    """
    Heuristic for detecting possible mid-sentence / mid-clause cuts.

    This is only an evaluation heuristic. It does NOT change
    the actual chunking behaviour in ingest.py.

    Checks whether the chunk starts with lowercase or ends without any punctuations
    """

    if not text:
        return False

    t = text.strip()

    if not t:
        return False

    starts_lower = (
        t[0].islower()
        if t[0].isalpha()
        else False
    )

    if strict:
        ends_no_punct = t[-1] not in '.!?":)'
        return starts_lower or ends_no_punct

    ends_no_punct = t[-1] not in '.!?":);'

    # Legal list markers such as:
    # (a), (b), i., ii., iii)
    if starts_lower and _LIST_MARKER_START_RE.match(t):
        starts_lower = False

    # Short heading-like chunks legitimately do not end
    # with sentence punctuation.
    last_line = t.split("\n")[-1].strip()

    if (
        ends_no_punct
        and len(t) < 60
        and _LOOKS_LIKE_HEADING_RE.match(last_line)
    ):
        ends_no_punct = False

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

    cut_leaves = sum(
        1
        for entry in entries
        if looks_cut(entry["leaf_text"])
    )

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

        if not looks_cut(leaf):
            continue

        cut_count += 1

        next_leaf = ""
        if i + 1 < len(entries):
            next_leaf = entries[i + 1]["leaf_text"]

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
    if len(sys.argv) < 2:
        print(
            "Usage: python3 chunking_metrics.py "
            "<pdf1> <pdf2> ..."
        )

        sys.exit(1)

    all_metrics = []

    for pdf_path in sys.argv[1:]:

        metrics = report_for_document(
            pdf_path
        )

        all_metrics.append(
            (pdf_path, metrics)
        )

    print("\n" + "=" * 90)
    print("CORPUS SUMMARY")
    print("=" * 90)

    total_chunks = sum(
        metrics["total_chunks"]
        for _, metrics in all_metrics
    )

    print(
        f"{'Document':<50} "
        f"{'Chunks':>8} "
        f"{'Cut%':>8} "
        f"{'TOC%':>8} "
        f"{'Contain%':>10}"
    )

    for path, metrics in all_metrics:

        name = path.split("/")[-1]

        if metrics["total_chunks"] == 0:
            print(
                f"{name:<50} "
                f"{'0':>8}"
            )
            continue

        print(
            f"{name:<50} "
            f"{metrics['total_chunks']:>8} "
            f"{metrics['cut_leaf_rate'] * 100:>7.1f}% "
            f"{metrics['toc_leaf_rate'] * 100:>7.1f}% "
            f"{metrics['containment_rate'] * 100:>9.1f}%"
        )

    print(
        f"\nTotal chunks across corpus: "
        f"{total_chunks}"
    )


if __name__ == "__main__":
    main()