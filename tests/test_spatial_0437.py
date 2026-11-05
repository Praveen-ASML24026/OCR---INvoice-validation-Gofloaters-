from pathlib import Path
from invoice_parser.main import process


def test_spatial_extraction_invoice_0437():
    sample = Path("../useless/Aug 2026/0437 - Board_Room.pdf")
    if not sample.exists():
        return

    result = process(str(sample), fast_pdf=True)

    # 1. Invoice Number & Date
    assert result["invoice"]["number"] == "0437"
    assert result["invoice"]["date"] == "2026-08-13"
    assert result["invoice"]["place_of_supply"] == "Karnataka"

    # 2. Operator Details
    assert result["operator"]["name"] == "Rainmakersworkspace India Private Limited - 2025-26"
    assert result["operator"]["gstin"] == "29AAICR7938R1Z5"
    assert result["operator"]["state"] == "Karnataka"

    # 3. Customer / GoFloaters Details
    assert result["gofloaters"]["name"] == "SMBSure Business Solution Pvt Ltd (KA)"
    assert result["gofloaters"]["gstin"] == "29AAYCS6808H1ZI"
    assert result["gofloaters"]["state"] == "Karnataka"

    # 4. Tax (Intra-state Karnataka CGST + SGST)
    assert result["tax"]["taxable_amount"] == 2400
    assert result["tax"]["cgst"] == 216
    assert result["tax"]["sgst"] == 216
    assert result["tax"]["igst"] is None
    assert result["tax"]["total"] == 2832

    # 5. Line items
    assert len(result["line_items"]) == 1
    item = result["line_items"][0]
    assert "Board Room Usage" in item["description"]
    assert item["quantity"] == 1
    assert item["rate"] == 2400
    assert item["amount"] == 2400

    # 6. GST compliance validation
    assert result["validation"]["valid"] is True
    assert result["validation"]["status"] == "valid"
