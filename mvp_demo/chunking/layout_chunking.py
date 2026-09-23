"""Offline layout chunking for OCR page dictionaries. Python 3.9+, stdlib only.

Input: a page dictionary, a list of pages, or {"pages": [...]}.
Output: parent/leaf entries compatible with the existing structural snapshot format.
Labels/coordinates are predictions, not ground truth. Unknown blocks are retained.
Character budgets are explicit; they are NOT token counts.
"""
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import math
import re
from chunking.toc_filter import remove_toc_regions


@dataclass
class LayoutBlock:
    text: str
    kind: str
    page: int                       # one-based, unlike the OCR's page_index
    block_id: str                   # page-qualified, unique within this document
    bbox: object = None             # normalised [0, 1], or None (never invented zeros)
    order: object = None
    raw: dict = field(default_factory=dict)


HEADINGS = {'doc_title', 'paragraph_title', 'section_title', 'heading', 'title'}
LABELS = {'field_label', 'form_label'}
VALUES = {'field_value', 'form_value', 'checkbox', 'checkbox_value'}


def is_layout_output(value):
    if isinstance(value, dict):
        return 'parsing_res_list' in value or 'pages' in value
    return isinstance(value, list) and bool(value) and all(
        isinstance(p, dict) and 'parsing_res_list' in p for p in value)


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalise_ocr_output(payload, diagnostics=None, allow_partial=False):
    """Validate page inventory and preserve all blocks, including uncertain footers."""
    notes = diagnostics if diagnostics is not None else []
    if not is_layout_output(payload):
        raise ValueError('Expected OCR page JSON with parsing_res_list, a page list, or {pages: [...]}')
    pages = payload.get('pages', [payload]) if isinstance(payload, dict) else payload
    if not isinstance(pages, list) or not pages:
        raise ValueError('OCR pages must be a non-empty list')
    blocks, seen_pages, expected_counts = [], set(), set()
    if isinstance(payload, dict) and payload.get('page_count') is not None:
        expected_counts.add(payload['page_count'])
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError('Each OCR page must be an object')
        index = page.get('page_index')
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ValueError('Every OCR page requires a non-negative integer page_index')
        if index in seen_pages:
            raise ValueError('Duplicate page_index: %s' % index)
        seen_pages.add(index)
        if page.get('page_count') is not None:
            expected_counts.add(page['page_count'])
        width, height = page.get('width'), page.get('height')
        dimensions_ok = _finite(width) and _finite(height) and width > 0 and height > 0
        rows = page.get('parsing_res_list')
        if not isinstance(rows, list):
            raise ValueError('parsing_res_list must be a list')
        for pos, raw in enumerate(rows):
            if not isinstance(raw, dict):
                raise ValueError('Each OCR block must be an object')
            text = raw.get('block_content', '')
            if not isinstance(text, str):
                raise ValueError('block_content must be a string; update the adapter for this schema')
            kind = str(raw.get('block_label', 'text')).lower()
            # Blank explicit values must survive: blank is not zero or unchecked.
            if not text.strip() and kind not in VALUES:
                continue
            box = raw.get('block_bbox')
            bbox = None
            if dimensions_ok and isinstance(box, (list, tuple)) and len(box) == 4 and all(map(_finite, box)):
                x0, y0, x1, y1 = box
                if 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height:
                    bbox = (x0 / width, y0 / height, x1 / width, y1 / height)
            if bbox is None:
                notes.append('Page %s block %s: missing/invalid geometry; retaining text and OCR order' % (index + 1, pos))
            order = raw.get('block_order')
            if not _finite(order):
                order = None
            bid = 'p%s:b%s:%s' % (index + 1, raw.get('block_id', pos), pos)
            blocks.append(LayoutBlock(text.strip(), kind, index + 1, bid, bbox, order, raw))
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 1 for n in expected_counts):
        raise ValueError('Invalid page_count')
    if len(expected_counts) > 1:
        raise ValueError('Inconsistent page_count values')
    expected = next(iter(expected_counts), None)
    missing = sorted(set(range(expected)) - seen_pages) if expected else []
    if expected is not None and any(i >= expected for i in seen_pages):
        raise ValueError('page_index is outside page_count')
    if missing:
        message = 'Incomplete OCR document: missing pages ' + ', '.join(str(i + 1) for i in missing)
        if not allow_partial:
            raise ValueError(message + '; use allow_partial=True only for offline testing')
        notes.append(message)
    if expected is None:
        notes.append('No page_count supplied; page completeness cannot be verified')
    return blocks


