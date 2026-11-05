import html
import re

GSTIN_PATTERN = re.compile(r"\b\d{2}[A-Z]{4,5}\d{4}[A-Z0-9]{1,2}Z[A-Z0-9]\b")
GSTIN_LABELED_PATTERN = re.compile(
    r"\b(?:GSTIN|GST\s*(?:NO|NUM|NUMBER|#|REG\w*)?|STIN)\s*[:.\-\s]*([0-9]{2}[A-Z]{4,5}[0-9]{4}[A-Z0-9]{1,2}Z[A-Z0-9])",
    re.IGNORECASE
)

PARTY_SECTION_LABELS = {
    "bill to": "customer", "billed to": "customer", "invoice to": "customer",
    "customer": "customer", "customer details": "customer", "buyer": "customer",
    "buyer details": "customer", "sold to": "customer", "to": "customer",
    "party details": "customer", "party details :": "customer", "party name": "customer",
    "details of receiver": "customer", "details of recipient": "customer", "recipient details": "customer",
    "billed to party": "customer",
    "supplier": "supplier", "supplier details": "supplier", "vendor": "supplier",
    "vendor details": "supplier", "billed by": "supplier", "bill from": "supplier",
    "from": "supplier", "issued by": "supplier",
}

FIELD_LABELS = {
    "invoice_number": {
        "invoice no", "invoice number", "invoice #", "inv no", "inv number", "invoice id",
        "bill no", "bill number", "bill #", "voucher no", "voucher number", "voucher #",
        "doc no", "document no", "document number", "pi no", "proforma no", "proforma invoice no",
        "ref no", "reference no", "tax invoice no", "tax invoice number", "receipt no", "invoice ref"
    },
    "invoice_date": {"invoice date", "issue date", "inv date", "bill date", "dated", "date", "date of issue",
                     "date of invoice", "invoice dt", "bill dt", "invoice dated", "tax invoice date"},
    "due_date": {"due date", "payment due", "due on", "pay by", "payment due date"},
}

LINE_ITEM_HEADERS = {
    "description": {"description", "item & description", "item and description", "particulars", "item", "service", "details", "activity", "product", "product or service", "service description"},
    "quantity": {"qty", "quantity", "units", "unit", "no", "nos"},
    "rate": {"rate", "unit price", "price", "unit rate", "unit cost"},
    "amount": {"amount", "total", "value", "taxable value", "line total", "line amount", "amt"},
}

TAX_LABELS = {
    "cgst": {"cgst", "c.g.s.t", "central gst", "central goods and services tax", "central tax", "cgst9", "cgst14", "cgst6", "cgst2.5", "cgst amt", "cgst amount"},
    "sgst": {"sgst", "s.g.s.t", "state gst", "state goods and services tax", "state tax", "sgst9", "sgst14", "sgst6", "sgst2.5", "utgst", "sgst amt", "sgst amount"},
    "igst": {"igst", "i.g.s.t", "integrated gst", "integrated goods and services tax", "integrated tax", "igst18", "igst12", "igst5", "igst28", "igst amt", "igst amount"},
    "generic_gst": {"gst", "g.s.t", "goods and services tax", "total gst", "total tax", "tax amount"},
}

SUMMARY_LABELS = {
    "taxable_amount": {
        "taxable amount", "taxable value", "taxable", "subtotal", "sub total",
        "sub total amount", "item total", "charges", "rental charges",
        "service charges", "space charges", "base amount", "basic amount",
        "basic value", "tariff", "assessable value", "chargeable amount",
    },
    "total": {
        "total", "grand total", "invoice total", "total amount", "amount payable",
        "net total", "total payable", "total invoice value", "invoice value",
        "net amount", "net value", "net payable", "balance due", "total charges",
    },
}

LINE_ITEM_STOP_WORDS = {
    "gst", "cgst", "sgst", "igst", "restaurant bill", "total", "subtotal",
    "sub total", "grand total", "tax", "taxes", "amount payable", "net total",
    "net amount", "net value", "net payable", "thanks for your business",
    "balance due", "round off", "roundoff", "discount", "charges", "total charges", "in words",
}


def clean(value):
    if value is None: return ""
    return " ".join(html.unescape(str(value)).split()).strip()


