"""
Confidence Scoring Module for Invoice Field Extraction.
Calculates calibrated confidence scores (0.0 to 1.0) on extracted key fields:
- invoice_number
- taxable_amount
- gstin (operator & customer)
- dates (invoice_date & due_date)
"""
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple


from .normalize import STATE_CODES

GSTIN_EXACT_REGEX = re.compile(
    r"^[0-9]{2}[A-Z]{4,5}[0-9]{4}[A-Z0-9]{1,2}Z[A-Z0-9]$"
)


def score_invoice_number(inv_num: Optional[str], sources: Dict[str, Any]) -> float:
    """Calculates confidence score for extracted invoice number."""
    if not inv_num or not isinstance(inv_num, str):
        return 0.0

    val = inv_num.strip()
    if len(val) < 2 or len(val) > 40:
        return 0.40

    low = val.lower()
    # Reject obvious non-invoice tokens
    if any(bad in low for bad in ["total", "gstin", "invoice", "date", "amount", "rupees", "balance", "thank"]):
        return 0.20

    score = 0.85
    # Has digits and alphanumeric separators typical of invoice IDs
    if any(c.isdigit() for c in val):
        score += 0.05
    if any(c in "/-_" for c in val):
        score += 0.05

    # Boost if explicitly labeled in extraction sources
    src = str(sources.get("invoice.number", "")).lower()
    if "labeled" in src or "semantic" in src:
        score += 0.05

    return round(min(1.0, max(0.0, score)), 2)


def score_taxable_amount(tax_dict: Dict[str, Any]) -> Tuple[float, bool]:
    """
    Calculates confidence score for taxable amount.
    Returns (score, tax_invariant_verified).
    """
    taxable = tax_dict.get("taxable_amount")
    total = tax_dict.get("total")

    if taxable is None:
        return 0.0, False

    try:
        taxable_val = float(taxable)
    except (ValueError, TypeError):
        return 0.0, False

    if taxable_val <= 0:
        return 0.30, False

    # Check mathematical invariant: taxable + cgst + sgst + igst == total
    taxes = [tax_dict.get(k) for k in ("cgst", "sgst", "igst") if tax_dict.get(k) is not None]
    if total is not None and taxes:
        try:
            sum_taxes = sum(float(t) for t in taxes)
            expected_total = taxable_val + sum_taxes
            actual_total = float(total)
            if abs(expected_total - actual_total) <= 1.05:
                return 1.0, True  # Mathematically proven consistency (accounting for standard GST round-off)
            else:
                return 0.30, False  # Mismatch between components and total
        except (ValueError, TypeError):
            pass

    if total is not None:
        try:
            if float(total) >= taxable_val:
                return 0.90, False
        except (ValueError, TypeError):
            pass

    return 0.80, False


def score_gstin(gstin: Optional[str], state: Optional[str] = None) -> float:
    """Calculates confidence score for a single GSTIN string."""
    if not gstin or not isinstance(gstin, str):
        return 0.0

    val = gstin.strip().upper()
    if len(val) != 15:
        return 0.50

    if not GSTIN_EXACT_REGEX.match(val):
        return 0.60

    from .validators import verify_gstin_checksum
    if not verify_gstin_checksum(val):
        return 0.40

    score = 0.90
    # Check if 14th char is standard 'Z'
    if val[13] == "Z":
        score += 0.05

    # Check if 2-digit state code matches state name
    if state:
        code = val[:2]
        expected_state = STATE_CODES.get(code, "").lower()
        if expected_state and (expected_state in state.lower() or state.lower() in expected_state):
            score += 0.05

    return round(min(1.0, max(0.0, score)), 2)


def score_date(date_str: Optional[str]) -> float:
    """Calculates confidence score for a date string."""
    if not date_str or not isinstance(date_str, str):
        return 0.0

    val = date_str.strip()
    # Check standard ISO format YYYY-MM-DD
    try:
        dt = datetime.strptime(val, "%Y-%m-%d").date()
        today = datetime.now().date()
        if dt > today:
            return 0.20
        # Reasonable invoice year range: 2017 (GST start) to today
        if 2017 <= dt.year <= (today.year + 1):
            return 0.98
        return 0.70
    except ValueError:
        pass

    # Other recognizable date format
    if re.search(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", val):
        return 0.80

    return 0.50


def calculate_confidence_scores(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes confidence scores for all key fields in the normalized document.
    Returns structured confidence dict with scores between 0.0 and 1.0.
    """
    sources = doc.get("extraction_sources", {})
    invoice_dict = doc.get("invoice", {})
    operator_dict = doc.get("operator", {})
    customer_dict = doc.get("gofloaters", {})
    tax_dict = doc.get("tax", {})

    # 1. Invoice Number Confidence
    inv_num_score = score_invoice_number(invoice_dict.get("number"), sources)

    # 2. Taxable Amount Confidence
    taxable_score, math_verified = score_taxable_amount(tax_dict)

    # 3. GSTIN Confidence
    op_gstin_score = score_gstin(operator_dict.get("gstin"), operator_dict.get("state"))
    cust_gstin_score = score_gstin(customer_dict.get("gstin"), customer_dict.get("state"))

    # Combined GSTIN score (prioritizing operator if present)
    gstin_scores = [s for s in [op_gstin_score, cust_gstin_score] if s > 0]
    gstin_score = round(sum(gstin_scores) / len(gstin_scores), 2) if gstin_scores else 0.0

    # 4. Dates Confidence
    inv_date_score = score_date(invoice_dict.get("date"))
    due_date_score = score_date(invoice_dict.get("due_date"))
    date_scores = [s for s in [inv_date_score, due_date_score] if s > 0]
    dates_score = round(sum(date_scores) / len(date_scores), 2) if date_scores else 0.0

    # Overall Confidence (Weighted Average)
    weights = {
        "invoice_number": 0.25,
        "taxable_amount": 0.30,
        "gstin": 0.25,
        "dates": 0.20,
    }
    overall = (
        (inv_num_score * weights["invoice_number"])
        + (taxable_score * weights["taxable_amount"])
        + (gstin_score * weights["gstin"])
        + (dates_score * weights["dates"])
    )

    return {
        "invoice_number": inv_num_score,
        "taxable_amount": taxable_score,
        "gstin": gstin_score,
        "dates": dates_score,
        "overall": round(overall, 2),
        "details": {
            "operator_gstin": op_gstin_score,
            "customer_gstin": cust_gstin_score,
            "invoice_date": inv_date_score,
            "due_date": due_date_score,
            "tax_invariant_verified": math_verified,
        },
    }
