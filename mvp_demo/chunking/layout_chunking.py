"""Offline layout chunking for OCR page dictionaries. Python 3.9+, stdlib only.

Input: OCR page JSON, or selected OCR/VLM Markdown/HTML text.
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
if __package__:
    from .toc_filter import remove_toc_regions
else:  # Also support running this file directly for offline tests.
    from toc_filter import remove_toc_regions


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
    if len(re.findall(r'<table\b', text, re.I)) > 1:
        raise ValueError('Nested tables require review before chunking')
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
        if any(len(row) != width for row in grid):
            raise ValueError('HTML table has inconsistent column counts; preserve explicit blank cells')
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
        grid = [_markdown_cells(line) for line in lines]
        if len(grid) > 1 and all(re.fullmatch(r':?-{3,}:?', cell) for cell in grid[1]):
            labels, rows = grid[0], grid[2:]
            if any(len(row) != len(labels) for row in grid[1:]):
                raise ValueError('Markdown table has inconsistent column counts; preserve explicit blank cells')
        else:
            labels, rows = ['Column %s' % (i + 1) for i in range(max(map(len, grid)))], grid
            diagnostics.append('Pipe table without explicit header separator; using positional column labels')
    result = []
    for n, row in enumerate(rows, 1):
        count = max(len(labels), len(row))
        values = []
        for c in range(count):
            label = labels[c] if c < len(labels) else 'Column %s' % (c + 1)
            value = row[c] if c < len(row) else '[unclear: missing cell]'
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


MAX_ATOMIC_CHARS = 8000
FORM_BLOCKS = LABELS | VALUES | {'form_item', 'form_field', 'checkbox'}
HEADING_CONNECTORS = {'of', 'the', 'and', 'on', 'for', 'to', 'in', 'a'}


def _check_chunk_sizes(parent_max_chars, child_max_chars):
    """Fail early when the requested parent/child sizes cannot work together."""
    if child_max_chars < 80 or parent_max_chars < child_max_chars + 100:
        raise ValueError('Require child_max_chars >= 80 and parent_max_chars >= child_max_chars + 100')


def _remove_toc_blocks(blocks, toc_filter, source_name, rejected, notes):
    """Remove only OCR blocks that sit completely inside a detected TOC region."""
    if toc_filter is None or not blocks:
        return blocks

    # Apply the existing TOC detector only to complete block ranges; preserve partial blocks.
    text, spans, cursor = '', [], 0
    for block in blocks:
        spans.append((cursor, cursor + len(block.text), block))
        text += block.text + '\n\n'
        cursor = len(text)

    toc_rejected = []
    toc_filter(text.rstrip(), toc_rejected, source_name)

    line_offsets, offset = [], 0
    for line in text.splitlines(keepends=True):
        line_offsets.append(offset)
        offset += len(line)
    line_offsets.append(offset)

    dropped_ids = set()
    for event in toc_rejected:
        if event.get('reason') != 'toc_region':
            continue
        start_of_toc = line_offsets[event['line_start'] - 1]
        end_of_toc = line_offsets[event['line_end']]
        for start, end, block in spans:
            if start >= start_of_toc and end <= end_of_toc:
                dropped_ids.add(block.block_id)
                rejected.append({
                    'stage': 'layout',
                    'reason': 'toc_region',
                    'text': block.text,
                    'block_id': block.block_id,
                    'page': block.page,
                })
            elif start < end_of_toc and end > start_of_toc:
                notes.append('TOC boundary crosses %s; retained block for review' % block.block_id)

    return [block for block in blocks if block.block_id not in dropped_ids]


def _looks_like_cross_page_heading(block, next_block):
    """Recognise a short footer that is really a heading continued on the next page."""
    words = block.text.split()
    title_like = all(
        word[:1].isupper() or word.lower() in HEADING_CONNECTORS
        for word in words
    )
    return (
        block.kind == 'footer'
        and len(words) <= 8
        and title_like
        and next_block is not None
        and _edge(block) == 'bottom'
        and next_block.page == block.page + 1
        and next_block.kind == 'text'
    )


def _block_units(block, field_pairs, child_max_chars, notes):
    """Turn one OCR block into one or more chunkable text units."""
    sources = [block]
    if block.block_id in field_pairs:
        value = field_pairs[block.block_id]
        sources.append(value)
        texts = [block.text + ': ' + (value.text or '[blank]')]
        atomic = True
    elif block.kind in {'table', 'table_body'}:
        texts = table_units(block, notes)
        atomic = True
    else:
        texts = [block.text or '[blank]']
        atomic = block.kind in FORM_BLOCKS

    units = []
    for text in texts:
        if atomic and len(text) <= MAX_ATOMIC_CHARS:
            pieces = [text]
            if len(text) > child_max_chars:
                notes.append(
                    'Atomic unit %s exceeds child character budget; retained intact'
                    % block.block_id
                )
        else:
            if atomic:
                raise ValueError('Atomic table row/field exceeds 8000 characters; review before ingestion')
            pieces = _split_prose(text, child_max_chars)
        units.extend((piece, sources, atomic) for piece in pieces)
    return units


def _build_sections(blocks, child_max_chars, notes):
    """Group ordered blocks beneath their nearest recognised heading."""
    pairs = _pair_fields(blocks, notes)
    paired_value_ids = {block.block_id for block in pairs.values()}
    sections = []
    current_units = []
    current_title = ''

    for index, block in enumerate(blocks):
        if block.block_id in paired_value_ids:
            continue

        next_block = blocks[index + 1] if index + 1 < len(blocks) else None
        is_heading = block.kind in HEADINGS
        if _looks_like_cross_page_heading(block, next_block):
            is_heading = True
            notes.append(
                'Treated retained margin block %s as a possible cross-page heading'
                % block.block_id
            )

        if is_heading:
            if current_units:
                sections.append((current_title, current_units))
            current_title = block.text
            # Keep the heading inside its own section text, including heading-only sections.
            current_units = [(block.text, [block], False)]
            continue

        current_units.extend(_block_units(block, pairs, child_max_chars, notes))

    if current_units:
        sections.append((current_title, current_units))
    return sections


def _group_units(units, character_limit):
    """Pack adjacent units together without passing the requested character limit."""
    groups, current_group, current_length = [], [], 0
    for unit in units:
        separator_size = 2 if current_group else 0
        new_size = len(unit[0]) + separator_size
        if current_group and current_length + new_size > character_limit:
            groups.append(current_group)
            current_group, current_length = [], 0
        current_group.append(unit)
        current_length += len(unit[0]) + (2 if len(current_group) > 1 else 0)
    if current_group:
        groups.append(current_group)
    return groups


def _unique_sources(units):
    """Return each source block once, while preserving its document order."""
    return {block.block_id: block for unit in units for block in unit[1]}


def _build_entries(sections, metadata, parent_max_chars, child_max_chars):
    """Build the existing parent/child entry dictionaries from section units."""
    entries = []
    for section_title, section_units in sections:
        parent_groups = _group_units(section_units, parent_max_chars)
        for parent_units in parent_groups:
            parent = '\n\n'.join(u[0] for u in parent_units)
            parent_sources = _unique_sources(parent_units)
            parent_id = hashlib.sha256(
                (metadata.get('source_url', '') + str(len(entries)) + parent).encode()
            ).hexdigest()[:24]

            # Atomic table rows and form fields remain whole, even if they pass this soft limit.
            child_groups = _group_units(parent_units, child_max_chars)
            for child_units in child_groups:
                leaf_text = '\n\n'.join(unit[0] for unit in child_units)
                child_sources = _unique_sources(child_units)
                entries.append({**metadata, 'leaf_text':leaf_text, 'parent_text':parent,
                    'parent_id':parent_id, 'chunk_id':parent_id + ':' + str(len(entries)),
                    'section_title':section_title, 'chunking_method':'layout_aware',
                    'page_start':min(b.page for b in child_sources.values()),
                    'page_end':max(b.page for b in child_sources.values()),
                    'parent_page_start':min(b.page for b in parent_sources.values()),
                    'parent_page_end':max(b.page for b in parent_sources.values()),
                    'block_ids':list(child_sources),
                    'layout_sources':[{'page':b.page, 'block_id':b.block_id, 'block_type':b.kind, 'bbox':b.bbox} for b in child_sources.values()],
                    'oversized_child':len(leaf_text)>child_max_chars})
    return entries



def _markdown_cells(line):
    """Split pipe cells, retaining empty cells and escaped literal pipes."""
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|') and not line.endswith('\\|'):
        line = line[:-1]
    cells, cell, escaped = [], [], False
    for char in line:
        if escaped:
            cell.append(char if char in '|\\' else '\\' + char)
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == '|':
            cells.append(''.join(cell).strip())
            cell = []
        else:
            cell.append(char)
    if escaped:
        cell.append('\\')
    cells.append(''.join(cell).strip())
    return cells


def _markdown_separator(line):
    cells = _markdown_cells(line)
    return '|' in line and bool(cells) and all(
        re.fullmatch(r':?-{3,}:?', cell) for cell in cells)


class _HTMLProse(HTMLParser):
    """Convert surrounding HTML prose/headings to text; tables are parsed separately."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if re.fullmatch(r'h[1-6]', tag):
            self.parts.append('\n\n' + '#' * int(tag[1]) + ' ')
        elif tag in {'p', 'div', 'section', 'li', 'br', 'caption'}:
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in {'p', 'div', 'section', 'li', 'caption'} or re.fullmatch(r'h[1-6]', tag):
            self.parts.append('\n\n')
    def handle_data(self, data):
        self.parts.append(data)


