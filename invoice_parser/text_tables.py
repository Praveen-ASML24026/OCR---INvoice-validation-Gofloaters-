"""
Text-based Table Extractor
Extracts tabular structures (line items, taxes, subtotals, grand totals)
from plain text or digital PDF text streams when Docling OCR is bypassed.
"""
import re
from typing import Any, Dict, List, Optional


HEADER_KEYWORDS = [
    r"\bdescription\b",
    r"\bparticulars\b",
    r"\bitem\b",
    r"\bamount\b",
    r"\brate\b",
    r"\bunits?\b",
    r"\bqty\b",
    r"\bquantity\b",
    r"\bunit\s*price\b",
    r"\bprice\b",
    r"\btotal\b",
    r"\bhrs\.?\b",
    r"\bhours\b",
    r"\bsac\b",
    r"\bhsn\b",
]

SUMMARY_LABEL_PAT = re.compile(
    r"\b(?:total|sub\s*total|subtotal|item\s*total|taxable|cgst\d*|sgst\d*|utgst\d*|igst\d*|gst\d*|round\s*off|net\s*amount|grand\s*total|amount\s*payable|balance\s*due)\b",
    re.I,
)


def extract_tables_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Parses plain text lines into structured table grids matching Docling's table format:
    [{"rows": [ [col0, col1, ...], ... ]}]
    """
    if not text:
        return []

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return []

    # Step 1: Locate Table Header Line
    header_idx = None
    for i, line in enumerate(lines):
        matches = sum(1 for kw in HEADER_KEYWORDS if re.search(kw, line, re.I))
        # Must have at least description and amount/rate/qty
        if matches >= 2 and re.search(r"\b(?:description|particulars|item)\b", line, re.I):
            header_idx = i
            break

    stop_table_pattern = re.compile(
        r"^(?:place\s*of\s*supply|bank\s*details|account\s*name|terms|as\s*agreed|authorized|powered\s*by|note|this\s*is|subject\s*to|amount\s*chargeable|hsn[\s\/]*sac|tax\s*amount\s*\(in\s*words\))\b",
        re.I,
    )

    # Step 1b: If standard multi-column header not found, check for "Billing Summary" section
    if header_idx is None:
        billing_idx = None
        for i, line in enumerate(lines):
            if re.search(r"\bbilling\s*summary\b", line, re.I):
                billing_idx = i
                break

        if billing_idx is not None:
            header_cols = ["#", "Description", "Units", "Rate", "Amount"]
            rows = [header_cols]
            i = billing_idx + 1
            item_desc: List[str] = []
            while i < len(lines):
                line = lines[i]
                if stop_table_pattern.search(line):
                    break
                m_chg = re.search(
                    r"^(?:Charges|Base\s*Amount|Rental\s*Charges)\s*[:\-]?\s*(?:INR|Rs\.?|₹)?\s*(-?\d[\d,]*(?:\.\d{1,2})?)\s*$",
                    line,
                    re.I,
                )
                if m_chg:
                    chg_val = m_chg.group(1).replace(",", "")
                    desc_str = " ".join(item_desc).strip() or "Conference / Meeting Room"
                    desc_str = re.sub(r"\bBilling\s*Period\b\s*", "(Period: ", desc_str, flags=re.I)
                    if "(Period:" in desc_str and not desc_str.endswith(")"):
                        desc_str += ")"
                    rows.append(["1", desc_str, "1", chg_val, chg_val])
                    rows.append(["Sub Total", "", "", "", chg_val])
                    item_desc = []
                    i += 1
                    continue

                m_tax = re.search(
                    r"^(CGST|SGST|IGST)\d*\s*[:\-]?\s*(?:INR|Rs\.?|₹)?\s*(-?\d[\d,]*(?:\.\d{1,2})?)\s*$",
                    line,
                    re.I,
                )
                if m_tax:
                    t_lbl = m_tax.group(1).upper()
                    t_val = m_tax.group(2).replace(",", "")
                    rows.append([t_lbl, "", "", "", t_val])
                    i += 1
                    continue

                m_tot = re.search(
                    r"^(?:Total\s*Charges|Grand\s*Total|Net\s*Amount|Total)\s*[:\-]?\s*(?:INR|Rs\.?|₹)?\s*(-?\d[\d,]*(?:\.\d{1,2})?)\s*$",
                    line,
                    re.I,
                )
                if m_tot:
                    tot_val = m_tot.group(1).replace(",", "")
                    rows.append(["Total", "", "", "", tot_val])
                    i += 1
                    continue

                m_words = re.search(r"(?:Total\s*Charges|In\s*Words).*?(\d[\d,]*(?:\.\d{1,2})?)\s*$", line, re.I)
                if m_words:
                    tot_val = m_words.group(1).replace(",", "")
                    if not any(r[0] in ("Total", "Grand Total") for r in rows):
                        rows.append(["Total", "", "", "", tot_val])
                    i += 1
                    continue

                if not re.search(r"^(?:GST\d*|CGST\d*|SGST\d*|IGST\d*|Total\s*Charges)\b", line, re.I):
                    cleaned_line = re.sub(r"^(?:Number\s*of\s*Seats|Item|Particulars)\s*[:\-]?\s*", "", line, flags=re.I).strip()
                    if cleaned_line:
                        item_desc.append(cleaned_line)
                i += 1

            if len(rows) > 1:
                return [{"rows": rows}]

        return []

    header_cols = ["#", "Description", "Units", "Rate", "Amount"]
    rows = [header_cols]

    # Step 2: Extract rows until table terminates
    current_desc_parts: List[str] = []
    current_item_no: Optional[str] = None

    _NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    six_numbers = re.compile(rf"(\d{{4,8}})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*$")
    five_numbers = re.compile(rf"({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*$")
    four_numbers = re.compile(rf"(\d{{4,8}})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*$")
    row_end_numbers = re.compile(rf"({_NUM})\s+({_NUM})\s+({_NUM})\s*$")
    two_numbers = re.compile(rf"({_NUM})\s+({_NUM})\s*$")

    i = header_idx + 1
    while i < len(lines):
        line = lines[i]

        # Stop condition for table section
        if stop_table_pattern.search(line):
            break

        # Check for Summary / Tax rows:
        # E.g.: "Total 2120.00", "CGST(9%)(+) 190.80", "Round Off(+) 0.40", "Net Amount INR 2502.00", "CGST Output @ 9% 9 % 216.00"
        m_sum = re.search(
            r"^([A-Za-z0-9%@()\s\+\-\/\._]+?)\s*[:\-]?\s*(?:INR|Rs\.?|₹)?\s*(-?\d[\d,]*(?:\.\d{1,2})?)\s*$",
            line,
            re.I,
        )
        if m_sum and SUMMARY_LABEL_PAT.search(m_sum.group(1)):
            label = m_sum.group(1).strip()
            val = m_sum.group(2).replace(",", "").strip()

            # Commit any pending line item description before summary
            if current_desc_parts:
                desc = " ".join(current_desc_parts).strip()
                rows.append([current_item_no or "1", desc, "", "", ""])
                current_desc_parts = []
                current_item_no = None

            # Map into row structure matching table width
            sum_row = [label, "", "", "", val]
            rows.append(sum_row)
            i += 1
            continue

        # Check for Line Item row:
        item_start = re.match(r"^(\d+)\s+([A-Za-z].*)$", line)
        item_idx = None
        line_body = line
        if item_start and not current_desc_parts:
            item_idx = item_start.group(1)
            line_body = item_start.group(2).strip()

        # Pattern B0_tax: SAC, Qty, Rate, Tax% TaxAmt ..., Amount
        m_tax = re.search(r"(\d{4,8})\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(?:\d+%\s+[\d,]+(?:\.\d+)?\s+)*([\d,]+(?:\.\d+)?)$", line_body)
        if m_tax:
            sac, qty, rate, amt = m_tax.group(1), m_tax.group(2).replace(",", ""), m_tax.group(3).replace(",", ""), m_tax.group(4).replace(",", "")
            prefix = line_body[: m_tax.start()].strip()
            if prefix:
                current_desc_parts.append(prefix)
            desc = " ".join(current_desc_parts).strip()
            if sac:
                desc = f"{desc} (SAC: {sac})".strip()
            rows.append([item_idx or current_item_no or "1", desc, qty, rate, amt])
            current_desc_parts = []
            current_item_no = None
            i += 1
            continue

        # Pattern B0: 6 numbers: SAC (e.g. 997212), Qty, Rate, Tax1, Tax2, Amount
        m6 = six_numbers.search(line_body)
        if m6:
            sac, qty, rate, amt = m6.group(1), m6.group(2).replace(",", ""), m6.group(3).replace(",", ""), m6.group(6).replace(",", "")
            prefix = line_body[: m6.start()].strip()
            if prefix:
                current_desc_parts.append(prefix)
            desc = " ".join(current_desc_parts).strip()
            if sac:
                desc = f"{desc} (SAC: {sac})".strip()
            rows.append([item_idx or current_item_no or "1", desc, qty, rate, amt])
            current_desc_parts = []
            current_item_no = None
            i += 1
            continue

        # Pattern B0b: 5 numbers: Qty, Rate, Tax1, Tax2, Amount
        m5 = five_numbers.search(line_body)
        if m5:
            qty, rate, amt = m5.group(1).replace(",", ""), m5.group(2).replace(",", ""), m5.group(5).replace(",", "")
            prefix = line_body[: m5.start()].strip()
            if prefix:
                current_desc_parts.append(prefix)
            desc = " ".join(current_desc_parts).strip()
            rows.append([item_idx or current_item_no or "1", desc, qty, rate, amt])
            current_desc_parts = []
            current_item_no = None
            i += 1
            continue

        # Pattern B1: 4 numbers: SAC (e.g. 997212), Qty (e.g. 4.00), Rate (e.g. 2,500.00), Amount (e.g. 10,000.00)
        m4 = four_numbers.search(line_body)
        if m4:
            sac, qty, rate, amt = m4.group(1), m4.group(2).replace(",", ""), m4.group(3).replace(",", ""), m4.group(4).replace(",", "")
            prefix = line_body[: m4.start()].strip()
            if prefix:
                current_desc_parts.append(prefix)
            desc = " ".join(current_desc_parts).strip()
            if sac:
                desc = f"{desc} (SAC: {sac})".strip()
            rows.append([item_idx or current_item_no or "1", desc, qty, rate, amt])
            current_desc_parts = []
            current_item_no = None
            i += 1
            continue

        # Pattern B2: numeric values line ending a description: "1 2120.00 2120.00" (qty, rate, amount)
        m3 = row_end_numbers.search(line)
        if m3:
            qty, rate, amt = m3.group(1).replace(",", ""), m3.group(2).replace(",", ""), m3.group(3).replace(",", "")
            prefix = line[: m3.start()].strip()
            if prefix:
                current_desc_parts.append(prefix)
            desc = " ".join(current_desc_parts).strip()
            rows.append([current_item_no or "1", desc, qty, rate, amt])
            current_desc_parts = []
            current_item_no = None
            i += 1
            continue

        # Pattern C: two numbers (rate, amount) with qty=1
        m2 = two_numbers.search(line)
        if m2 and current_desc_parts:
            rate, amt = m2.group(1).replace(",", ""), m2.group(2).replace(",", "")
            prefix = line[: m2.start()].strip()
            if prefix:
                current_desc_parts.append(prefix)
            desc = " ".join(current_desc_parts).strip()
            rows.append([current_item_no or "1", desc, "1", rate, amt])
            current_desc_parts = []
            current_item_no = None
            i += 1
            continue

        # Pattern D: single number ending line with an item index (e.g., "1 Board Room Usage 2,400.00")
        if item_idx:
            m1 = re.search(rf"^(.+?)\s+({_NUM})\s*$", line_body)
            if m1:
                desc_val = m1.group(1).strip()
                amt_val = m1.group(2).replace(",", "")
                if desc_val and not SUMMARY_LABEL_PAT.search(desc_val):
                    if current_desc_parts:
                        desc_val = " ".join(current_desc_parts + [desc_val]).strip()
                    rows.append([item_idx, desc_val, "1", amt_val, amt_val])
                    current_desc_parts = []
                    current_item_no = None
                    i += 1
                    continue

        # If it was an item start with description only on this line
        if item_start and not current_desc_parts:
            current_item_no = item_idx
            current_desc_parts.append(line_body)
            i += 1
            continue

        # Continuation line of previous description
        if current_desc_parts:
            current_desc_parts.append(line)
            i += 1
            continue

        i += 1

    if current_desc_parts:
        desc = " ".join(current_desc_parts).strip()
        rows.append([current_item_no or "1", desc, "", "", ""])

    if len(rows) > 1:
        return [{"rows": rows}]

    return []