def _gap(blocks, axis, minimum):
    intervals = sorted((b.bbox[axis], b.bbox[axis + 2]) for b in blocks)
    end, best = intervals[0][1], None
    for start, stop in intervals[1:]:
        if start - end >= minimum and (best is None or start - end > best[0]):
            best = (start - end, (start + end) / 2)
        end = max(end, stop)
    return best[1] if best else None


def _xy_order(blocks):
    """Recursive whitespace cuts; vertical gutters preserve separate columns."""
    if len(blocks) <= 1:
        return blocks
    # A left-aligned section heading followed by wide body text ends the preceding
    # metadata band. Without this, the right-hand date may follow the heading.
    for heading in sorted((b for b in blocks if b.kind in HEADINGS and b.bbox[0] <= .2), key=lambda b:b.bbox[1]):
        cut = heading.bbox[1]
        above = [b for b in blocks if b.bbox[3] <= cut]
        below = [b for b in blocks if b.bbox[1] >= cut]
        wide_body = any(b.kind == 'text' and b.bbox[1] >= heading.bbox[3]
                        and b.bbox[2] - b.bbox[0] >= .65 for b in below)
        if above and below and len(above) + len(below) == len(blocks) and wide_body:
            return _xy_order(above) + _xy_order(below)
    # Coordinates are page fractions. Thresholds are provisional, configurable in code.
    for axis, minimum in ((0, 0.035), (1, 0.008)):
        cut = _gap(blocks, axis, minimum)
        if cut is not None:
            first = [b for b in blocks if b.bbox[axis + 2] <= cut]
            second = [b for b in blocks if b.bbox[axis] >= cut]
            if first and second and len(first) + len(second) == len(blocks):
                return _xy_order(first) + _xy_order(second)
    return sorted(blocks, key=lambda b: (round(b.bbox[1], 3), b.bbox[0], b.order if b.order is not None else math.inf))


def order_blocks(blocks, diagnostics):
    ordered = []
    for page in sorted({b.page for b in blocks}):
        group = [b for b in blocks if b.page == page]
        if all(b.bbox is not None for b in group):
            ordered.extend(_xy_order(group))
        elif all(b.order is not None for b in group):
            ordered.extend(sorted(group, key=lambda b: b.order))
        else:
            diagnostics.append('Page %s: incomplete geometry/order; preserving supplied block sequence' % page)
            ordered.extend(group)
    return ordered


def _edge(b):
    if b.bbox is None:
        return None
    return 'top' if b.bbox[3] <= .10 else 'bottom' if b.bbox[1] >= .90 else None


def filter_repeated_margins(blocks, rejected, diagnostics):
    """Only repeated, explicitly labelled margin text is removed; uncertainty stays."""
    groups = {}
    for b in blocks:
        if b.kind not in {'header', 'footer', 'page_number', 'number'} or not _edge(b):
            continue
        keytext = ' '.join(b.text.casefold().split())
        if re.fullmatch(r'(?:page\s*)?\d+(?:\s*(?:of|/)\s*\d+)?', keytext):
            keytext = '<page number>'
        key = (_edge(b), keytext)
        groups.setdefault(key, []).append(b)
    removed = set()
    for group in groups.values():
        # Require repeated pages AND similar vertical placement; don't blanket-delete footers.
        if len({b.page for b in group}) >= 2 and max(b.bbox[1] for b in group) - min(b.bbox[1] for b in group) < .025:
            for b in group:
                removed.add(b.block_id)
                rejected.append({'stage': 'layout', 'reason': 'repeated_margin', 'text': b.text, 'page': b.page, 'block_id': b.block_id})
    for b in blocks:
        if b.block_id not in removed and b.kind in {'footer', 'header'}:
            diagnostics.append('Retained uncertain %s on page %s: %s' % (b.kind, b.page, b.text[:90]))
    return [b for b in blocks if b.block_id not in removed]


