"""
chunk_structure_metrics.py

Check whether chunks are structurally constructed correctly

It evaluates:
- chunk lengths
- parent-child containment
- parent-equals-child rate
- possible sentence cuts
- TOC leakage
- section-detection method
"""

import sys
import json
import re

from pathlib import Path
from contextlib import redirect_stdout
from ingest import (
    extract_document_text,
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

_MARKDOWN_HEADING_START_RE = re.compile(r"^\s*#{1,6}\s+\S")
_NUMBERED_ITEM_START_RE = re.compile(
    r"^\s*(?:\d+[A-Za-z]?(?:\.\d+)*[.)]?|\([A-Za-z0-9ivxlcdm]+\))\s+",
    re.IGNORECASE,
)
_BULLET_START_RE = re.compile(r"^\s*(?:[-*•▪◦]|\u2022)\s+")
_SAFE_END_CHARS = '.!?":;)]}'


def _looks_like_structural_start(text):
    """Recognise boundaries that may validly begin without sentence prose."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    first = lines[0]
    if _MARKDOWN_HEADING_START_RE.match(first):
        return True
    if _NUMBERED_ITEM_START_RE.match(first) or _LIST_MARKER_START_RE.match(first):
        return True
    if _BULLET_START_RE.match(first):
        return True
    if "|" in first or "<tr" in first.lower() or "<td" in first.lower():
        return True
    if first.isupper():
        return True

    words = first.split()
    return len(words) <= 8 and first.istitle()


def _boundary_is_safe(parent, position, boundary):
    """Judge a child's start or end using its exact position in its parent."""
    if position <= 0 or position >= len(parent):
        return True

    before = parent[:position]
    after = parent[position:]
    before_trimmed = before.rstrip()
    if boundary == "start":
        boundary_space = before[len(before_trimmed):]
    else:
        boundary_space = after[: len(after) - len(after.lstrip())]

    if not before_trimmed or not after.strip():
        return True
    if "\n\n" in boundary_space:
        return True
    if before_trimmed[-1] in _SAFE_END_CHARS:
        return True
    if _looks_like_structural_start(after.lstrip()):
        return True

    return False


def find_boundary_issues(entries):
    """Find likely cuts using local parent offsets, including overlapping leaves."""
    issues = []
    previous_parent_key = None
    search_from = 0

    for chunk_index, entry in enumerate(entries):
        child = entry["leaf_text"].strip()
        parent = entry["parent_text"].strip()
        parent_key = (entry.get("source_url", ""), parent)

        if parent_key != previous_parent_key:
            search_from = 0

        start = parent.find(child, search_from)
        if start < 0:
            start = parent.find(child)
        if start < 0:
            previous_parent_key = parent_key
            continue

        end = start + len(child)
        search_from = start + 1
        previous_parent_key = parent_key

        if not _boundary_is_safe(parent, start, "start"):
            issues.append({
                "chunk_index": chunk_index,
                "boundary": "start",
                "before": parent[max(0, start - 250):start],
                "after": parent[start:min(len(parent), start + 250)],
            })

        if not _boundary_is_safe(parent, end, "end"):
            issues.append({
                "chunk_index": chunk_index,
                "boundary": "end",
                "before": parent[max(0, end - 250):end],
                "after": parent[end:min(len(parent), end + 250)],
            })

    return issues


def print_storage_containment_failures(entries):
    failure_count = 0

    for i, entry in enumerate(entries):
        child = entry["leaf_text"].strip()
        stored_parent = entry["parent_text"].strip()

        if child in stored_parent:
            continue

        failure_count += 1

        print(f"\nStorage containment failure #{failure_count}")
        print(f"Chunk: {i + 1}")

        print("\nRetrieved child:")
        print(child[:500])

        print("\nStored parent ending:")
        print(stored_parent[-500:])

    if failure_count == 0:
        print("\nNo storage containment failures detected.")


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

    # Check the full, nonempty child against its local parent. 
    contained = sum(
        1
        for entry in entries
        if entry["leaf_text"].strip() and entry["leaf_text"].strip()
        in entry["parent_text"]
    )

    # Check whether the parent and child have the exact same text
    parent_equals_child = sum(
        1
        for entry in entries
        if entry["parent_text"].strip()
        == entry["leaf_text"].strip()
    )

    boundary_issues = find_boundary_issues(entries)
    cut_leaf_indices = {
        issue["chunk_index"]
        for issue in boundary_issues
    }
    cut_leaves = len(cut_leaf_indices)

    # Compare the leaf to check whether there are any that looks like a TOC
    toc_leaves = sum(
        1
        for entry in entries
        if section_toc(entry["leaf_text"])
    )

    stored_parent_contains_child = sum(
        1
        for entry in entries
        if entry["leaf_text"].strip() and entry["leaf_text"].strip()
        in entry["parent_text"].strip()
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

        "cut_leaf_count":
            cut_leaves,

        "cut_boundary_count":
            len(boundary_issues),

        "toc_leaf_rate":
            toc_leaves / n,

        "stored_parent_contains_child_rate":
        stored_parent_contains_child / n,
    }

def print_cut_points(entries):
    issues = find_boundary_issues(entries)

    print("\n" + "-" * 90)
    print("POSSIBLE CUT POINTS")
    print("-" * 90)

    for issue_number, issue in enumerate(issues, start=1):
        print(
            f"\nCut #{issue_number} — Chunk {issue['chunk_index'] + 1} "
            f"({issue['boundary']} boundary within its parent)"
        )

        print("\nText before boundary:")
        print(issue["before"])

        print("\nText after boundary:")
        print(issue["after"])

        print("\n" + "." * 60)

    if not issues:
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
    doc_type="Unknown",
    *, full_text=None, entries=None, rejected_chunks=None
):
    print("\n" + "=" * 90)
    print(pdf_path)
    print("=" * 90)

    if full_text is None:
        full_text = extract_document_text(pdf_path)

    method, heading_count = compute_section_detection_stats(full_text)
    if rejected_chunks is None:
        rejected_chunks = []
    if entries is None:
        entries = build_section_based_chunks(
            full_text,
            {"source_url": Path(pdf_path).name, "fund_name": fund_name, "doc_type": doc_type},
            rejected_chunks,
        )

    print(f"Removed TOC blocks: {len(rejected_chunks)}")
    for rejected in rejected_chunks:
        removed_text = rejected["text"]
        line_range = ""
        if rejected.get("line_start") is not None:
            line_range = (
                f", source lines {rejected['line_start']}"
                f"-{rejected.get('line_end', rejected['line_start'])}"
            )
        print(
            f"\nREMOVED [{rejected['stage']}] {rejected['reason']}"
            f" ({len(removed_text):,} chars{line_range})"
        )
        print("Beginning:")
        print(removed_text[:500])
        if len(removed_text) > 1000:
            print("\nEnding:")
            print(removed_text[-500:])
    print("\nTOC rule matches are a filter consistency check, not independently measured leakage.")
    print("Containment checks local entries, not fetched Pinecone records.")

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
            f"{metrics['cut_leaf_rate'] * 100:.1f}% "
            f"({metrics['cut_leaf_count']} chunks, "
            f"{metrics['cut_boundary_count']} boundaries)"
        )

        print(
            "Retained TOC-rule match rate:       "
            f"{metrics['toc_leaf_rate'] * 100:.1f}%"
        )

        print(
            "Local parent contains full child: "
            f"{metrics['stored_parent_contains_child_rate'] * 100:.1f}%"
        )

        print_storage_containment_failures(entries)

        print_cut_points(entries)

    return metrics

