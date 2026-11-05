"""
Layout-independent extraction layers, used only to FILL fields the
table-based semantic pass could not find:

  Layer A  regex over the full document text (no table needed)
  Layer B  GST arithmetic check (label-free tax / total detection)

Nothing here overwrites a value that layer 1 already found.
"""
import re

from .addresses import _cells, clean_party_address, fill_addresses, valid_address
from .normalize import (
    GSTIN_PATTERN, GSTIN_LABELED_PATTERN, clean, clean_party_name, is_valid_party_name, looks_like_address, looks_like_organization,
    normalize_date, normalize_number, STATE_CODES, pos_state_code, state_from_gstin, state_from_text,
)

DATE_PAT = (r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}"
            r"|\d{1,2}(?:\s*(?:st|nd|rd|th))?\s+[A-Za-z]{3,9},?\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}"
            r"|\d{1,2}\s*[-/]\s*[A-Za-z]{3,9}\s*[-/]\s*\d{2,4}")
# must not be a slice of a longer token such as an invoice number CHN/26-27/0499
DATE_RE = re.compile(r"(?<![\w/.\-])(?:" + DATE_PAT + r")(?![\w/\-]|\.\d)")
INV_NO_LABEL = re.compile(
    r"(?:tax\s+)?(?:invoice|inv|bill|voucher|doc(?:ument)?|receipt|proforma|pi)\.?\s*(?:(?:no|number|num|id|#|ref)\b|#|\b(?=:)|(?=[:/]))|^\s*#\s*$", re.I
)
INV_DATE_LABEL = re.compile(r"(?:invoice|inv|bill|issue)?\s*dated?\b", re.I)
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_\-.]{2,}")
AMOUNT_RE = re.compile(r"\d[\d,]*(?:\.\d{1,2})?")
PERCENT = re.compile(r"-?\d+(?:\.\d+)?\s*%")
UNLABELED_NO = re.compile(r"(?m)^[\s#|*]*#\s*([A-Za-z0-9][A-Za-z0-9/_\-.]{2,})\s*$")
SEP_ROW = re.compile(r"^[\s|:\-]*$")

TOTAL_PRIORITY = ["grand total", "total charges", "total invoice value", "invoice total", "total payable",
                  "amount payable", "net payable", "net amount", "net total", "balance due", "total amount", "amount due", "total"]
TOTAL_PRIORITY_RES = [(label, re.compile(rf"\b{label}\b", re.I)) for label in TOTAL_PRIORITY]
SKIP_TOTAL = ("sub total", "subtotal", "taxable", "tax total", "total tax", "total cess", "cess", "total discount", "discount", "total gst", "in words", "words", "terms", "net ")
GOFLOATERS_HINTS = ("gofloaters", "go floaters", "smbsure", "smb sure", "gofloters", "go floter")
ADDRESS_JUNK = ("subject", "booking id", "hsn", "sac", "qty", "item &", "description", "---", "invoice", "amount", "rate")
ADDRESS_STOP = ("terms & conditions", "terms and conditions", "our bank", "bank details",
                "a/c no", "account no", "ifsc", "swift")

INV_PATS = [
    re.compile(r"\b(INV[-/][A-Za-z0-9/_\-.]{2,})\b", re.I),
    re.compile(r"(?:(?:tax\s+)?(?:invoice|inv|bill|voucher|doc(?:ument)?|receipt|proforma|p\.?i\.?))\s*(?:(?:no\.?|#|number|num|id|ref)\b|[:/#])\s*[:.\-/#\s]*([A-Za-z0-9][A-Za-z0-9/_\-.]{1,})", re.I),
    re.compile(r"\b(?:PI|P\.I\.)\.?\s*(?:no\.?|#|number|num|id|ref)?\s*[:.\-/#\s]*([A-Za-z0-9][A-Za-z0-9/_\-.]{1,})", re.I),
    re.compile(r"^\s*#\s*[:\s]*([A-Za-z0-9][A-Za-z0-9/_\-.]{2,})\s*$", re.I | re.M),
    re.compile(r"(?:tax\s+)?invoice\s*#\s*[:\s]*([A-Za-z0-9][A-Za-z0-9/_\-.]{2,})", re.I),
    re.compile(r"\bPROFORMA\s+INVOICE\s*[/:\-]\s*([A-Za-z0-9][A-Za-z0-9/_\-.]{1,})", re.I),
]
PRE_DATE_RE = re.compile(r"(?:^|\n)\s*([A-Za-z0-9][A-Za-z0-9/_\-.]{3,})\s*\n[ \t]*(?:Issue\s+Date|Invoice\s+Date|Date\s*of\s*Issue|Date)\s*:", re.I)
FALLBACK_DATE_RE = re.compile(
    r"(?:invoice|inv|bill|issue)?\s*dated?\s*[:#-]?\s*(\d{1,2}[-/\s]+(?:[A-Za-z]{3,9}|\d{1,2})[-/\s]+\d{2,4}|\d{1,2}[\r\n\s]*(?:st|nd|rd|th)?[\r\n\s]+[A-Za-z]{3,9},?[\r\n\s]+\d{2,4})",
    re.I,
)
DATE_NORM_VALID_RE = re.compile(r"(19|20)\d{2}-\d{2}-\d{2}")
DUE_DATE_LABEL = re.compile(r"\bdue\s*date\b", re.I)
POS_LABEL = re.compile(r"\bplace\s+of\s+supply\b", re.I)

RATE_PCT_STRIP_RE = re.compile(r'(?i)\(?\s*-?\d+(?:\.\d+)?\s*%\s*\)?|@\s*\d+(?:\.\d+)?\s*%?')
CGST_WORD_RE = re.compile(r'\bcgst\d*\b', re.I)
SGST_WORD_RE = re.compile(r'\b(?:sgst|utgst)\d*\b', re.I)
IGST_WORD_RE = re.compile(r'\bigst\d*\b', re.I)
SUBTOTAL_WORD_RE = re.compile(r'\b(?:sub\s*total|taxable\s*amount)\b', re.I)
GRAND_TOTAL_WORD_RE = re.compile(r'\b(?:grand\s*total|invoice\s*total|balance\s*due)\b', re.I)
GSTIN_WORD_RE = re.compile(r'\bgstin\b', re.I)
DECIMAL_AMOUNT_RE = re.compile(r'[\d,]+\.\d{2}')

SUBTOTAL_ROW_RE = re.compile(r"\b(?:sub\s*total|taxable\s*(?:amount|value))\b", re.I)
BASE_AMOUNT_ROW_RE = re.compile(r"\b(?:base\s*amount|rental\s*charges)\b", re.I)
TAX_ROW_RES = {
    "cgst": re.compile(r"\bcgst\d*\b", re.I),
    "sgst": re.compile(r"\b(?:sgst|utgst)\d*\b", re.I),
    "igst": re.compile(r"\bigst\d*\b", re.I),
}
COMBINED_GST_ROW_RE = re.compile(r"\b(?:total\s+tax|gst\s+amount|tax\s+amount|gst)\b", re.I)

CUSTOMER_GST_LABEL_RE = re.compile(r'\b(?:customer\s*gst|buyer\s*gst|client\s*gst)\b', re.I)
VENDOR_GST_LABEL_RE = re.compile(r'\b(?:vendor\s*gst|supplier\s*gst|seller\s*gst|our\s*gst)\b', re.I)
NEARBY_CUSTOMER_GST_RE = re.compile(r'\b(?:customer\s*gst(?:in)?|buyer\s*gst(?:in)?|client\s*gst(?:in)?)\b', re.I)
NEARBY_VENDOR_GST_RE = re.compile(r'\b(?:company\s*id|seller|vendor|our\s*gstin|supplier)\b', re.I)
SINGLE_GSTIN_BUYER_RE = re.compile(r'\b(?:customer\s*gst(?:in)?|buyer\s*gst(?:in)?|client\s*gst(?:in)?|bill(?:ed)?\s*to\s*gst(?:in)?)\b', re.I)

HEADER_LINE_ITEM_RE = re.compile(r"\b(?:item\s*&\s*description|particulars|description|product\s*or\s*service|activity|services?)\b", re.I)
STOP_LINE_ITEMS_RE = re.compile(
    r"\b(?:sub\s*total|subtotal|total\s*(?:in\s*words|amount|payable)?|grand\s*total|net\s*amount|"
    r"rupees|terms\s*&|bank|balance\s*due|thank\s*you|cgst\d*|sgst\d*|igst\d*|round\s*off|place\s+of\s+supply)\b"
    r"|^\s*total\b",
    re.I,
)
PAREN_SAC_RE = re.compile(r"\((?:SAC|HSN)\s*[:\-]?\s*(\d{4,8})\)", re.I)
WORD_SAC_RE = re.compile(r"\b(?:sac|hsn)\s*[:.\-]?\s*(\d{4,8})\b", re.I)
CLEAN_UNITS_RE = re.compile(r"(?i)\b(?:nos?|pcs?|hrs?|units?|days?|months?|inr|rs\.?)\b")
REAL_WORDS_RE = re.compile(r"\b[A-Za-z]{3,}\b")
NUMS_FIND_RE = re.compile(r"\b\d[\d,]*(?:\.\d{1,2})?\b")
ENDS_WITH_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d{1,2})?\s*$")
DESC_LEAD_NUM_RE = re.compile(r"^\d+\s+")
CURRENCY_STRIP_RE = re.compile(r"\s*(?:rs\.?|inr|₹)\s*$", re.I)
DESC_TRAILING_AMOUNTS_RE = re.compile(r"(?:(?:\s*(?:rs\.?|inr|₹)\s*)?[\d,]+(?:\.\d{1,2})?\s*(?:rs\.?|inr|₹)?)+$", re.I)
DESC_TAX_WORD_RE = re.compile(r"\b(?:cgst\d*|sgst\d*|igst\d*|tax)\b", re.I)