class _HTMLTable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell = [], None, None
    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in {'td', 'th'}:
            attrs = dict(attrs)
            self.cell = {'text': '', 'header': tag == 'th', 'rowspan': int(attrs.get('rowspan', 1)), 'colspan': int(attrs.get('colspan', 1))}
        elif tag == 'br' and self.cell is not None:
            self.cell['text'] += ' '
    def handle_data(self, data):
        if self.cell is not None:
            self.cell['text'] += data
    def handle_endtag(self, tag):
        if tag in {'td', 'th'} and self.cell is not None:
            if self.row is None:
                self.row = []
            self.row.append(self.cell)
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def table_units(block, diagnostics):
    """Serialize table rows with known headers; never invent column meanings."""
    text = block.text
    if '<table' in text.lower():
        parser = _HTMLTable()
        try:
            parser.feed(text)
            grid, headers, carry = [], [], {}
            for r, row in enumerate(parser.rows):
                cells, col = {}, 0
                for c, (remaining, value) in list(carry.items()):
                    cells[c] = value
                    if remaining <= 1:
                        del carry[c]
                    else:
                        carry[c] = (remaining - 1, value)
                for cell in row:
                    while col in cells:
                        col += 1
                    value = ' '.join(cell['text'].split())
                    if not 1 <= cell['colspan'] <= 100 or not 1 <= cell['rowspan'] <= 100:
                        raise ValueError('Unreasonable table span')
                    for c in range(col, col + cell['colspan']):
                        cells[c] = value
                        if cell['rowspan'] > 1:
                            carry[c] = (cell['rowspan'] - 1, value)
                    col += cell['colspan']
                grid.append([cells.get(c, '') for c in range(max(cells, default=-1) + 1)])
                headers.append(bool(row) and all(cell['header'] for cell in row))
        except (ValueError, TypeError) as exc:
            diagnostics.append('Cannot parse table %s: %s; preserving raw content' % (block.block_id, exc))
            return [text]
        if not grid:
            diagnostics.append('No table rows recognised; preserving raw content')
            return [text]
        header_count = 0
        for flag in headers:
            if not flag:
                break
            header_count += 1
        width = max(map(len, grid))
        labels = []
        for c in range(width):
            parts = [row[c] for row in grid[:header_count] if c < len(row) and row[c]]
            labels.append(' / '.join(dict.fromkeys(parts)) or 'Column %s' % (c + 1))
        rows = grid[header_count:]
        if not rows:
            return [' | '.join(row) for row in grid]
        if not header_count:
            diagnostics.append('Table %s has no explicit th headers; using positional column labels' % block.block_id)
    else:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) < 2 or not all('|' in line for line in lines):
            return [text]
        grid = [[v.strip() for v in line.strip('|').split('|')] for line in lines]
        if len(grid) > 1 and all(re.fullmatch(r':?-{3,}:?', cell) for cell in grid[1]):
            labels, rows = grid[0], grid[2:]
        else:
            labels, rows = ['Column %s' % (i + 1) for i in range(max(map(len, grid)))], grid
            diagnostics.append('Pipe table without explicit header separator; using positional column labels')
    result = []
    for n, row in enumerate(rows, 1):
        count = max(len(labels), len(row))
        values = []
        for c in range(count):
            label = labels[c] if c < len(labels) else 'Column %s' % (c + 1)
            value = row[c] if c < len(row) else ''
            values.append('%s: %s' % (label, value if value else '[blank]'))
        result.append('Table row %s | %s' % (n, ' | '.join(values)))
    return result or [text]


def _pair_fields(blocks, diagnostics):
    """Pair explicit label/value types only, with unique mutual spatial matches."""
    candidates = {}
    for a in blocks:
        if a.kind not in LABELS or a.bbox is None:
            continue
        matches = []
        for b in blocks:
            if b.page != a.page or b.kind not in VALUES or b.bbox is None:
                continue
            overlap = min(a.bbox[3], b.bbox[3]) - max(a.bbox[1], b.bbox[1])
            small_height = min(a.bbox[3]-a.bbox[1], b.bbox[3]-b.bbox[1])
            gap = b.bbox[0] - a.bbox[2]
            if overlap >= .5 * small_height and -.005 <= gap <= .3:
                matches.append(b)
        if len(matches) == 1:
            candidates[a.block_id] = matches[0]
        elif matches:
            diagnostics.append('Ambiguous field association %s; retaining separate blocks' % a.block_id)
    frequency = Counter(b.block_id for b in candidates.values())
    return {a: b for a, b in candidates.items() if frequency[b.block_id] == 1}


