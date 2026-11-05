def _order_texts(document_texts):
    """
    Sorts document texts in natural reading order.
    If the upper portion of a document has a multi-column layout (e.g. Supplier/Customer details
    on the left, Invoice No/Date/Order details on the right), separate the columns so their
    respective multi-line addresses and key-values are not horizontally interleaved.
    """
    items_with_bbox = []
    has_bboxes = False
    for item in document_texts:
        bbox = None
        prov = getattr(item, "prov", None)
        if prov and len(prov) > 0:
            b = getattr(prov[0], "bbox", None)
            if b is not None and hasattr(b, "l") and hasattr(b, "t"):
                bbox = b
                has_bboxes = True
        items_with_bbox.append((item, bbox))

    if not has_bboxes:
        return [it[0] for it in items_with_bbox]

    valid_bboxes = [b for _, b in items_with_bbox if b is not None]
    if len(valid_bboxes) < 6:
        return [it[0] for it in items_with_bbox]

    min_x = min(b.l for b in valid_bboxes)
    max_x = max(b.r for b in valid_bboxes)
    min_y = min(b.b for b in valid_bboxes)
    max_y = max(b.t for b in valid_bboxes)
    page_h = max_y - min_y
    page_w = max_x - min_x
    if page_w < 50 or page_h < 50:
        return [it[0] for it in items_with_bbox]

    mid_x = min_x + page_w * 0.48
    header_threshold_y = min_y + page_h * 0.35

    header_left = []
    header_right = []
    rest = []

    for it, b in items_with_bbox:
        if b is not None and b.t >= header_threshold_y:
            if b.r <= mid_x + page_w * 0.08:
                header_left.append((it, b))
            elif b.l >= mid_x - page_w * 0.08:
                header_right.append((it, b))
            else:
                rest.append((it, b))
        else:
            rest.append((it, b))

    if len(header_left) >= 3 and len(header_right) >= 3:
        header_top_y = min(header_left[0][1].t, header_right[0][1].t)
        titles = [x for x in rest if x[1] is not None and x[1].t > header_top_y]
        lower_rest = [x for x in rest if x not in titles]

        titles.sort(key=lambda x: -x[1].t)
        header_left.sort(key=lambda x: -x[1].t)
        header_right.sort(key=lambda x: -x[1].t)
        lower_rest.sort(key=lambda x: -x[1].t if x[1] is not None else 0)

        ordered = [x[0] for x in titles] + [x[0] for x in header_left] + [x[0] for x in header_right] + [x[0] for x in lower_rest]
        return ordered

    return [it[0] for it in items_with_bbox]


def extract_document(document):
    result = {"texts": [], "tables": [], "pictures": [], "markdown": ""}

    ordered_texts = _order_texts(getattr(document, "texts", []))
    for item in ordered_texts:
        result["texts"].append({
            "text": item.text,
            "label": getattr(item, "label", None),
            "level": getattr(item, "level", None),
        })

    for table in document.tables:
        rows = []
        for row in table.data.grid:
            rows.append([cell.text if cell is not None else "" for cell in row])
        result["tables"].append({"rows": rows})

    for picture in document.pictures:
        result["pictures"].append({"type": type(picture).__name__})

    # Full reading-order text incl. tables. Used by the layout-independent
    # fallback layers, so invoices without proper tables still work.
    try:
        result["markdown"] = document.export_to_markdown()
    except Exception:
        result["markdown"] = "\n".join(t["text"] for t in result["texts"])

    return result
