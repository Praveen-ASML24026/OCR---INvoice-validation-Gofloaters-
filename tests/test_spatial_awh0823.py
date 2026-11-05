from pathlib import Path
from invoice_parser.main import process


def test_spatial_extraction_invoice_awh0823():
    sample = Path("../useless/Aug 2026/2627-AWH0823 - GoFloters_2627-AWH0823.pdf")
    if not sample.exists():
        return

    result = process(str(sample), fast_pdf=True)

    # 1. Invoice Number & Date
    assert result["invoice"]["number"] == "2627-AWH0823"
    assert result["invoice"]["date"] == "2026-08-24"

    # 2. Operator Details
    assert result["operator"]["name"] == "AlienWorkHub LLP"
    assert result["operator"]["gstin"] == "36ABYFA4985H1ZN"
    assert result["operator"]["state"] == "Telangana"

    # 3. Customer / GoFloaters Details (handles typo GoFloters)
    assert result["gofloaters"]["name"] == "GoFloaters"
    assert result["gofloaters"]["gstin"] == "33AAYCS6808H1ZT"
    assert result["gofloaters"]["state"] == "Tamil Nadu"

    # 4. Tax (Inter-state IGST only; nil CGST/SGST)
    assert result["tax"]["taxable_amount"] == 1200
    assert result["tax"]["cgst"] is None
    assert result["tax"]["sgst"] is None
    assert result["tax"]["igst"] == 216
    assert result["tax"]["total"] == 1416

    # 5. Line items
    assert len(result["line_items"]) == 1
    item = result["line_items"][0]
    assert "Meeting room 03 Hours" in item["description"]
    assert item["quantity"] == 3
    assert item["rate"] == 400.0
    assert item["amount"] == 1200

    # 6. GST compliance validation
    assert result["validation"]["valid"] is True
    assert result["validation"]["status"] == "valid"
