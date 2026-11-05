"""
Spatial Layout Engine for Digital Documents
Performs 2D bounding-box layout analysis, Table Zone Isolation, and Recursive XY-Cut segmentation
to reconstruct natural visual reading order and preserve table grids.
"""
import re
from typing import Any, Dict, List, Tuple


TABLE_HEADER_PAT = re.compile(r"\b(?:particulars|description|item(?:\s*name)?)\b", re.I)
TABLE_COL_PAT = re.compile(r"\b(?:rate|amount|qty|quantity|units?|hrs\.?|sac|hsn|price|total)\b", re.I)
TABLE_END_PAT = re.compile(
    r"\b(?:grand\s*total|net\s*amount|total\s*payable|balance\s*due|amount\s*payable|sub\s*total|amount\s*chargeable|tax\s*amount\s*\(in\s*words\)|\btotal)\b",
    re.I,
)


def extract_spatial_pdf(file_path: str) -> Dict[str, Any]:
    """
    Extracts structured layout from a digital PDF using pypdfium2 bounding boxes.
    Returns:
        {
            "text": full_reconstructed_text,
            "texts": [{"text": line, "bbox": [x0, y0, x1, y1]} for line in lines],
            "raw_pages": [page_text, ...]
        }
    """
    import pypdfium2 as pdfium

    pdf_doc = pdfium.PdfDocument(file_path)
    all_pages_text = []
    text_elements = []
    raw_stream_pages = []

    try:
        for page_idx, page in enumerate(pdf_doc):
            tp = page.get_textpage()
            raw_page_stream = tp.get_text_range() or ""
            raw_stream_pages.append(raw_page_stream)
            # Check for font encoding corruption (e.g. non-standard ToUnicode CMap)
            bad_ctrl = sum(1 for c in raw_page_stream if ord(c) < 32 and c not in "\n\r\t")
            if len(raw_page_stream) > 0 and (bad_ctrl / len(raw_page_stream)) > 0.03:
                tp.close()
                page.close()
                return {"text": "", "texts": [], "raw_pages": [], "raw_stream": "", "corrupted_font": True}

            n_chars = tp.count_chars()
            n_rects = tp.count_rects()
            if n_rects == 0 or (n_chars > 50 and n_rects > n_chars * 0.25):
                # When rects are character-level, extracting each rect individually produces
                # spaced-out characters ("S m b s u r e"). In this case, get_text_range()
                # provides natural font word spacing and layout.
                raw = raw_page_stream
                all_pages_text.append(raw)
                for line in raw.splitlines():
                    if line.strip():
                        text_elements.append({"text": line.strip()})
                tp.close()
                page.close()
                continue

            items = []
            for i in range(n_rects):
                r = tp.get_rect(i)  # (x0, y0, x1, y1)
                txt = tp.get_text_bounded(*r).strip()
                if txt:
                    items.append({
                        "text": txt,
                        "x0": r[0],
                        "y0": r[1],
                        "x1": r[2],
                        "y1": r[3],
                        "height": r[3] - r[1],
                        "width": r[2] - r[0],
                    })

            tp.close()
            page.close()

            if not items:
                continue

            # Detect Table Zones to protect table rows from vertical slicing
            page_blocks = partition_page_zones(items)

            page_block_strings = []
            for b in page_blocks:
                b_lines = format_block_lines(b)
                if b_lines:
                    page_block_strings.append("\n".join(b_lines))
                    for line_str in b_lines:
                        text_elements.append({"text": line_str})

            page_text = "\n\n".join(page_block_strings)
            all_pages_text.append(page_text)

    finally:
        pdf_doc.close()

    full_text = "\n\n".join(all_pages_text)
    return {
        "text": full_text,
        "texts": text_elements,
        "raw_pages": all_pages_text,
        "raw_stream": "\n\n".join(raw_stream_pages),
    }