COL_CGST_RE = re.compile(r"\b(?:cgst|c\.g\.s\.t)\d*\b", re.I)
COL_SGST_RE = re.compile(r"\b(?:sgst|s\.g\.s\.t|utgst)\d*\b", re.I)
COL_IGST_RE = re.compile(r"\b(?:igst|i\.g\.s\.t)\d*\b", re.I)
COL_HEADER_CHECK_RE = re.compile(r"\b(?:amt|amount|rate|qty)\b", re.I)

STACKED_PCT_RE = re.compile(r"\(?\s*-?\d+(?:\.\d+)?\s*%\s*\)?|@\s*\d+(?:\.\d+)?\s*%?")
STACKED_LINE_MATCH_RE = re.compile(r"\b(?:sub\s*total|taxable\s*(?:amount|value)|cgst\d*|sgst\d*|igst\d*|gst)\b", re.I)
DIGIT_RE = re.compile(r"\d")
SUBTOTAL_STACK_RE = re.compile(r"\b(?:sub\s*total|taxable\s*(?:amount|value))\b", re.I)
CGST_STACK_RE = re.compile(r"\bcgst\d*\b|central\s*(?:tax|gst)", re.I)
SGST_STACK_RE = re.compile(r"\b(?:sgst|utgst)\d*\b|state\s*(?:tax|gst)", re.I)
IGST_STACK_RE = re.compile(r"\bigst\d*\b|integrated\s*(?:tax|gst)", re.I)
GST_STACK_RE = re.compile(r"\b(?:gst|tax)\b", re.I)
TOTAL_STACK_RE = re.compile(r"\b(?:grand\s*total|total\s*payable|net\s*amount|total)\b", re.I)


def _rows(text):
    """Text/markdown -> list of rows, each a list of cell strings."""
    rows = []
    for line in text.splitlines():
        if not line.strip() or SEP_ROW.match(line):
            continue
        if "|" in line:
            cells = [clean(c) for c in line.strip().strip("|").split("|")]
        elif re.search(r"[ \t]{2,}", line):
            cells = [clean(c) for c in re.split(r"[ \t]{2,}", line.strip()) if c.strip()]
        else:
            cells = [clean(line)]
        rows.append(cells)
    return rows


def _amount(cell):
    if not cell:
        return None
    c = clean(cell)
    # Reject dates, IDs, and financial year codes
    if re.search(r"\b\d{1,2}[-/\s.]+(?:[A-Za-z]{3,}|\d{1,2})[-/\s.]+\d{2,4}\b", c):
        return None
    if re.search(r"\b\d{2,4}\s*[-/]\s*\d{2,4}\b", c):
        return None
    if re.search(r"[A-Za-z0-9]+/[A-Za-z0-9]+", c):
        return None
    # Reject GSTINs, PANs, IFSCs, bank account numbers, phone numbers
    if GSTIN_PATTERN.search(c.upper()) or re.search(r"\b[A-Z]{5}\d{4}[A-Z]\b", c.upper()):
        return None
    if re.search(r"\b(?:ifsc|micr|a/c|account|bank|gstin|gst\s*no|stin)\b", c, re.I):
        return None
    # An address / sentence or line item description is not an amount
    if re.match(r"^\d+\s+[A-Za-z]", c):
        return None
    if len(re.findall(r"[A-Za-z]{2,}", c)) >= 2 and not re.search(r"\d[\d,]*\.\d{1,2}\b", c):
        return None
    # Strip tax labels with concatenated rates e.g. CGST9, SGST9, IGST18
    c = re.sub(r"\b(?:cgst|sgst|igst|gst|tax|cst|sst)\s*\d+\b", " ", c, flags=re.I)
    # Strip percentage e.g. (9%), 9%, 18%, -09 %
    c = re.sub(r"\(?\s*-?\d+(?:\.\d+)?\s*%\s*\)?", " ", c)
    # Normalize typo multiple dots e.g. 467..28 -> 467.28
    c = re.sub(r"\.{2,}", ".", c)
    nums = AMOUNT_RE.findall(c)
    if not nums:
        return None
    decimals = [n for n in nums if "." in n]
    res = normalize_number(decimals[-1]) if decimals else normalize_number(nums[-1])
    if res in (2024, 2025, 2026, 2027, 2028):
        return None
    if isinstance(res, (int, float)) and int(res) == res and (re.fullmatch(r"99\d{4}", str(int(res))) or len(str(int(res))) == 8):
        return None
    return res


def _candidates(rows, label_re, kind, column_lookup=False, skip=("due",), below=True):
    """Yield every value found for a label: same cell -> later cells -> column below -> next line."""
    for ri, cells in enumerate(rows):
        for ci, cell in enumerate(cells):
            low = cell.lower()
            m = label_re.search(cell)
            if not m or any(w in low for w in skip):
                continue
            rem = cell[m.end():].strip()
            # If cell is in a table header row (e.g. contains 'description', 'sl no', or adjacent rows are column headers)
            # and there is no same-cell amount, do not walk downwards into table line items
            if kind == "amount":
                if re.search(r"\b(?:sl\s*no|description|particulars|product)\b", cell, re.I):
                    continue
                if ri + 1 < len(rows) and re.search(r"^\s*(?:amount|rate|qty|quantity|description|particulars|item)\b", rows[ri + 1][0], re.I):
                    if not _pick(rem, kind):
                        continue
                if ri > 0 and re.search(r"^\s*(?:rate|qty|quantity|description|particulars|item)\b", rows[ri - 1][0], re.I):
                    if not _pick(rem, kind):
                        continue
                if rem in ("-", "--", "nil", "n/a", "na", "0", "0.00"):
                    continue
            # If the remainder in this cell is another label (e.g. Sub Total CGST9 (9%)), skip it
            if kind == "amount" and re.search(r"\b(?:cgst|sgst|igst|tax|total|subtotal|gst)\b", rem, re.I):
                pass
            else:
                v = _pick(rem, kind)
                if v is not None:
                    yield v
                    continue
            got = False
            for nxt in cells[ci + 1:]:
                if kind == "amount" and "%" in nxt and not AMOUNT_RE.search(PERCENT.sub("", nxt)):
                    continue
                v = _pick(nxt, kind)
                if v is not None:
                    yield v; got = True
                    break
            if got:
                continue
            # Look at rows below: skip empty rows or rows with only currency symbols / colons
            if not below:
                continue
            for r_below in range(ri + 1, min(ri + 6, len(rows))):
                below = rows[r_below]
                if not below or not any(below):
                    continue
                first_tok = clean(below[0]).strip(" :₹$-")
                if not first_tok and len(below) == 1:
                    continue
                if kind == "amount" and re.search(r"\b(?:total|taxable|subtotal|sub\s*total|grand\s*total|cgst|sgst|igst|gst|charges|in\s*words|amount|rate|qty)\b", below[0], re.I) and not label_re.search(below[0]):
                    break
                target = below[ci] if ci < len(below) and below[ci] else below[0]
                if kind in ("id", "date") and ID_LABEL_ROW_JUNK.search(" ".join(below)):
                    break                      # that row is PAN / GSTIN / bank data, not this label's value
                if kind == "amount":
                    clean_target = clean(target)
                    if clean_target == "%" or re.fullmatch(r"\d+(?:\.\d+)?%", clean_target):
                        continue
                    nxt_cell = clean(below[ci + 1]) if ci + 1 < len(below) else ""
                    nxt_row_first = clean(rows[r_below + 1][0]) if r_below + 1 < len(rows) and rows[r_below + 1] else ""
                    if re.fullmatch(r"\d+(?:\.\d+)?", clean_target) and (nxt_cell.startswith("%") or nxt_row_first == "%" or float(clean_target) in (2.5, 5.0, 6.0, 9.0, 12.0, 14.0, 18.0, 28.0)):
                        continue
                    if clean_target.lower() in ("nos.", "nos", "qty", "units", "unit", "pcs", "pcs."):
                        continue
                    if re.fullmatch(r"99\d{4}", clean_target) or (len(clean_target) == 8 and clean_target.isdigit()):
                        continue
                v = _pick(target, kind)
                if v is not None:
                    yield v; got = True
                    break


STOP_IDS = {"invoice", "date", "due", "bill", "terms", "tax", "total", "gst", "gstin", "order", "receipt", "quotation", "proforma", "irn", "cin", "pan", "document"}


PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ID_LABEL_ROW_JUNK = re.compile(r"\b(?:pan|gstin|gst\s*no|cin|ifsc|a/c|account|micr|phone|mobile|tel|cell|fax|pin\s*code|hsn|sac|bill(?:ed)?\s*to|buyer|customer|consignee|ship(?:ped)?\s*to)\b", re.I)