def _html_text(text):
    parser = _HTMLProse()
    parser.feed(text)
    parser.close()
    return ''.join(parser.parts).strip()


def has_table_markup(text):
    """Detect explicit tables only. Flattened OCR lines are not recoverable tables."""
    return isinstance(text, str) and (
        bool(re.search(r'<table\b', text, re.I))
        or any(_markdown_separator(line) for line in text.splitlines())
    )


def _selected_text_blocks(text, notes):
    """Read headings, prose and complete tables in their supplied order.

    Page 0 is an internal ordering placeholder only. It is removed from output;
    Markdown without page metadata cannot tell us the original PDF page number.
    """
    blocks, headers = [], {}
    table_number = 0

    def add(content, kind):
        if content.strip():
            blocks.append(LayoutBlock(content.strip(), kind, 0,
                                      'text:b%s' % len(blocks)))

    def add_table(content):
        nonlocal table_number
        table_number += 1
        context = ' > '.join(headers[level] for level in sorted(headers))
        caption_match = re.search(r'<caption\b[^>]*>(.*?)</caption\s*>', content, re.I | re.S)
        caption = _html_text(caption_match[1]) if caption_match else ''
        prefix = '\n'.join(part for part in (
            '[Section: %s]' % context if context else '',
            '[Table %s%s]' % (table_number, ': ' + caption if caption else ''),
        ) if part)
        block = LayoutBlock(content, 'table', 0, 'text:table%s' % table_number)
        for row in table_units(block, notes):
            # Already serialized: use an atomic field so it cannot be split again.
            add(prefix + '\n' + row, 'form_item')

    def add_markdown(prose):
        lines, paragraph = prose.splitlines(), []
        def flush():
            if paragraph:
                add('\n'.join(paragraph), 'text')
                paragraph.clear()
        i = 0
        while i < len(lines):
            line = lines[i]
            fence = re.match(r'^\s*(`{3,}|~{3,})', line)
            if fence:
                flush()
                marker = fence[1]
                code = [line]
                i += 1
                while i < len(lines):
                    code.append(lines[i])
                    closed = re.fullmatch(r'\s*' + re.escape(marker[0]) + '{' + str(len(marker)) + r',}\s*', lines[i])
                    i += 1
                    if closed:
                        break
                add('\n'.join(code), 'text')
                continue
            heading = re.match(r'^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$', line)
            if heading:
                flush()
                level = len(heading[1])
                for depth in list(headers):
                    if depth >= level:
                        del headers[depth]
                headers[level] = heading[2]
                add(' > '.join(headers[d] for d in sorted(headers)), 'heading')
                i += 1
            elif i + 1 < len(lines) and '|' in line and _markdown_separator(lines[i + 1]):
                flush()
                table = [line, lines[i + 1]]
                i += 2
                while i < len(lines) and lines[i].strip() and '|' in lines[i]:
                    table.append(lines[i])
                    i += 1
                add_table('\n'.join(table))
            elif not line.strip():
                flush()
                i += 1
            else:
                paragraph.append(line)
                i += 1
        flush()

    # HTML table boundaries are explicit; do not turn their cells into paragraphs.
    cursor = 0
    for match in re.finditer(r'<table\b[^>]*>.*?</table\s*>', text, re.I | re.S):
        before = text[cursor:match.start()]
        add_markdown(_html_text(before) if re.search(r'</?(?:h[1-6]|p|div)\b', before, re.I) else before)
        add_table(match[0])
        cursor = match.end()
    tail = text[cursor:]
    if re.search(r'<table\b', tail, re.I):
        raise ValueError('Unclosed HTML table; fix selected extraction before ingestion')
    add_markdown(_html_text(tail) if re.search(r'</?(?:h[1-6]|p|div)\b', tail, re.I) else tail)
    return blocks