def partition_page_zones(items: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    Isolates tabular regions from non-tabular blocks.
    Tabular regions are formatted row-by-row without vertical cuts.
    Non-tabular regions are decomposed using Recursive XY-Cut.
    """
    items_by_y = sorted(items, key=lambda it: (-it["y1"], it["x0"]))

    # Look for table header
    table_header_y = None
    for it in items_by_y:
        txt = it["text"]
        if TABLE_HEADER_PAT.search(txt):
            if TABLE_COL_PAT.search(txt) or any(
                TABLE_COL_PAT.search(other["text"])
                for other in items_by_y
                if abs(other["y0"] - it["y0"]) < 8.0 and other is not it
            ):
                table_header_y = it["y1"]
                break

    # Look for table end / grand total
    table_end_y = None
    if table_header_y is not None:
        for it in reversed(items_by_y):
            if it["y1"] < table_header_y and TABLE_END_PAT.search(it["text"]):
                table_end_y = it["y0"]
                break

    if table_header_y is not None and table_end_y is not None and table_header_y > table_end_y:
        # We have a well-defined table zone
        top_items = [it for it in items if it["y0"] >= table_header_y - 3.0]
        table_items = [it for it in items if table_header_y + 3.0 > it["y1"] and it["y0"] >= table_end_y - 5.0]
        bottom_items = [it for it in items if it["y1"] < table_end_y - 3.0]

        result_blocks = []
        if top_items:
            result_blocks.extend(xy_cut_blocks(top_items))
        if table_items:
            # Table items remain a single cohesive grid block
            result_blocks.append(table_items)
        if bottom_items:
            result_blocks.extend(xy_cut_blocks(bottom_items))
        return result_blocks

    return xy_cut_blocks(items)


def find_h_cuts(items: List[Dict[str, Any]], min_gap: float) -> Tuple[List[int], float]:
    if not items or len(items) < 2:
        return [], 0.0
    by_y = sorted(items, key=lambda it: (-it["y1"], it["x0"]))
    cuts = []
    max_gap = 0.0
    cur_y0 = by_y[0]["y0"]
    for i in range(len(by_y) - 1):
        cur_y0 = min(cur_y0, by_y[i]["y0"])
        gap = cur_y0 - by_y[i + 1]["y1"]
        if gap >= min_gap:
            cuts.append(i + 1)
            if gap > max_gap:
                max_gap = gap
            cur_y0 = by_y[i + 1]["y0"]
    return cuts, max_gap


def find_v_cuts(items: List[Dict[str, Any]], min_gap: float) -> Tuple[List[int], float]:
    if not items or len(items) < 2:
        return [], 0.0
    by_x = sorted(items, key=lambda it: it["x0"])
    cuts = []
    max_gap = 0.0
    cur_x1 = by_x[0]["x1"]
    for i in range(len(by_x) - 1):
        cur_x1 = max(cur_x1, by_x[i]["x1"])
        gap = by_x[i + 1]["x0"] - cur_x1
        if gap >= min_gap:
            # Do not cut if items across the gap are colon-prefixed values or direct key-value continuations
            nxt_txt = by_x[i + 1]["text"].lstrip()
            if nxt_txt.startswith((":", "-", "=")):
                continue
            if any(it["text"].lstrip().startswith((":", "-", "=")) for it in by_x[i + 1:] if abs(it["y0"] - by_x[i]["y0"]) < 8.0):
                continue
            cuts.append(i + 1)
            if gap > max_gap:
                max_gap = gap
            cur_x1 = by_x[i + 1]["x1"]
    return cuts, max_gap


def xy_cut_blocks(items: List[Dict[str, Any]], min_gap_h: float = 4.0, min_gap_v: float = 6.0) -> List[List[Dict[str, Any]]]:
    """
    Recursive XY-Cut block decomposition.
    Partitions 2D bounding boxes into natural reading order blocks.
    Prioritizes prominent vertical column gutters over within-paragraph line spacing.
    """
    if not items:
        return []
    if len(items) == 1:
        return [items]

    h_cuts, max_h = find_h_cuts(items, min_gap_h)
    v_cuts, max_v = find_v_cuts(items, min_gap_v)

    # When a distinct vertical gutter separates parallel columns (e.g. Bill To / Ship To),
    # vertical cut takes priority over horizontal cuts so columns remain intact.
    if v_cuts and (not h_cuts or max_v > max_h):
        by_x = sorted(items, key=lambda it: it["x0"])
        blocks = []
        start = 0
        for cut in v_cuts:
            blocks.extend(xy_cut_blocks(by_x[start:cut], min_gap_h, min_gap_v))
            start = cut
        blocks.extend(xy_cut_blocks(by_x[start:], min_gap_h, min_gap_v))
        return blocks
    elif h_cuts:
        by_y = sorted(items, key=lambda it: (-it["y1"], it["x0"]))
        blocks = []
        start = 0
        for cut in h_cuts:
            blocks.extend(xy_cut_blocks(by_y[start:cut], min_gap_h, min_gap_v))
            start = cut
        blocks.extend(xy_cut_blocks(by_y[start:], min_gap_h, min_gap_v))
        return blocks
    elif v_cuts:
        by_x = sorted(items, key=lambda it: it["x0"])
        blocks = []
        start = 0
        for cut in v_cuts:
            blocks.extend(xy_cut_blocks(by_x[start:cut], min_gap_h, min_gap_v))
            start = cut
        blocks.extend(xy_cut_blocks(by_x[start:], min_gap_h, min_gap_v))
        return blocks

    return [items]


def format_block_lines(block_items: List[Dict[str, Any]]) -> List[str]:
    """
    Groups items within a spatial block into visual lines sorted top-to-bottom,
    with cells within each line sorted strictly left-to-right.
    """
    if not block_items:
        return []

    block_items.sort(key=lambda it: (-it["y1"], it["x0"]))
    lines: List[Dict[str, Any]] = []

    for it in block_items:
        placed = False
        for line in lines:
            overlap_y0 = max(it["y0"], line["y0"])
            overlap_y1 = min(it["y1"], line["y1"])
            overlap = overlap_y1 - overlap_y0
            min_h = min(it["height"], line["height"])
            if min_h > 0 and (overlap / min_h) > 0.35:
                line["items"].append(it)
                line["y0"] = min(line["y0"], it["y0"])
                line["y1"] = max(line["y1"], it["y1"])
                placed = True
                break
        if not placed:
            lines.append({
                "y0": it["y0"],
                "y1": it["y1"],
                "height": it["height"],
                "items": [it]
            })

    lines.sort(key=lambda l: -l["y1"])
    result = []
    for l in lines:
        # Sort tokens strictly left-to-right by horizontal coordinate
        l["items"].sort(key=lambda it: it["x0"])
        parts = []
        for idx, it in enumerate(l["items"]):
            txt = it["text"]
            if not parts:
                parts.append((txt, 0.0))
                continue
            prev_it = l["items"][idx - 1]
            gap = it["x0"] - prev_it["x1"]
            is_punct = txt in (".", ",", "/", "-", ":", ")", "%") or prev_it["text"] in ("/", "-", "(", "₹", "$") or txt.startswith((".", ","))
            is_digit_split = (prev_it["text"].isdigit() and (txt.isdigit() or txt.startswith("."))) or (prev_it["text"].endswith(".") and txt.isdigit())
            is_char_split = len(prev_it["text"]) <= 2 and len(txt) <= 2 and gap < 3.0
            if gap < 2.5 or (is_punct and gap < 4.0) or (is_digit_split and gap < 4.0) or is_char_split:
                prev_txt, prev_gap = parts[-1]
                parts[-1] = (prev_txt + txt, prev_gap)
            else:
                parts.append((txt, gap))

        line_str = ""
        for p_idx, (p_txt, p_gap) in enumerate(parts):
            if p_idx == 0:
                line_str = p_txt
            elif p_gap >= 12.0:
                line_str += "  " + p_txt
            else:
                line_str += " " + p_txt
        result.append(line_str)

    return result