def is_non_invoice_id(tok):
    """PAN / GSTIN / IFSC / phone / bank-account / date-like / IRN tokens are never an invoice number."""
    t = clean(tok).upper().replace(" ", "")
    if not t:
        return True
    if len(t) > 30 or re.fullmatch(r"[0-9A-F]{30,64}", t):
        return True
    if re.fullmatch(r"(?:19|20)\d{2}", clean(tok)):
        return True
    low = clean(tok).lower()
    if any(m in low for m in ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")):
        return True
    if PAN_RE.fullmatch(t) or IFSC_RE.fullmatch(t) or GSTIN_PATTERN.search(t):
        return True
    if re.fullmatch(r"\+?\d{10,18}", t):          # phone / account / Aadhaar
        return True
    if re.match(r"^\d+(?:st|nd|rd|th)(?:[A-Za-z]+)?$", clean(tok), re.I):  # floor / stage / date ordinals
        return True
    if DATE_RE.fullmatch(clean(tok)):
        return True
    if clean(tok).lower() in ("irn", "ack", "ack no", "ack date", "e-invoice", "einvoice", "qr", "urn"):
        return True
    return False


def _id_score(tok):
    if not tok or tok.lower() in STOP_IDS or not any(c.isdigit() for c in tok) or is_non_invoice_id(tok):
        return -1
    return 2 if re.search(r"[A-Za-z/\-]", tok) else (1 if len(tok) <= 10 else 0)


def _find(rows, label_re, kind, column_lookup=False, skip=("due",), below=True):
    cands = list(_candidates(rows, label_re, kind, column_lookup, skip, below))
    if not cands:
        return None
    if kind == "id":
        valid_ids = [c for c in cands if _id_score(c) >= 0]
        return max(valid_ids, key=_id_score) if valid_ids else None
    return cands[0]


def _pick(text, kind):
    if not text:
        return None
    if kind == "date":
        for m in DATE_RE.finditer(text):
            d = normalize_date(m.group(0))
            if re.fullmatch(r"(19|20)\d{2}-\d{2}-\d{2}", d or ""):
                return d
        return None
    if kind == "text":
        t = clean(text).strip(" :-|")
        return t if 0 < len(t) < 60 else None
    if kind == "id":
        clean_text = clean(text).strip(" :-|#")
        clean_text = re.sub(r"(?i)\s*(?:show|hide|copy|print|original|duplicate|triplicate)$", "", clean_text).strip()
        # Check if the whole string after label is a valid invoice id with spaces (e.g. Co/Sep 2026/24)
        m_full = re.match(r"^([A-Za-z0-9][A-Za-z0-9/_\- ]{1,35}[A-Za-z0-9])$", clean_text)
        if m_full:
            tok = m_full.group(1).strip()
            tok = re.sub(r"(?i)\s*(?:show|hide|copy|print|original|duplicate|triplicate)$", "", tok).strip()
            if any(c.isdigit() for c in tok) and not DATE_RE.fullmatch(tok) and tok.lower() not in STOP_IDS and not is_non_invoice_id(tok):
                return tok
        for m in ID_RE.finditer(text):
            tok = m.group(0).strip(".-/_")
            tok = re.sub(r"(?i)\s*(?:show|hide|copy|print|original|duplicate|triplicate)$", "", tok).strip()
            if any(c.isdigit() for c in tok) and not DATE_RE.fullmatch(tok) and tok.lower() not in STOP_IDS and not is_non_invoice_id(tok):
                return tok
        return None
    return _amount(text)


def extract_table_column_taxes(extracted):
    """Extract CGST/SGST/IGST and taxable amounts from table columns."""
    out = {}
    for table in extracted.get("tables", []):
        rows = table.get("rows", []) if isinstance(table, dict) else table
        if len(rows) < 2:
            continue
        col_types = {}
        combined_headers = []
        num_cols = max(len(r) for r in rows[:2])
        for c_idx in range(num_cols):
            h0 = clean(rows[0][c_idx]).lower() if c_idx < len(rows[0]) else ""
            h1 = clean(rows[1][c_idx]).lower() if len(rows) > 1 and c_idx < len(rows[1]) else ""
            combined_headers.append(f"{h0} {h1}".strip())

        for ci, norm in enumerate(combined_headers):
            if "%" in norm or "rate" in norm:
                continue
            if COL_CGST_RE.search(norm):
                col_types["cgst"] = ci
            elif COL_SGST_RE.search(norm):
                col_types["sgst"] = ci
            elif COL_IGST_RE.search(norm):
                col_types["igst"] = ci
            elif re.search(r"\b(?:gst|total\s+tax|tax\s+amount)\b", norm) and not re.search(r"\b(?:cgst|sgst|igst|gstin)\b", norm):
                col_types["gst_total"] = ci
            elif norm in ("amount", "line total", "amt") and "taxable_amount" not in col_types:
                col_types["taxable_amount"] = ci

        data_start_idx = 1
        if len(rows) > 2 and any(COL_HEADER_CHECK_RE.search(clean(c)) for c in rows[1]):
            data_start_idx = 2

        if col_types:
            for field, ci in col_types.items():
                total_val = 0.0
                found_any = False
                for r in rows[data_start_idx:]:
                    if ci < len(r) and r[ci]:
                        r_label = clean(r[0]).lower() if r and r[0] else ""
                        if any(re.search(rf"\b{term}\b", r_label) for term in ("total", "sub total", "subtotal", "cgst", "sgst", "igst", "tax", "round off", "balance")):
                            continue
                        val = normalize_number(r[ci])
                        if val is not None and not str(r[ci]).endswith("%"):
                            total_val += val
                            found_any = True
                if found_any and total_val > 0:
                    out[field] = round(total_val, 2)
    return out


def extract_stacked_summary(text):
    """Extract summary totals when labels and amounts are stacked in parallel columns."""
    res = {}
    lines = [clean(l) for l in text.splitlines() if clean(l)]
    for i, line in enumerate(lines):
        norm = line.lower()
        norm_no_pct = STACKED_PCT_RE.sub("", norm).strip()
        if STACKED_LINE_MATCH_RE.search(norm_no_pct) and not DIGIT_RE.search(norm_no_pct):
            seq = []
            for j in range(i, min(i + 8, len(lines))):
                l_j = STACKED_PCT_RE.sub("", lines[j].lower()).strip()
                if SUBTOTAL_STACK_RE.search(l_j) and not any(k == "taxable_amount" for k, _ in seq):
                    seq.append(("taxable_amount", j))
                elif CGST_STACK_RE.search(l_j) and not any(k == "cgst" for k, _ in seq):
                    seq.append(("cgst", j))
                elif SGST_STACK_RE.search(l_j) and not any(k == "sgst" for k, _ in seq):
                    seq.append(("sgst", j))
                elif IGST_STACK_RE.search(l_j) and not any(k == "igst" for k, _ in seq):
                    seq.append(("igst", j))
                elif GST_STACK_RE.search(l_j) and not any(k in ("gst_total", "cgst", "sgst", "igst") for k, _ in seq):
                    seq.append(("gst_total", j))
                elif TOTAL_STACK_RE.search(l_j) and not DIGIT_RE.search(l_j) and not any(k == "total" for k, _ in seq):
                    seq.append(("total", j))
                    break
            has_taxes = any(k in ("cgst", "sgst", "igst") for k, _ in seq)
            has_totals = any(k in ("taxable_amount", "total") for k, _ in seq)
            if (len(seq) >= 2 and (has_totals or has_taxes)) or (len(seq) >= 1 and has_taxes):
                # If amounts are interleaved between labels, this is an adjacent label-value sequence, not a detached stacked block
                interleaved_amounts = 0
                label_indices = [idx for _, idx in seq]
                for j in range(min(label_indices), max(label_indices) + 1):
                    if j not in label_indices and _amount(lines[j]) is not None:
                        interleaved_amounts += 1
                if interleaved_amounts >= len(seq) - 1:
                    continue

                last_label_idx = max(idx for _, idx in seq)
                amounts = []
                for k in range(last_label_idx + 1, min(last_label_idx + 30, len(lines))):
                    amt = _amount(lines[k])
                    if amt is not None and not lines[k].endswith("%") and amt not in (2024, 2025, 2026, 2027):
                        amounts.append(amt)

                # Solve via arithmetic invariant: taxable_amount + taxes == total
                for tot in amounts:
                    if tot < 10.0:
                        continue
                    for base in amounts:
                        if base >= tot or base < 10.0:
                            continue
                        for cgst in amounts:
                            if cgst >= tot or cgst >= base:
                                continue
                            for sgst in amounts:
                                if sgst >= tot or sgst >= base:
                                    continue
                                diff = abs((base + cgst + sgst) - tot)
                                if diff <= 1.05 and (diff / tot) <= 0.02:
                                    rate = (cgst + sgst) / base
                                    if 0.02 <= rate <= 0.35:
                                        if any(k == "cgst" for k, _ in seq) and any(k == "sgst" for k, _ in seq):
                                            return {"taxable_amount": base, "cgst": cgst, "sgst": sgst, "total": tot}
                        for igst in amounts:
                            if igst >= tot or igst >= base:
                                continue
                            diff = abs((base + igst) - tot)
                            if diff <= 1.05 and (diff / tot) <= 0.02:
                                rate = igst / base
                                if 0.02 <= rate <= 0.35:
                                    if any(k == "igst" for k, _ in seq):
                                        return {"taxable_amount": base, "igst": igst, "total": tot}
                        for gst in amounts:
                            if gst >= tot or gst >= base:
                                continue
                            diff = abs((base + gst) - tot)
                            if diff <= 1.05 and (diff / tot) <= 0.02:
                                rate = gst / base
                                if 0.02 <= rate <= 0.35:
                                    if any(k == "gst_total" for k, _ in seq):
                                        return {"taxable_amount": base, "gst_total": gst, "total": tot}

                # Check if base is elsewhere in text (e.g. from subtotal / before tax 1,200.00)
                subtotal_candidates = []
                for m_sub in re.finditer(r"(?i)\b(?:sub\s*total|taxable\s*(?:amount|value)|before\s*tax)\b[^\d]*?([\d,]+(?:\.\d{2})?)", text):
                    try:
                        subtotal_candidates.append(float(m_sub.group(1).replace(",", "")))
                    except ValueError:
                        pass
                for base in subtotal_candidates:
                    if base <= 0:
                        continue
                    for tot in amounts:
                        if tot <= 0 or base >= tot:
                            continue
                        for cgst in amounts:
                            for sgst in amounts:
                                diff = abs((base + cgst + sgst) - tot)
                                if diff <= 1.05 and (diff / tot) <= 0.02 and 0.02 <= ((cgst + sgst) / base) <= 0.35:
                                    if any(k == "cgst" for k, _ in seq) and any(k == "sgst" for k, _ in seq):
                                        return {"taxable_amount": base, "cgst": cgst, "sgst": sgst, "total": tot}
                        for igst in amounts:
                            diff = abs((base + igst) - tot)
                            if diff <= 1.05 and (diff / tot) <= 0.02 and 0.02 <= (igst / base) <= 0.35:
                                if any(k == "igst" for k, _ in seq):
                                    return {"taxable_amount": base, "igst": igst, "total": tot}
                        for gst in amounts:
                            diff = abs((base + gst) - tot)
                            if diff <= 1.05 and (diff / tot) <= 0.02 and 0.02 <= (gst / base) <= 0.35:
                                if any(k == "gst_total" for k, _ in seq):
                                    return {"taxable_amount": base, "gst_total": gst, "total": tot}

                if len(amounts) >= len(seq):
                    tot = amounts[-1]
                    for idx in range(len(amounts) - len(seq) + 1):
                        cand_amts = amounts[idx: idx + len(seq)]
                        cand = {k: a for (k, _), a in zip(seq, cand_amts)}
                        if "total" in cand:
                            cand["total"] = tot
                        t_sum = sum(cand.get(t, 0) for t in ("cgst", "sgst", "igst", "gst_total"))
                        base = cand.get("taxable_amount", 0)
                        if base and abs(tot - (base + t_sum)) <= 1.5:
                            return cand
    return res


def regex_extract(text):
    out = {"invoice": {}, "operator": {}, "gofloaters": {}, "tax": {}}
    rows = _rows(text)

    # 1. Invoice Number
    v = _find(rows, INV_NO_LABEL, "id", column_lookup=True, skip=("due", "date", "dated"))
    if v and _id_score(v) > 0 and v.lower() not in ("description", "item", "qty", "amount"):
        m_inv = re.search(r"\b(INV[-/][A-Za-z0-9/_\-.]*?" + re.escape(v) + r")\b", text, re.I)
        out["invoice"]["number"] = m_inv.group(1).strip(".-/_:") if m_inv else v
    if not out["invoice"].get("number"):
        for p in INV_PATS:
            for m in p.finditer(text):
                cand = m.group(1).strip(".-/_:")
                m_inv = re.search(r"\b(INV[-/][A-Za-z0-9/_\-.]*?" + re.escape(cand) + r")\b", text, re.I)
                if m_inv and len(m_inv.group(1)) > len(cand):
                    cand = m_inv.group(1).strip(".-/_:")
                if _id_score(cand) > 0 and cand.lower() not in ("description", "item", "qty", "amount"):
                    out["invoice"]["number"] = cand
                    break
            if out["invoice"].get("number"):
                break
    if not out["invoice"].get("number"):
        # Standalone prominent invoice ID immediately above Issue Date / Invoice Date
        m_pre_date = PRE_DATE_RE.search(text)
        if m_pre_date:
            cand = m_pre_date.group(1).strip()
            if _id_score(cand) > 0 and not is_non_invoice_id(cand) and cand.lower() not in ("description", "item", "qty", "amount"):
                out["invoice"]["number"] = cand
    if not out["invoice"].get("number"):
        m = UNLABELED_NO.search(text)
        if m and _id_score(m.group(1)) > 0:
            out["invoice"]["number"] = m.group(1)

    # 2. Invoice Date
    v = _find(rows, INV_DATE_LABEL, "date", column_lookup=True,
              skip=("due", "ack", "delivery", "order", "ship", "service", "expiry", "valid", "period"))
    if v:
        out["invoice"]["date"] = v
    if not out["invoice"].get("date"):
        m_date = FALLBACK_DATE_RE.search(text)
        if m_date:
            d_norm = normalize_date(m_date.group(1))
            if DATE_NORM_VALID_RE.fullmatch(d_norm or ""):
                out["invoice"]["date"] = d_norm
    if not out["invoice"].get("date"):
        m_month = re.search(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b", text, re.I)
        if m_month:
            d_norm = normalize_date(m_month.group(0))
            if DATE_NORM_VALID_RE.fullmatch(d_norm or ""):
                out["invoice"]["date"] = d_norm

    v = _find(rows, DUE_DATE_LABEL, "date", skip=())
    if v:
        out["invoice"]["due_date"] = v
    v = _find(rows, POS_LABEL, "text", skip=("ship", "bill", "consignee", "buyer", "customer"))
    if not v or not state_from_text(v):
        m_pos = re.search(r"(?i)\bplace\s*of\s*supply\b[\s\S]{0,100}?[:\-]\s*([A-Za-z\s]+(?:\s*\(\d{1,2}\))?)", text)
        if m_pos:
            cand_pos = m_pos.group(1).strip()
            if state_from_text(cand_pos):
                v = cand_pos
    if v and state_from_text(v):
        out["invoice"]["place_of_supply"] = v

    # 3. Taxes: Same-line extraction with rates stripped (e.g. CGST (9%) 1,152.00 or CGST -09 % 43.00)
    for l in text.splitlines():
        cleaned = RATE_PCT_STRIP_RE.sub(' ', l)
        if CGST_WORD_RE.search(cleaned) and not GSTIN_WORD_RE.search(cleaned):
            m = DECIMAL_AMOUNT_RE.findall(cleaned)
            val = float(m[-1].replace(',', '')) if m else _amount(cleaned)
            if val is not None and out["tax"].get("cgst") is None:
                out["tax"]["cgst"] = val
        if SGST_WORD_RE.search(cleaned):
            m = DECIMAL_AMOUNT_RE.findall(cleaned)
            val = float(m[-1].replace(',', '')) if m else _amount(cleaned)
            if val is not None and out["tax"].get("sgst") is None:
                out["tax"]["sgst"] = val
        if IGST_WORD_RE.search(cleaned):
            m = DECIMAL_AMOUNT_RE.findall(cleaned)
            val = float(m[-1].replace(',', '')) if m else _amount(cleaned)
            if val is not None and out["tax"].get("igst") is None:
                out["tax"]["igst"] = val
        if re.search(r'\b(?:gst|tax)\s*@?\s*\d+(?:\.\d+)?%\b', cleaned, re.I) and not re.search(r'\b(?:cgst|sgst|igst|gstin)\b', cleaned, re.I):
            m = DECIMAL_AMOUNT_RE.findall(cleaned)
            val = float(m[-1].replace(',', '')) if m else _amount(cleaned)
            if val is not None and val > 1 and out["tax"].get("gst_total") is None:
                out["tax"]["gst_total"] = val
        if SUBTOTAL_WORD_RE.search(cleaned):
            m = DECIMAL_AMOUNT_RE.findall(cleaned)
            valid_m = [x for x in m if not re.search(r'202[4-7]', x)]
            if valid_m and out["tax"].get("taxable_amount") is None:
                if len(valid_m) >= 2:
                    out["tax"]["taxable_amount"] = float(valid_m[0].replace(',', ''))
                    if out["tax"].get("total") is None:
                        out["tax"]["total"] = float(valid_m[-1].replace(',', ''))
                else:
                    out["tax"]["taxable_amount"] = float(valid_m[-1].replace(',', ''))
        if GRAND_TOTAL_WORD_RE.search(cleaned):
            m = DECIMAL_AMOUNT_RE.findall(cleaned)
            if m and not re.search(r'202[4-7]', m[-1]) and out["tax"].get("total") is None:
                out["tax"]["total"] = float(m[-1].replace(',', ''))

    # Check for multi-tax GST breakdown summary rows (e.g., 2,400.00 9% 216.00 9% 216.00 432.00)
    for l in text.splitlines():
        m_gst_row = re.search(r"([\d,]+(?:\.\d{2})?)\s+\d+(?:\.\d+)?%\s+([\d,]+(?:\.\d{2})?)\s+\d+(?:\.\d+)?%\s+([\d,]+(?:\.\d{2})?)\s+([\d,]+(?:\.\d{2})?)", l)
        if m_gst_row:
            try:
                base_val = float(m_gst_row.group(1).replace(",", ""))
                cgst_val = float(m_gst_row.group(2).replace(",", ""))
                sgst_val = float(m_gst_row.group(3).replace(",", ""))
                tot_tax_val = float(m_gst_row.group(4).replace(",", ""))
                if abs((cgst_val + sgst_val) - tot_tax_val) <= 0.05 and cgst_val > 0:
                    if out["tax"].get("taxable_amount") is None:
                        out["tax"]["taxable_amount"] = base_val
                    if out["tax"].get("cgst") is None:
                        out["tax"]["cgst"] = cgst_val
                    if out["tax"].get("sgst") is None:
                        out["tax"]["sgst"] = sgst_val
                    break
            except (ValueError, TypeError):
                pass
        # Check for 3-amount pattern: base cgst sgst (e.g. 7,200.00 648.00 648.00)
        m_3amts = re.search(r"\b([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\b", l)
        if m_3amts and re.search(r"(?i)\b(?:cgst|sgst)\b", l):
            try:
                a_val = float(m_3amts.group(1).replace(",", ""))
                b_val = float(m_3amts.group(2).replace(",", ""))
                c_val = float(m_3amts.group(3).replace(",", ""))
                if a_val > 0 and abs(b_val - c_val) <= 0.05 and 0.01 <= (b_val / a_val) <= 0.15:
                    if out["tax"].get("taxable_amount") is None:
                        out["tax"]["taxable_amount"] = a_val
                    if out["tax"].get("cgst") is None:
                        out["tax"]["cgst"] = b_val
                    if out["tax"].get("sgst") is None:
                        out["tax"]["sgst"] = c_val
                    break
            except (ValueError, TypeError):
                pass

    v = _find(rows, SUBTOTAL_ROW_RE, "amount", skip=())
    if v is None:   # loose labels double as line-item names: only trust a value on the same row
        v = _find(rows, BASE_AMOUNT_ROW_RE, "amount", skip=(), below=False)
    if v is not None and v not in (2024, 2025, 2026, 2027) and out["tax"].get("taxable_amount") is None:
        out["tax"]["taxable_amount"] = v

    for tax in ("cgst", "sgst", "igst"):
        if out["tax"].get(tax) is None:
            v = _find(rows, TAX_ROW_RES[tax], "amount", skip=())
            if v is not None and v > 0:
                out["tax"][tax] = v

    if all(out["tax"].get(k) is None for k in ("cgst", "sgst", "igst")) and out["tax"].get("gst_total") is None:   # single combined GST / tax line
        v = _find(rows, COMBINED_GST_ROW_RE, "amount",
                  skip=("gstin", "gst no", "gst number", "gst reg", "stin", "taxable", "sac", "hsn", "pan"))
        if v is not None and v > 1:
            out["tax"]["gst_total"] = v

    for label, pat in TOTAL_PRIORITY_RES:
        v = _find(rows, pat, "amount", skip=SKIP_TOTAL)
        if v is not None and v > 0 and v not in (2024, 2025, 2026, 2027) and out["tax"].get("total") is None:
            out["tax"]["total"] = v
            break

    # Stacked summary fallback
    stacked = extract_stacked_summary(text)
    if stacked:
        if "taxable_amount" in stacked:
            out["tax"]["taxable_amount"] = stacked["taxable_amount"]
        if "total" in stacked:
            out["tax"]["total"] = stacked["total"]
        for k in ("cgst", "sgst", "igst", "gst_total"):
            if k in stacked and out["tax"].get(k) is None:
                out["tax"][k] = stacked[k]

    # 4. GSTIN -> party
    cells = _cells(text)
    gstin_matches = []
    for i, c in enumerate(cells):
        c_up = c.upper()
        m = GSTIN_PATTERN.search(c_up)
        if m and m.group(0)[:2] in STATE_CODES:
            gstin_matches.append((m.group(0), i, c))
        else:
            lm = GSTIN_LABELED_PATTERN.search(c_up)
            if lm:
                val = lm.group(1).upper()
                if val[:2] in STATE_CODES and GSTIN_PATTERN.fullmatch(val):
                    gstin_matches.append((val, i, c))

    op_g = None
    gf_g = None
    # Pass 1: explicit labels on GSTIN
    for g, idx, cell in gstin_matches:
        cell_low = cell.lower()
        # Direct cell match takes highest priority
        if CUSTOMER_GST_LABEL_RE.search(cell_low):
            gf_g = g
            continue
        if VENDOR_GST_LABEL_RE.search(cell_low):
            op_g = g
            continue
        nearby_before = ' '.join(cells[max(0, idx-2): idx+1]).lower()
        if NEARBY_CUSTOMER_GST_RE.search(nearby_before):
            gf_g = g
        elif NEARBY_VENDOR_GST_RE.search(nearby_before):
            op_g = g
        elif "AAYCS6808H" in g:
            gf_g = g

    # Pass 2: distance to GoFloaters / SMBSure hints
    all_g = [g for g, _, _ in gstin_matches]
    if len(all_g) >= 2:
        if gf_g and not op_g:
            op_g = [g for g in all_g if g != gf_g][0]
        elif op_g and not gf_g:
            gf_g = [g for g in all_g if g != op_g][0]
        elif not op_g and not gf_g:
            hints = [i for i, c in enumerate(cells) if any(h in c.lower() for h in GOFLOATERS_HINTS)]
            def dist(k):
                before = [k - i for i in hints if i <= k and k - i <= 12]
                after = [i - k for i in hints if i > k and i - k <= 2]
                return (0, min(before)) if before else ((1, min(after)) if after else None)
            scored = sorted((d, k, g) for g, k, _ in gstin_matches if (d := dist(k)) is not None)
            if scored:
                gf_g = scored[0][2]
                others = [g for g in all_g if g != gf_g]
                if others: op_g = others[0]
            else:
                op_g = all_g[0]
                gf_g = all_g[1]
    elif len(all_g) == 1:
        single_g = all_g[0]
        nearby = ' '.join(cells[max(0, gstin_matches[0][1]-3): gstin_matches[0][1]+1]).lower()
        if "AAYCS6808H" in single_g or SINGLE_GSTIN_BUYER_RE.search(nearby):
            gf_g = single_g
            op_g = None
        else:
            op_g = single_g
            gf_g = None

    if op_g: out["operator"]["gstin"] = op_g
    if gf_g: out["gofloaters"]["gstin"] = gf_g
    return out


def _clean_value(section, key, value):
    if value in (None, "", "null"):
        return None
    if key == "gstin":
        cleaned_up = clean(value).upper()
        m = GSTIN_PATTERN.search(cleaned_up)
        if m:
            return m.group(0)
        lm = GSTIN_LABELED_PATTERN.search(cleaned_up)
        if lm:
            val = lm.group(1).upper()
            if GSTIN_PATTERN.fullmatch(val):
                return val
        return None          # reject hallucinated GSTINs
    if section == "tax":
        return normalize_number(value)
    if key in ("date", "due_date"):
        return normalize_date(value)
    return clean(value)


def missing_fields(doc):
    checks = [("invoice", "number"), ("invoice", "date"), ("operator", "gstin"),
              ("gofloaters", "gstin"), ("tax", "total")]
    miss = [f"{s}.{k}" for s, k in checks if not doc.get(s, {}).get(k)]
    t = doc.get("tax", {})
    if all(t.get(k) is None for k in ("cgst", "sgst", "igst")):
        miss.append("tax.cgst/sgst/igst")
    return miss


def merge_fill(doc, extra, source):
    """Fill only empty fields. Returns list of fields that were filled."""
    filled = []
    VALID_KEYS = {
        "invoice": {"number", "date", "due_date", "place_of_supply"},
        "operator": {"name", "address", "state", "gstin"},
        "gofloaters": {"name", "address", "state", "gstin"},
        "tax": {"taxable_amount", "cgst", "sgst", "igst", "total", "gst_total"},
    }
    for section, values in (extra or {}).items():
        if not isinstance(values, dict) or section not in doc:
            continue
        allowed = VALID_KEYS.get(section, set(doc[section].keys()))
        for key, value in values.items():
            if key not in allowed:
                continue
            value = _clean_value(section, key, value)
            if value is None or doc[section].get(key) not in (None, ""):
                continue
            doc[section][key] = value
            filled.append(f"{section}.{key}")
    for party in ("operator", "gofloaters"):
        p = doc.get(party, {})
        if not p.get("state"):
            p["state"] = state_from_gstin(p.get("gstin")) or state_from_text(p.get("address"))
    if filled:
        doc.setdefault("extraction_sources", {})[source] = filled
    return filled


PIN = re.compile(r"\b[1-8]\d{5}\b")
ADDR_LABELS = re.compile(r"\b(?:gstin|gst\s*no|bill(?:ed)?\s*to|customer\s*(?:name|details)?|address|name)\b\s*[:\-]?", re.I)


def arithmetic_match(doc, text):
    """
    GST-slab arithmetic is only used as EVIDENCE. It never fills cgst / sgst / igst: the tax type is
    populated only when CGST / SGST / IGST is explicitly labelled in the document.
    """
    tax = doc["tax"]
    base = tax.get("taxable_amount")
    if not base or any(tax.get(k) is not None for k in ("cgst", "sgst", "igst")):
        return
    nums = set()
    for n in AMOUNT_RE.findall(text):
        try:
            nums.add(round(float(n.replace(",", "")), 2))
        except ValueError:
            pass
    for rate in (18, 12, 5, 28):
        whole, half = round(base * rate / 100, 2), round(base * rate / 200, 2)
        total = round(base + whole, 2)
        if total in nums and (whole in nums or half in nums):
            if tax.get("total") is None:
                tax["total"] = total
                doc.setdefault("extraction_sources", {})["arithmetic_match"] = ["tax.total", f"gst_rate={rate}%"]
            doc.setdefault("evidence", {})["unlabelled_gst_amounts"] = {"rate": rate, "gst_amount": whole}
            return


def derive_fields(doc, text=""):
    """Arithmetic / rule-based completion. Only fills empty fields."""
    tax = doc["tax"]
    gst_total = tax.pop("gst_total", None)
    derived = []
    if gst_total is not None and all(tax.get(k) is None for k in ("cgst", "sgst", "igst")):
        # a single unlabelled GST amount: kept as evidence only, never split into CGST/SGST/IGST
        doc.setdefault("evidence", {})["unlabelled_gst_total"] = gst_total
    if tax.get("taxable_amount") is None:
        amounts = [i.get("amount") for i in doc.get("line_items", []) if i.get("amount") is not None]
        if amounts:
            tax["taxable_amount"] = round(sum(amounts), 2)
            derived.append("tax.taxable_amount(sum of line items)")
        else:
            cgst = tax.get("cgst")
            sgst = tax.get("sgst")
            igst = tax.get("igst")
            total = tax.get("total")
            candidate_base = None
            if cgst and cgst > 0:
                for r in (0.09, 0.14, 0.06, 0.025, 0.05, 0.12, 0.18, 0.28):
                    calc_base = round(cgst / r, 2)
                    if f"{calc_base:.2f}" in text or f"{int(calc_base)}" in text or f"{calc_base:,.2f}" in text:
                        candidate_base = calc_base
                        break
            elif igst and igst > 0:
                for r in (0.18, 0.12, 0.05, 0.28):
                    calc_base = round(igst / r, 2)
                    if f"{calc_base:.2f}" in text or f"{int(calc_base)}" in text or f"{calc_base:,.2f}" in text:
                        candidate_base = calc_base
                        break
            elif gst_total and gst_total > 0:
                for r in (0.18, 0.12, 0.05, 0.28):
                    calc_base = round(gst_total / r, 2)
                    if f"{calc_base:.2f}" in text or f"{int(calc_base)}" in text or f"{calc_base:,.2f}" in text:
                        candidate_base = calc_base
                        break

            if candidate_base is None and total and (cgst or sgst or igst or gst_total):
                sum_taxes = sum(t for t in (cgst, sgst, igst, gst_total) if t is not None)
                diff = round(total - sum_taxes, 2)
                for cand in (diff, round(diff), round(diff, 1)):
                    if f"{cand:.2f}" in text or f"{int(cand)}" in text:
                        candidate_base = cand
                        break

            if candidate_base is not None and candidate_base > 0:
                tax["taxable_amount"] = candidate_base
                derived.append("tax.taxable_amount(derived from tax and document text)")
    if tax.get("total") is None and tax.get("taxable_amount") is not None:
        parts = [tax.get(k) for k in ("cgst", "sgst", "igst") if tax.get(k) is not None]
        if parts:
            tax["total"] = round(tax["taxable_amount"] + sum(parts), 2)
            derived.append("tax.total")
    # Sanity check: taxable_amount and total swapped
    parts = sum([tax.get(k) for k in ("cgst", "sgst", "igst") if tax.get(k) is not None])
    if tax.get("taxable_amount") is not None and tax.get("total") is not None:
        if tax["taxable_amount"] > tax["total"] and tax["total"] > 0:
            if parts > 0 and abs(tax["total"] - parts) <= 0.05:
                # The value in total was actually the sum of taxes (e.g. 648 = 324 + 324), not grand total.
                # Do NOT swap: taxable_amount is the true base amount; compute the real grand total.
                tax["total"] = round(tax["taxable_amount"] + parts, 2)
                derived.append("total(calculated from taxable + taxes; previous total was tax sum)")
            elif parts > 0 and abs((tax["total"] + parts) - tax["taxable_amount"]) <= 0.5:
                # Genuine swap where total held base amount and taxable_amount held grand total
                tax["taxable_amount"], tax["total"] = tax["total"], tax["taxable_amount"]
                derived.append("swapped taxable_amount and total")
            elif parts == 0:
                tax["taxable_amount"], tax["total"] = tax["total"], tax["taxable_amount"]
                derived.append("swapped taxable_amount and total")

    # If total equaled taxable_amount (e.g. table line items subtotal was labeled 'TOTAL'), but taxes are present
    parts = sum([tax.get(k) for k in ("cgst", "sgst", "igst") if tax.get(k) is not None])
    if parts > 0 and tax.get("taxable_amount") is not None:
        expected_total = round(tax["taxable_amount"] + parts, 2)
        if tax.get("total") is None or abs(tax["taxable_amount"] - tax["total"]) < 0.05:
            tax["total"] = expected_total
            derived.append("total(calculated from taxable + taxes)")

    # If CGST is known and SGST is missing in intra-state, or vice versa
    if tax.get("cgst") is not None and tax.get("sgst") is None and tax.get("igst") is None:
        if tax.get("total") and tax.get("taxable_amount") and abs((tax["total"] - tax["taxable_amount"]) - (tax["cgst"] * 2)) <= 1.0:
            tax["sgst"] = tax["cgst"]
            derived.append("tax.sgst(matched CGST)")
    elif tax.get("sgst") is not None and tax.get("cgst") is None and tax.get("igst") is None:
        if tax.get("total") and tax.get("taxable_amount") and abs((tax["total"] - tax["taxable_amount"]) - (tax["sgst"] * 2)) <= 1.0:
            tax["cgst"] = tax["sgst"]
            derived.append("tax.cgst(matched SGST)")

    # If taxable_amount and total are both known with total > taxable_amount, but tax components are missing
    if tax.get("total") and tax.get("taxable_amount") and tax["total"] > tax["taxable_amount"]:
        if all(tax.get(k) is None for k in ("cgst", "sgst", "igst")) and doc.get("operator", {}).get("gstin"):
            if re.search(r"\b(?:cgst|sgst|igst)\b", text, re.I):
                tax_diff = round(tax["total"] - tax["taxable_amount"], 2)
                eff_rate = tax_diff / tax["taxable_amount"]
                if any(abs(eff_rate - r) <= 0.02 for r in (0.05, 0.12, 0.18, 0.28)):
                    op_st = doc.get("operator", {}).get("state")
                    gf_st = doc.get("invoice", {}).get("place_of_supply") or doc.get("gofloaters", {}).get("state")
                    if op_st and gf_st and op_st.lower() != gf_st.lower():
                        tax["igst"] = tax_diff
                        derived.append("tax.igst(derived from total - taxable interstate)")
                    elif op_st and gf_st and op_st.lower() == gf_st.lower():
                        half = round(tax_diff / 2, 2)
                        tax["cgst"] = half
                        tax["sgst"] = half
                        derived.append("tax.cgst_sgst(derived from total - taxable intrastate)")
                    elif re.search(r"\bigst\b", text, re.I):
                        tax["igst"] = tax_diff
                        derived.append("tax.igst(derived from total - taxable with text igst)")
                    elif re.search(r"\b(?:cgst|sgst)\b", text, re.I):
                        half = round(tax_diff / 2, 2)
                        tax["cgst"] = half
                        tax["sgst"] = half
                        derived.append("tax.cgst_sgst(derived from total - taxable with text cgst/sgst)")

    # No GST of any kind on the invoice (bill of supply / unregistered supplier): taxable value == total.
    if (tax.get("taxable_amount") is None and tax.get("total") is not None
            and all(tax.get(k) is None for k in ("cgst", "sgst", "igst"))
            and "unlabelled_gst_total" not in doc.get("evidence", {})
            and "unlabelled_gst_amounts" not in doc.get("evidence", {})):
        tax["taxable_amount"] = tax["total"]
        derived.append("tax.taxable_amount(= total, no GST charged)")
        doc.setdefault("evidence", {})["no_gst_charged"] = True

    if derived:
        doc.setdefault("extraction_sources", {})["derived"] = derived


LINE_ITEM_NOISE = re.compile(
    r"(?i)\b(?:dedicated\s+desk|hot\s+desk|meeting\s+room|conference\s+room|day\s+pass|bill\s+for\s+the\s+month(?:\s+of)?"
    r"(?:\s+[A-Za-z]{3,9}\.?\s+\d{4})?|utility\s+charges?|other\s+utility(?:\s+charges?)?|(?:rental|service|space|maintenance)\s+charges?"
    r"|\((?:beverages?|prin[a-z]*|printing|electricity|internet|parking)\)|booking\s+id\s*(?:is)?\s*[:#]?\s*\w+|security\s+deposit)"
)


def strip_line_item_text(address, line_items=None):
    """Remove billed-item wording (desk, utility charges ...) that a table walk dragged into an address."""
    if not address:
        return address
    a = address
    for item in line_items or []:
        d = clean((item or {}).get("description"))
        if len(d) > 6 and d.lower() in a.lower():
            a = re.sub(re.escape(d), " ", a, flags=re.I)
    a = LINE_ITEM_NOISE.sub(" ", a)
    a = re.sub(r"\s+", " ", a).strip(" ,;:-|")
    return a or None


HEADER_TOKENS = re.compile(
    r"^(?:#|item|description|particulars|product|service|hsn|sac|qty|quantity|units?|rate|price|unit\s*price|amount|taxable|cgst|sgst|igst|total"
    r"|%\s*amt|\b%\b|\s*|/|\b&\b)+$",
    re.I,
)
HEADER_WORDS = {
    "description", "particulars", "item", "product", "rate", "qty", "quantity",
    "amount", "total", "units", "unit", "hsn", "sac", "cgst", "sgst", "igst",
    "tax", "value", "inr", "price", "sl", "no", "rt", "disc", "per", "services", "service"
}


def extract_digital_line_items(text):
    """Extract line items from unstructured text streams when table parsing didn't produce items."""
    lines = [clean(l) for l in text.splitlines() if clean(l)]
    header_idx = None
    for i, l in enumerate(lines):
        norm = l.lower()
        if HEADER_LINE_ITEM_RE.search(norm):
            header_idx = i
            break

    if header_idx is None:
        return []

    items = []
    curr_desc = []
    curr_hsn = None
    for line in lines[header_idx + 1: min(header_idx + 35, len(lines))]:
        if STOP_LINE_ITEMS_RE.search(line):
            break
        words = set(re.findall(r"[a-zA-Z]+", line.lower()))
        if words and words.issubset(HEADER_WORDS):
            continue
        if HEADER_TOKENS.match(line):
            continue

        # Extract SAC/HSN embedded in parenthetical description, e.g., Meeting Room (SAC : 997212)
        m_paren_sac = PAREN_SAC_RE.search(line)
        if m_paren_sac:
            curr_hsn = m_paren_sac.group(1)
        else:
            m_hsn = WORD_SAC_RE.search(line)
            if m_hsn:
                curr_hsn = m_hsn.group(1)

        cleaned_words = CLEAN_UNITS_RE.sub("", line)
        has_real_words = bool(REAL_WORDS_RE.search(cleaned_words))
        nums = NUMS_FIND_RE.findall(line)

        if nums and not has_real_words:
            # Standalone numeric amounts row
            if len(nums) == 1 and "." not in nums[0] and (re.fullmatch(r"99\d{4}", nums[0]) or len(nums[0]) == 8):
                curr_hsn = nums[0]
                continue
            amt = normalize_number(nums[-1])
            if isinstance(amt, (int, float)) and int(amt) == amt and (re.fullmatch(r"99\d{4}", str(int(amt))) or len(str(int(amt))) == 8):
                if not curr_hsn:
                    curr_hsn = str(int(amt))
                amt = None
            qty = None
            rate = None
            if len(nums) >= 2:
                rate = normalize_number(nums[-2]) if ("." in nums[-2] or len(nums) >= 3) else None
                qty = normalize_number(nums[0]) if (nums[0] != nums[-1] or len(nums) >= 3) else None
            desc = " ".join(curr_desc).strip()
            desc = DESC_LEAD_NUM_RE.sub("", desc)
            if desc and amt:
                items.append({
                    "description": desc,
                    "hsn_sac": curr_hsn,
                    "quantity": qty,
                    "rate": rate,
                    "amount": amt,
                })
            elif not desc and items and amt:
                # If amount column was placed below Qty/Rate row (e.g. Qty Rate \n 6 250 \n Amount \n 1,500)
                prev = items[-1]
                if prev.get("quantity") and prev.get("amount") and abs(prev["quantity"] * prev["amount"] - amt) < 0.05:
                    prev["rate"] = prev["amount"]
                    prev["amount"] = amt
            curr_desc = []
            curr_hsn = None
        elif len(nums) >= 2 and ENDS_WITH_NUM_RE.search(line):
            # Check for row with tax percentage and amount columns:
            # e.g. 1 Day Pass 997212 1.00 340.00 9% 30.60 9% 30.60 340.00
            m_row_tax = re.search(r"(\d{4,8})\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(?:\d+%\s+[\d,]+(?:\.\d+)?\s+)*([\d,]+(?:\.\d+)?)$", line)
            if m_row_tax:
                hsn = m_row_tax.group(1)
                qty = normalize_number(m_row_tax.group(2))
                rate = normalize_number(m_row_tax.group(3))
                amt = normalize_number(m_row_tax.group(4))
                desc_part = line[: m_row_tax.start()].strip()
                desc = " ".join(curr_desc + [desc_part]).strip()
                desc = DESC_LEAD_NUM_RE.sub("", desc)
                if desc and amt:
                    items.append({
                        "description": desc,
                        "hsn_sac": hsn,
                        "quantity": qty,
                        "rate": rate,
                        "amount": amt,
                    })
                curr_desc = []
                curr_hsn = None
                continue

            # Combined description and amounts on same line
            if len(nums) == 1 and re.match(r"^\d+\s+[A-Za-z]", line) and not ENDS_WITH_NUM_RE.search(line) and "." not in nums[0]:
                curr_desc.append(DESC_LEAD_NUM_RE.sub("", line).strip())
                continue
            amt = normalize_number(nums[-1])
            if isinstance(amt, (int, float)) and int(amt) == amt and (re.fullmatch(r"99\d{4}", str(int(amt))) or len(str(int(amt))) == 8):
                if not curr_hsn:
                    curr_hsn = str(int(amt))
                amt = None
            qty = None
            rate = None
            hsn = curr_hsn or (nums[0] if len(nums[0]) == 6 and nums[0].startswith("99") else None)
            if len(nums) >= 3:
                rate = normalize_number(nums[-2]) if "." in nums[-2] else None
                qty = normalize_number(nums[1] if hsn == nums[0] else nums[0])
                if rate and amt and rate > 0 and abs(amt / rate - round(amt / rate)) < 0.01:
                    qty = int(round(amt / rate))
            desc_part = DESC_TRAILING_AMOUNTS_RE.sub("", line).strip()
            desc = " ".join(curr_desc + [desc_part]).strip()
            desc = DESC_LEAD_NUM_RE.sub("", desc)
            desc = CURRENCY_STRIP_RE.sub("", desc).strip()
            if desc and amt:
                items.append({
                    "description": desc,
                    "hsn_sac": hsn,
                    "quantity": qty,
                    "rate": rate,
                    "amount": amt,
                })
            curr_desc = []
            curr_hsn = None
        else:
            if not DESC_TAX_WORD_RE.search(line):
                curr_desc.append(line)

    if not items and curr_desc:
        desc = " ".join(curr_desc).strip()
        desc = DESC_LEAD_NUM_RE.sub("", desc)
        sac_code = None
        base_amt = None
        for rem_line in lines[header_idx + 1: min(header_idx + 35, len(lines))]:
            if not sac_code:
                m_sac = re.search(r"\b(99\d{4})\b", rem_line)
                if m_sac:
                    sac_code = m_sac.group(1)
            if base_amt is None:
                m_amt = DECIMAL_AMOUNT_RE.search(rem_line)
                if m_amt:
                    val = float(m_amt.group(0).replace(",", ""))
                    if val > 10.0 and val not in (2024, 2025, 2026, 2027):
                        base_amt = val
        if desc and base_amt:
            items.append({
                "description": desc,
                "hsn_sac": sac_code,
                "quantity": None,
                "rate": None,
                "amount": base_amt,
            })

    # Deduplicate / merge redundant items caused by overlapping PDF text layers
    merged = []
    for item in items:
        if not merged:
            merged.append(item)
            continue
        prev = merged[-1]
        p_desc = re.sub(r"[^a-z0-9]", "", prev["description"].lower())
        c_desc = re.sub(r"[^a-z0-9]", "", item["description"].lower())
        if p_desc and c_desc and (p_desc in c_desc or c_desc in p_desc):
            best_desc = prev["description"] if len(prev["description"]) >= len(item["description"]) else item["description"]
            best_desc = re.sub(r"(\s+\d+%\s*)+$", "", best_desc).strip()
            qty = prev.get("quantity") or item.get("quantity")
            amt = max(prev.get("amount") or 0, item.get("amount") or 0)
            rate = prev.get("rate") or item.get("rate")
            if not rate and qty and amt:
                calc_rate = round(amt / qty, 2)
                if abs(calc_rate * qty - amt) <= 0.05:
                    rate = calc_rate
            merged[-1] = {
                "description": best_desc,
                "hsn_sac": prev.get("hsn_sac") or item.get("hsn_sac"),
                "quantity": qty,
                "rate": rate,
                "amount": amt,
            }
        else:
            merged.append(item)
    return merged


def _norm(v):
    return re.sub(r"[^a-z0-9]", "", (v or "").lower())


def separate_parties(doc):
    """
    The operator is never GoFloaters. Anything on the operator that belongs to the bill-to party
    (its name, its address, its GSTIN) is removed: null is better than the customer's details.
    """
    op, gf = doc["operator"], doc["gofloaters"]
    removed = []
    name = (op.get("name") or "").lower()
    if name and any(h in name for h in GOFLOATERS_HINTS):
        op["name"] = None
        removed.append("operator.name")
    a, b = _norm(op.get("address")), _norm(gf.get("address"))
    if a and b and (a in b or b in a):
        op["address"] = None
        removed.append("operator.address")
    if op.get("gstin") and op.get("gstin") == gf.get("gstin"):
        if "AAYCS6808H" in op["gstin"]:
            op["gstin"], op["state"] = None, None
            removed.append("operator.gstin")
        else:
            gf["gstin"], gf["state"] = None, None
            removed.append("gofloaters.gstin")
    if removed:
        doc.setdefault("evidence", {})["operator_cleared_as_billto_data"] = removed
    return removed


def resolve_stacked_header_block(lines):
    """
    Resolves multi-line label/value blocks where consecutive labels ending in ':'
    are followed by consecutive values (e.g. in 26/27-64).
    """
    for i, line in enumerate(lines):
        clean_line = clean(line)
        if clean_line.upper() in ("TAX INVOICE", "INVOICE", "TAX INVOICE / BILL OF SUPPLY", "BILL OF SUPPLY"):
            labels = []
            j = i + 1
            while j < len(lines) and re.search(r":\s*$", clean(lines[j])):
                labels.append(clean(lines[j]))
                j += 1
            if len(labels) >= 2:
                num_vals = len(labels) + 1
                values = [clean(lines[k]) for k in range(j, min(j + num_vals, len(lines)))]
                out = {}
                if len(values) == len(labels) + 1:
                    out["invoice_number"] = values[0]
                    val_map = dict(zip(labels, values[1:]))
                elif len(values) == len(labels):
                    val_map = dict(zip(labels, values))
                else:
                    val_map = {}
                for lbl, v in val_map.items():
                    low_lbl = lbl.lower()
                    if "issue date" in low_lbl or "invoice date" in low_lbl:
                        out["date"] = normalize_date(v)
                    elif "due date" in low_lbl:
                        out["due_date"] = normalize_date(v)
                    elif "place of supply" in low_lbl:
                        out["place_of_supply"] = v
                    elif "invoice no" in low_lbl or "bill no" in low_lbl:
                        out["invoice_number"] = v
                return out
    return {}


def apply_fallbacks(doc, extracted):
    md = extracted.get("markdown") or ""
    texts = [clean(t.get("text", "")) for t in extracted.get("texts", []) if clean(t.get("text", ""))]
    extra_texts = [t for t in texts if t not in md]
    text = md + ("\n\n" + "\n".join(extra_texts) if extra_texts else "")

    # 0. Check stacked header blocks (e.g. TAX INVOICE followed by stacked labels and values)
    hdr_fields = resolve_stacked_header_block(text.splitlines())
    if hdr_fields:
        if not doc["invoice"].get("number") and hdr_fields.get("invoice_number"):
            doc["invoice"]["number"] = hdr_fields["invoice_number"]
        if not doc["invoice"].get("date") and hdr_fields.get("date"):
            doc["invoice"]["date"] = hdr_fields["date"]
        if not doc["invoice"].get("due_date") and hdr_fields.get("due_date"):
            doc["invoice"]["due_date"] = hdr_fields["due_date"]
        if not doc["invoice"].get("place_of_supply") and hdr_fields.get("place_of_supply"):
            doc["invoice"]["place_of_supply"] = hdr_fields["place_of_supply"]

    # 1. Check table columns for explicit tax amounts
    tbl_taxes = extract_table_column_taxes(extracted)
    for k, v in tbl_taxes.items():
        if doc["tax"].get(k) is None:
            doc["tax"][k] = v

    if not doc.get("line_items"):
        items = extract_digital_line_items(text)
        if items:
            doc["line_items"] = items

    extra = regex_extract(text)
    merge_fill(doc, extra, "regex_text")
    if separate_parties(doc):                 # a bill-to detail had landed on the operator: retry from evidence
        merge_fill(doc, extra, "regex_text_retry")

    # If invoice number or date is still missing, check raw sequential text stream
    if not doc["invoice"].get("number") or not doc["invoice"].get("date"):
        raw_text = extracted.get("raw_text")
        if raw_text and raw_text != text:
            raw_extra = regex_extract(raw_text)
            if not doc["invoice"].get("number") and raw_extra.get("invoice", {}).get("number"):
                doc["invoice"]["number"] = raw_extra["invoice"]["number"]
            if not doc["invoice"].get("date") and raw_extra.get("invoice", {}).get("date"):
                doc["invoice"]["date"] = raw_extra["invoice"]["date"]

    # 2. Check stacked summary blocks if taxes are still missing
    if any(doc["tax"].get(k) is None for k in ("taxable_amount", "total", "cgst", "sgst", "igst")):
        stacked = extract_stacked_summary(text)
        if stacked:
            if "taxable_amount" in stacked:
                doc["tax"]["taxable_amount"] = stacked["taxable_amount"]
            if "total" in stacked:
                doc["tax"]["total"] = stacked["total"]
            for k, v in stacked.items():
                if doc["tax"].get(k) is None:
                    doc["tax"][k] = v

    derive_fields(doc, text)
    arithmetic_match(doc, text)

    # General check: If no separate CGST/SGST/IGST breakdown exists, record lumped GST mention
    if all(doc["tax"].get(k) is None for k in ("cgst", "sgst", "igst")):
        if (
            re.search(
                r"(?i)\b(?:"
                r"gst\s*(?:@|:|-)?\s*\(?\s*\d+(?:\.\d+)?%\)?"
                r"|tax\s*(?:@|:|-)?\s*\(?\s*\d+(?:\.\d+)?%\)?"
                r"|gst\s*(?:total|amount|rate|charge|charges|value|payable|tax|output)"
                r"|(?:total|output|add|plus)\s*gst"
                r"|goods\s*(?:and|&)\s*services\s*tax"
                r"|gst\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*[\d,]+(?:\.\d{2})?"
                r")\b",
                text,
            )
            and not re.search(r"(?i)\b(?:cgst|sgst|igst)\b", text)
        ):
            doc.setdefault("evidence", {})["has_lumped_gst_mention"] = True

    fill_addresses(doc, text)          # positive-evidence addresses; table leftovers are discarded

    separate_parties(doc)
    for party in ("operator", "gofloaters"):
        p = doc[party]
        if not p.get("state"):
            p["state"] = state_from_gstin(p.get("gstin")) or state_from_text(p.get("address"))

    if not doc["gofloaters"].get("name"):
        for item in extracted.get("texts", []):
            txt = clean(item.get("text"))
            m = re.search(r"(?i)\b(?:bill(?:ed)?\s*to|customer|buyer|party(?:\s*details)?)\b\s*[:\-]?\s*([A-Za-z0-9&.,()' -]{3,80}\b(?:limited|ltd\.?|llp|pvt\.?\s*ltd\.?|private\s+limited|inc\.?)\.?)", txt)
            if m:
                doc["gofloaters"]["name"] = clean(m.group(1))
                break
    if not doc["gofloaters"].get("name"):
        for item in extracted.get("texts", []):
            txt = clean(item.get("text"))
            low = txt.lower()
            if any(h in low for h in GOFLOATERS_HINTS):
                if "smbsure" in low:
                    m = re.search(r"(?i)\b(smbsure\s+business\s+solutions(?:\s+private\s+limited|\s+pvt\.?\s*ltd\.?)?)\b", txt)
                    doc["gofloaters"]["name"] = clean(m.group(1)) if m else txt
                elif "gofloater" in low or "go float" in low or "gofloter" in low or "go floter" in low:
                    doc["gofloaters"]["name"] = "GoFloaters"
                break

    if not doc["gofloaters"].get("name"):
        if doc["gofloaters"].get("gstin") and "AAYCS6808H" in doc["gofloaters"]["gstin"]:
            doc["gofloaters"]["name"] = "GoFloaters"

    if doc["gofloaters"].get("name"):
        doc["gofloaters"]["name"] = re.sub(r"^(?:name|customer(?:\s*name)?|buyer(?:\s*name)?|bill(?:\s*to)?|m/s\.?)\s*[:\-]\s*", "", doc["gofloaters"]["name"], flags=re.I).strip()

    op_name = doc["operator"].get("name") or ""
    if re.search(r"\bPAN\b|\b[A-Z]{5}[0-9]{4}[A-Z]\b", op_name, re.I):
        doc["operator"]["name"] = None
        op_name = ""

    if "favouring" in op_name.lower():
        m = re.search(r"(?i)\bfavouring\s+([A-Za-z0-9&.,' -]{3,60}?)\s+payable\b", op_name)
        if m:
            doc["operator"]["name"] = clean(m.group(1))
    elif not doc["operator"].get("name") or not is_valid_party_name(doc["operator"].get("name"), for_party="operator"):
        doc["operator"]["name"] = None
        for item in extracted.get("texts", []):
            txt = clean(item.get("text"))
            if is_valid_party_name(txt, for_party="operator") and not looks_like_address(txt):
                if looks_like_organization(txt):
                    doc["operator"]["name"] = txt
                    break
        if not doc["operator"].get("name"):
            for item in extracted.get("texts", [])[:15]:
                txt = clean(item.get("text"))
                if is_valid_party_name(txt, for_party="operator") and not looks_like_address(txt):
                    doc["operator"]["name"] = txt
                    break

    for party in ("operator", "gofloaters"):
        if doc[party].get("name"):
            doc[party]["name"] = clean_party_name(doc[party]["name"])
        if doc[party].get("address"):
            doc[party]["address"] = strip_line_item_text(doc[party]["address"], doc.get("line_items"))
            doc[party]["address"] = clean_party_address(doc[party]["address"], doc[party].get("name"))

    # A due date is optional on an invoice: it is never listed as missing (see missing_fields).
    doc["missing_after_extraction"] = missing_fields(doc)

    warnings = []
    for party in ("operator", "gofloaters"):
        for key in ("name", "address", "state"):
            if not doc[party].get(key):
                warnings.append(f"{party}.{key} not found")
    t = doc["tax"]
    parts = [t.get(k) for k in ("cgst", "sgst", "igst") if t.get(k) is not None]
    if t.get("taxable_amount") is not None and t.get("total") is not None and parts:
        if abs(t["taxable_amount"] + sum(parts) - t["total"]) > 1.05:
            warnings.append("total does not equal taxable amount + taxes")
    ev = doc.get("evidence", {})
    if "unlabelled_gst_total" in ev or "unlabelled_gst_amounts" in ev:
        warnings.append("GST amount found but no explicit CGST / SGST / IGST label, so the tax fields were left null.")
    if ev.get("no_gst_charged"):
        warnings.append("No CGST / SGST / IGST found on the invoice: taxable amount was set equal to the total.")
    pos = doc["invoice"].get("place_of_supply") or ""
    pos_code = pos_state_code(pos)
    op_c, gf_c = (doc["operator"].get("gstin") or "")[:2], (doc["gofloaters"].get("gstin") or "")[:2]
    if pos_code and op_c and gf_c and op_c != gf_c and pos_code == op_c:
        warnings.append(f"Place of supply is {pos} (same as operator state) but the GoFloaters GSTIN is in another "
                        f"state. Validation follows GSTINs and addresses (REQ1-REQ3); place of supply is only supporting evidence.")
    doc["warnings"] = warnings
    return doc