def build_markup_snapshot(text, base_metadata=None, *, parent_max_chars=1500,
                          child_max_chars=550, toc_filter=None):
    """Chunk final selected Markdown/HTML, preserving each table row and its headers.

    This is structure-aware text handling, with no invented spatial coordinates.
    Ordinary prose keeps its paragraph/sentence splitting. Formatted table rows
    are atomic; oversized rows are flagged for the ingest token-limit check.
    """
    if not isinstance(text, str):
        raise TypeError('Expected selected Markdown/HTML text')
    _check_chunk_sizes(parent_max_chars, child_max_chars)
    notes, rejected = [], []
    blocks = _selected_text_blocks(text, notes)
    # Tables are deliberately not passed through the TOC heuristic: numbers in
    # table cells must not be confused with contents-page references.
    entries = _build_entries(_build_sections(blocks, child_max_chars, notes),
                             dict(base_metadata or {}), parent_max_chars, child_max_chars)
    for entry in entries:
        entry['chunking_method'] = 'markdown_structure'
        for key in ('page_start', 'page_end', 'parent_page_start', 'parent_page_end'):
            entry.pop(key, None)
        for source in entry['layout_sources']:
            source['page'] = None
    notes.append('Selected text has no verified page coordinates; page metadata omitted')
    return {'schema_version': 2, 'full_text': text, 'entries': entries,
            'rejected_chunks': rejected, 'layout_diagnostics': list(dict.fromkeys(notes)),
            'chunking_method': 'markdown_structure',
            'chunking_config': {'parent_max_chars': parent_max_chars,
                                'child_max_chars': child_max_chars}}