def _split_prose(text, limit):
    """Lossless whitespace-trimmed slices. Prefer paragraph/sentence/list boundaries."""
    pieces = []
    remaining = text.strip()
    while len(remaining) > limit:
        window = remaining[:limit + 1]
        boundaries = [m.end() for m in re.finditer(r'\n\s*\n|[.!?][\"\u201d\u2019\)\]]?\s+|\n(?=\s*(?:[-*•]|\d+[.)])\s)', window)]
        cut = next((n for n in reversed(boundaries) if limit // 3 <= n <= limit), None)
        if cut is None:
            cut = window.rfind(' ', 0, limit + 1)
        if cut <= 0:
            cut = limit
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def build_layout_snapshot(payload, base_metadata=None, *, parent_max_chars=1500,
                          child_max_chars=550, allow_partial=False, toc_filter=None):
    """No model/network calls. Atomic rows/fields may exceed child budget (flagged).

    Very large atomic units are kept intact up to 8000 chars, then split with an
    explicit warning; never silently truncate data. Parent size is a soft budget
    for atomic units. A TOC callback may be the existing remove_toc_regions.
    """
    if child_max_chars < 80 or parent_max_chars < child_max_chars + 100:
        raise ValueError('Require child_max_chars >= 80 and parent_max_chars >= child_max_chars + 100')
    if toc_filter is None:
        toc_filter = remove_toc_regions
    meta = dict(base_metadata or {})
    notes, rejected = [], []
    original = normalise_ocr_output(payload, notes, allow_partial)
    full_text = '\n\n'.join(b.text for b in original)
    blocks = filter_repeated_margins(original, rejected, notes)
    blocks = order_blocks(blocks, notes)
    # Apply the existing TOC detector only to complete block ranges; preserve partial blocks.
    if toc_filter is not None and blocks:
        text, spans, cursor = '', [], 0
        for b in blocks:
            spans.append((cursor, cursor + len(b.text), b))
            text += b.text + '\n\n'
            cursor = len(text)
        toc_rejected = []
        toc_filter(text.rstrip(), toc_rejected, meta.get('source_url', ''))
        line_offsets, offset = [], 0
        for line in text.splitlines(keepends=True):
            line_offsets.append(offset)
            offset += len(line)
        line_offsets.append(offset)
        drop = set()
        for event in toc_rejected:
            if event.get('reason') != 'toc_region':
                continue
            lo = line_offsets[event['line_start'] - 1]
            hi = line_offsets[event['line_end']]
            for start, end, b in spans:
                if start >= lo and end <= hi:
                    drop.add(b.block_id)
                    rejected.append({'stage':'layout', 'reason':'toc_region', 'text':b.text, 'block_id':b.block_id, 'page':b.page})
                elif start < hi and end > lo:
                    notes.append('TOC boundary crosses %s; retained block for review' % b.block_id)
        blocks = [b for b in blocks if b.block_id not in drop]
    pairs = _pair_fields(blocks, notes)
    paired_values = {b.block_id for b in pairs.values()}
    sections, units, title = [], [], ''
    for i, b in enumerate(blocks):
        if b.block_id in paired_values:
            continue
        heading = b.kind in HEADINGS
        # Recover a short, nonrepeated bottom heading only with a next-page body continuation.
        if b.kind == 'footer' and len(b.text.split()) <= 8 and all(w[:1].isupper() or w.lower() in {'of','the','and','on','for','to','in','a'} for w in b.text.split()) and i+1 < len(blocks):
            following = blocks[i+1]
            if _edge(b) == 'bottom' and following.page == b.page + 1 and following.kind == 'text':
                heading = True
                notes.append('Treated retained margin block %s as a possible cross-page heading' % b.block_id)
        if heading:
            if units:
                sections.append((title, units))
            title = b.text
            units = [(b.text, [b], False)]   # preserve heading text even for heading-only sections
            continue
        sources = [b]
        if b.block_id in pairs:
            value = pairs[b.block_id]
            sources.append(value)
            texts = [b.text + ': ' + (value.text or '[blank]')]
            atomic = True
        elif b.kind in {'table', 'table_body'}:
            texts = table_units(b, notes)
            atomic = True
        else:
            texts = [b.text or '[blank]']
            atomic = b.kind in LABELS | VALUES | {'form_item', 'form_field', 'checkbox'}
        for text in texts:
            if atomic and len(text) <= 8000:
                pieces = [text]
                if len(text) > child_max_chars:
                    notes.append('Atomic unit %s exceeds child character budget; retained intact' % b.block_id)
            else:
                if atomic:
                    notes.append('Atomic unit %s exceeds 8000 chars; split for storage, review required' % b.block_id)
                pieces = _split_prose(text, child_max_chars)
            units.extend((piece, sources, atomic) for piece in pieces)
    if units:
        sections.append((title, units))
    entries = []
    for title, section in sections:
        groups, group, length = [], [], 0
        for unit in section:
            extra = len(unit[0]) + (2 if group else 0)
            if group and length + extra > parent_max_chars:
                groups.append(group)
                group, length = [], 0
            group.append(unit)
            length += len(unit[0]) + (2 if len(group) > 1 else 0)
        if group:
            groups.append(group)
        for parent_units in groups:
            parent = '\n\n'.join(u[0] for u in parent_units)
            sources = {b.block_id:b for u in parent_units for b in u[1]}
            parent_id = hashlib.sha256((meta.get('source_url','') + str(len(entries)) + parent).encode()).hexdigest()[:24]
            # Pack adjacent small units, never split an atomic row just to meet a soft budget.
            leaves, leaf, length = [], [], 0
            for unit in parent_units:
                if leaf and length + 2 + len(unit[0]) > child_max_chars:
                    leaves.append(leaf)
                    leaf, length = [], 0
                leaf.append(unit)
                length += len(unit[0]) + (2 if len(leaf) > 1 else 0)
            if leaf:
                leaves.append(leaf)
            for leaf in leaves:
                leaf_text = '\n\n'.join(u[0] for u in leaf)
                child_sources = {b.block_id:b for u in leaf for b in u[1]}
                entries.append({**meta, 'leaf_text':leaf_text, 'parent_text':parent,
                    'parent_id':parent_id, 'chunk_id':parent_id + ':' + str(len(entries)),
                    'section_title':title, 'chunking_method':'layout_aware',
                    'page_start':min(b.page for b in child_sources.values()),
                    'page_end':max(b.page for b in child_sources.values()),
                    'parent_page_start':min(b.page for b in sources.values()),
                    'parent_page_end':max(b.page for b in sources.values()),
                    'block_ids':list(child_sources),
                    'layout_sources':[{'page':b.page, 'block_id':b.block_id, 'block_type':b.kind, 'bbox':b.bbox} for b in child_sources.values()],
                    'oversized_child':len(leaf_text)>child_max_chars})
    return {'schema_version':2, 'full_text':full_text, 'entries':entries,
            'rejected_chunks':rejected, 'layout_diagnostics':list(dict.fromkeys(notes)),
            'chunking_method':'layout_aware', 'partial_input_allowed':allow_partial,
            'chunking_config':{'parent_max_chars':parent_max_chars, 'child_max_chars':child_max_chars}}


def build_layout_aware_chunks(payload, base_metadata, rejected_chunks=None, **kwargs):
    snapshot = build_layout_snapshot(payload, base_metadata, **kwargs)
    if rejected_chunks is not None:
        rejected_chunks.extend(snapshot['rejected_chunks'])
    return snapshot['entries']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ocr_json', type=Path)
    parser.add_argument('--out-dir', type=Path, default=Path('test_chunking_output/layout_snapshots'))
    parser.add_argument('--allow-partial', action='store_true', help='Permit incomplete page inventory for offline tests only')
    parser.add_argument('--source-name', help='Original PDF filename for snapshot metadata')
    args = parser.parse_args()
    try:
        payload = json.loads(args.ocr_json.read_text(encoding='utf-8-sig'))
        snapshot = build_layout_snapshot(payload, {'source_url':args.source_name or args.ocr_json.stem}, allow_partial=args.allow_partial)
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(2, 'Cannot chunk OCR JSON: %s\n' % exc)
    snapshot['source_path'] = str(args.ocr_json)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    suffix = hashlib.sha256(str(args.ocr_json.resolve()).encode()).hexdigest()[:10]
    target = args.out_dir / (args.ocr_json.stem + '_' + suffix + '_chunks.json')
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Saved %s entries to %s' % (len(snapshot['entries']), target))
    for note in snapshot['layout_diagnostics']:
        print('REVIEW:', note)


if __name__ == '__main__':
    main()