def main():
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  python3 chunk_structure_metrics.py <pdf1> <pdf2> ...")
        print("  python3 chunk_structure_metrics.py --all")
        print("  python3 chunk_structure_metrics.py --all-pdfs")
        print("  python3 chunk_structure_metrics.py --snapshot path/to/document_chunks.json")
        return

    snapshot_mode = args[0] in {"--snapshot", "--all"}
    if args[0] == "--snapshot":
        if len(args) < 2:
            raise SystemExit("Provide one or more snapshot JSON paths after --snapshot.")
        pdf_paths = [Path(arg) for arg in args[1:]]
    elif args[0] == "--all":
        snapshot_dir = Path("test_chunking_output") / "snapshots"
        pdf_paths = sorted(snapshot_dir.glob("*_chunks.json"))
        if not pdf_paths:
            raise SystemExit(f"No snapshot files found in {snapshot_dir}.")
    elif args[0] == "--all-pdfs":
        pdf_paths = sorted(Path("../pdfs").glob("*.pdf"))
        if not pdf_paths:
            raise SystemExit("No PDF files found in ../pdfs.")
    else:
        pdf_paths = [Path(arg) for arg in args]

    for pdf_path in pdf_paths:
        output_dir = Path("test_chunking_output") / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_name = output_dir / f"test_{pdf_path.stem}_output.txt"

        print(f"Processing: {pdf_path.name}")

        try:
            with open(output_name, "w", encoding="utf-8") as f:
                with redirect_stdout(f):
                    if snapshot_mode:
                        data = json.loads(pdf_path.read_text(encoding="utf-8"))
                        report_for_document(
                            data["source_path"], full_text=data["full_text"],
                            entries=data["entries"], rejected_chunks=data["rejected_chunks"],
                        )
                    else:
                        report_for_document(str(pdf_path))

            print(f"Saved: {output_name}")

        except Exception as e:
            print(f"ERROR processing {pdf_path.name}: {e}")

if __name__ == "__main__":
    main()