def build_layout_snapshot(payload, base_metadata=None, *, parent_max_chars=1500,
                          child_max_chars=550, allow_partial=False, toc_filter=None):
    """Convert OCR JSON or selected Markdown/HTML into a chunking snapshot.

    This function is intentionally a short overview of the pipeline. The helper
    functions above contain the details for each individual step.
    """
    if isinstance(payload, str):
        return build_markup_snapshot(payload, base_metadata, parent_max_chars=parent_max_chars,
                                     child_max_chars=child_max_chars, toc_filter=toc_filter)
    _check_chunk_sizes(parent_max_chars, child_max_chars)

    metadata = dict(base_metadata or {})
    notes, rejected = [], []
    selected_toc_filter = remove_toc_regions if toc_filter is None else toc_filter

    original_blocks = normalise_ocr_output(payload, notes, allow_partial)
    full_text = '\n\n'.join(block.text for block in original_blocks)

    blocks = filter_repeated_margins(original_blocks, rejected, notes)
    blocks = order_blocks(blocks, notes)
    blocks = _remove_toc_blocks(
        blocks,
        selected_toc_filter,
        metadata.get('source_url', ''),
        rejected,
        notes,
    )

    sections = _build_sections(blocks, child_max_chars, notes)
    entries = _build_entries(
        sections,
        metadata,
        parent_max_chars,
        child_max_chars,
    )

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
    parser.add_argument('ocr_json', type=Path, help='Selected .md/.html/.txt, or structured OCR .json')
    parser.add_argument('--out-dir', type=Path, default=Path('test_chunking_output/layout_snapshots'))
    parser.add_argument('--allow-partial', action='store_true', help='Permit incomplete page inventory for offline tests only')
    parser.add_argument('--source-name', help='Original PDF filename for snapshot metadata')
    args = parser.parse_args()
    try:
        content = args.ocr_json.read_text(encoding='utf-8-sig')
        payload = json.loads(content) if args.ocr_json.suffix.lower() == '.json' else content
        snapshot = build_layout_snapshot(payload, {'source_url':args.source_name or args.ocr_json.stem}, allow_partial=args.allow_partial)
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(2, 'Cannot chunk input: %s\n' % exc)
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