def normalize(value):
    value = clean(value).lower().replace("", "")
    value = re.sub(r"[.:,#]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def find_gstin(value):
    if not value:
        return None
    cleaned = clean(value).upper()
    match = GSTIN_PATTERN.search(cleaned)
    if match:
        return match.group(0)
    lm = GSTIN_LABELED_PATTERN.search(cleaned)
    if lm:
        val = lm.group(1).upper()
        if GSTIN_PATTERN.fullmatch(val):
            return val
    return None


_NORM_PARTY_SECTION_LABELS = {normalize(x): role for x, role in PARTY_SECTION_LABELS.items()}

_NORM_FIELD_MAP = {}
for field, labels in FIELD_LABELS.items():
    for label in labels:
        _NORM_FIELD_MAP[normalize(label)] = field

_NORM_LINE_HEADER_MAP = {}
for field, labels in LINE_ITEM_HEADERS.items():
    for label in labels:
        _NORM_LINE_HEADER_MAP[normalize(label)] = field

_NORM_TAX_LABEL_MAP = {}
for tax_type, labels in TAX_LABELS.items():
    for label in labels:
        _NORM_TAX_LABEL_MAP[normalize(label)] = tax_type

_EMBEDDED_FIELD_PATTERNS = {
    "invoice_number": re.compile(r"(?:invoice\s*(?:no\.?|number|#)|inv\s*(?:no\.?|number)|bill\s*(?:no\.?|number))\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9./_\- ]*?)(?=\s*(?:date|due|gst|vendor|client|amount|\Z))", re.I),
    "invoice_date": re.compile(r"(?:invoice\s*date|issue\s*date|inv\s*date|bill\s*date|dated?)\s*[:#-]?\s*(\d{1,2}(?:\s*(?:st|nd|rd|th))?\s+[A-Za-z]{3,9},?\s+\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", re.I),
    "due_date": re.compile(r"(?:due\s*date|payment\s*due)\s*[:#-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", re.I),
}


def is_party_section(value):
    return normalize(value) in _NORM_PARTY_SECTION_LABELS


def party_role(value):
    return _NORM_PARTY_SECTION_LABELS.get(normalize(value))


def identify_field(value):
    return _NORM_FIELD_MAP.get(normalize(value))


def identify_embedded_field(value):
    raw = clean(value)
    for field, pattern in _EMBEDDED_FIELD_PATTERNS.items():
        match = pattern.search(raw)
        if match:
            return field, match.group(1).strip()
    return None, None


def identify_line_header(value):
    n = normalize(value)
    direct = _NORM_LINE_HEADER_MAP.get(n)
    if direct:
        return direct
    # semantic fallback for common compound headers
    if "description" in n or "particular" in n: return "description"
    if "product or service" in n: return "description"
    if n in {"qty", "quantity", "units", "unit"} or n.startswith("quantity "): return "quantity"
    if "unit price" in n or "unit rate" in n or n == "rate": return "rate"
    if n == "amount" or n.endswith(" amount") or n in {"amt", "line total"}: return "amount"
    return None


def identify_tax_label(value):
    raw = clean(value).lower()
    if "\ufffd" in raw:
        return None
    # If the label explicitly says rate or % only (e.g. "CGST - %"), it is a rate header not amount
    if re.search(r"\b(?:rate|%)\b", raw) and not re.search(r"\b(?:amt|amount)\b", raw):
        return None
    # Normalize unicode replacement character or OCR cut between c/s and st
    normalized_raw = re.sub(r"\b([csi])[\ufffd\?]?st\b", r"\1gst", raw)
    normalized_raw = re.sub(r"\b([csi])[\ufffd\?]?st\s*\(", r"\1gst(", normalized_raw)
    n = normalize(normalized_raw)
    direct = _NORM_TAX_LABEL_MAP.get(n)
    if direct:
        return direct
    if re.search(r"\bc[\ufffd\?]?g?s[\ufffd\?]?t\d*\b|central\s*(?:gst|tax)", normalized_raw) or normalized_raw.startswith("cgst") or normalized_raw.startswith("cst(") or "cgst" in normalized_raw:
        return "cgst"
    if re.search(r"\bs[\ufffd\?]?g?s[\ufffd\?]?t\d*\b|state\s*(?:gst|tax)|utgst\d*", normalized_raw) or normalized_raw.startswith("sgst") or normalized_raw.startswith("sst(") or "sgst" in normalized_raw:
        return "sgst"
    if re.search(r"\bi[\ufffd\?]?g?s[\ufffd\?]?t\d*\b|integrated\s*(?:gst|tax)", normalized_raw) or normalized_raw.startswith("igst") or "igst" in normalized_raw:
        return "igst"
    if re.search(r"\b(?:total\s*tax|total\s*gst|tax\s*amount)\b", normalized_raw):
        return "generic_gst"
    if re.fullmatch(r"gst(?:\s*\(\d+%\))?", n):
        return "generic_gst"
    return None


def identify_summary_label(value):
    n = normalize(value)
    for field, labels in SUMMARY_LABELS.items():
        if n in {normalize(x) for x in labels}: return field
    if any(k in n for k in ("grand total", "invoice total", "net amount", "net payable", "net total", "balance due", "total payable")):
        return "total"
    if any(k in n for k in ("taxable amount", "taxable value", "taxable", "subtotal", "sub total", "item total")):
        return "taxable_amount"
    return None


def is_number(value):
    if value is None: return False
    s = str(value).replace(",", "").replace("₹", "").replace("$", "").replace("€", "").strip()
    s = re.sub(r"(?i)\b(?:inr|rs\.?)\b", "", s).rstrip("/-").strip()
    if s.endswith("%"): return False
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def build_key_value_candidates(tables):
    candidates = []
    for ti, rows in enumerate(tables):
        for ri, row in enumerate(rows):
            cells = [clean(c) for c in row]
            for ci, cell in enumerate(cells):
                field = identify_field(cell)
                value = None
                if field:
                    for nxt in cells[ci+1:]:
                        if not nxt: continue
                        if identify_field(nxt): break
                        value = nxt; break
                else:
                    field, value = identify_embedded_field(cell)
                if field and value:
                    candidates.append({"field": field, "value": value, "table_index": ti, "row": ri, "column": ci, "confidence": 0.92 if not identify_field(cell) else 0.9})
    return candidates


def _party_candidate(role, label, values, gstin, ti, ri, ci, confidence=0.85):
    return {"section": "party", "role": role, "section_label": label, "values": values, "gstin": gstin, "table_index": ti, "row": ri, "column": ci, "confidence": confidence}


def build_party_candidates(tables):
    candidates = []
    for ti, rows in enumerate(tables):
        anchors = []
        for ri, row in enumerate(rows):
            cells = [clean(c) for c in row]
            found = [(ci, c, party_role(c)) for ci, c in enumerate(cells) if c and is_party_section(c)]
            if found:
                # A row such as "Billed By | Billed To" creates independent column anchors.
                anchors = [{"column": ci, "label": c, "role": role, "values": [], "gstin": None, "start": ri} for ci, c, role in found]
                for ci, c, role in found:
                    # duplicate labels in merged cells should not create duplicate parties
                    if sum(1 for a in anchors if a["label"].lower() == c.lower()) > 1:
                        pass
                continue
            if not anchors:
                continue
            # stop party collection when a line-item header appears
            if any(identify_line_header(c) for c in cells if c):
                for a in anchors:
                    if a["values"]:
                        candidates.append(_party_candidate(a["role"], a["label"], a["values"], a["gstin"], ti, a["start"], a["column"]))
                anchors = []
                continue
            for a in anchors:
                ci = a["column"]
                # use the anchor column when possible; for one-column party blocks collect all cells
                selected = []
                if len(anchors) == 1:
                    selected = cells
                elif ci < len(cells) and cells[ci]:
                    selected = [cells[ci]]
                # If Docling merged the row into the left cell, allow the full row only for the first anchor.
                elif ci == 0 and cells:
                    selected = [c for c in cells if c]
                for cell in selected:
                    if not cell or is_party_section(cell) or identify_field(cell): continue
                    if cell.lower().strip() in {"to", "from", "customer id"}: continue
                    found_gstin = find_gstin(cell)
                    if found_gstin:
                        a["gstin"] = found_gstin
                        if cell not in a["values"]: a["values"].append(cell)
                        continue
                    if re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", cell) or is_number(cell): continue
                    if cell not in a["values"]: a["values"].append(cell)
        for a in anchors:
            if a["values"]:
                candidates.append(_party_candidate(a["role"], a["label"], a["values"], a["gstin"], ti, a["start"], a["column"]))
    return candidates


def build_line_item_candidates(tables):
    candidates = []
    for ti, rows in enumerate(tables):
        header_row_index = None; column_map = {}
        for ri, row in enumerate(rows):
            cells = [clean(c) for c in row]; current = {}
            for ci, cell in enumerate(cells):
                h = identify_line_header(cell)
                if h: current[h] = ci
            if "description" in current and ("amount" in current or "rate" in current):
                header_row_index, column_map = ri, current; break
        if header_row_index is None: continue
        for ri in range(header_row_index + 1, len(rows)):
            cells = [clean(c) for c in rows[ri]]
            if not any(cells): continue
            di = column_map.get("description")
            description = cells[di] if di is not None and di < len(cells) else None
            if not description: continue
            norm_desc = normalize(description)
            if any(w in norm_desc for w in ("round off", "roundoff", "discount")) or identify_tax_label(description) or identify_summary_label(description):
                continue
            if norm_desc in {normalize(x) for x in LINE_ITEM_STOP_WORDS}: continue
            item = {"description": description, "quantity": None, "rate": None, "amount": None, "table_index": ti, "row": ri, "confidence": 0.8}
            for field in ("quantity", "rate", "amount"):
                ci = column_map.get(field)
                if ci is not None and ci < len(cells): item[field] = cells[ci] or None
            if not any(item[x] for x in ("quantity", "rate", "amount")): continue
            prev = candidates[-1] if candidates and candidates[-1]["table_index"] == ti else None
            # a row with only a description (+ a merged-cell repeat of the same amount) continues the item above
            if prev and item["quantity"] is None and item["rate"] is None and item["amount"] in (None, prev["amount"]):
                prev["description"] = clean(prev["description"] + " " + description)
                continue
            candidates.append(item)
    return candidates


def build_tax_candidates(tables):
    candidates = []
    for ti, rows in enumerate(tables):
        for ri, row in enumerate(rows):
            cells = [clean(c) for c in row]
            for ci, cell in enumerate(cells):
                tax_type = identify_tax_label(cell)
                if not tax_type: continue
                num_cells = []
                for nxt in cells[ci+1:]:
                    if not nxt: continue
                    if nxt.endswith("%") or re.fullmatch(r"\d+(?:\.\d+)?\s*%", nxt): continue
                    if identify_tax_label(nxt) or identify_summary_label(nxt): break
                    if is_number(nxt):
                        num_cells.append(nxt)
                if num_cells:
                    chosen = num_cells[-1]
                    for cand_num in num_cells:
                        clean_num = cand_num.replace(",", "").replace("₹", "").replace("$", "").replace("€", "").strip()
                        clean_num = re.sub(r"(?i)\b(?:inr|rs\.?)\b", "", clean_num).rstrip("/-").strip()
                        try:
                            val_f = float(clean_num)
                            if "." in clean_num or (len(num_cells) > 1 and int(val_f) not in {0, 5, 9, 12, 14, 18, 28}):
                                chosen = cand_num
                                break
                        except ValueError:
                            pass
                    candidates.append({"tax_type": tax_type, "value": chosen, "table_index": ti, "row": ri, "column": ci, "evidence": cell, "confidence": 0.8})
    return candidates


def build_summary_candidates(tables):
    candidates = []
    for ti, rows in enumerate(tables):
        for ri, row in enumerate(rows):
            cells = [clean(c) for c in row]
            for ci, cell in enumerate(cells):
                field = identify_summary_label(cell)
                if not field: continue
                for nxt in cells[ci+1:]:
                    if not nxt: continue
                    if nxt.endswith("%") or re.fullmatch(r"\d+(?:\.\d+)?\s*%", nxt): continue
                    if identify_tax_label(nxt): continue
                    if identify_summary_label(nxt): break
                    if is_number(nxt):
                        candidates.append({"field": field, "value": nxt, "table_index": ti, "row": ri, "column": ci, "evidence": cell, "confidence": 0.9}); break
    return candidates


def build_semantic_candidates(extracted):
    tables = []
    for table in extracted.get("tables", []):
        rows = table.get("rows", []) if isinstance(table, dict) else table
        if rows: tables.append(rows)
    return {"key_values": build_key_value_candidates(tables), "parties": build_party_candidates(tables), "line_items": build_line_item_candidates(tables), "taxes": build_tax_candidates(tables), "summaries": build_summary_candidates(tables)}
