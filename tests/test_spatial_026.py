from pathlib import Path
from invoice_parser.main import process

def test_spatial_extraction_invoice_026():
    sample = Path("../useless/Aug 2026/026 - 026.PI-SMBSURE_BUSINESS_SOLUTIONS_-Sep-26.pdf")
    if not sample.exists():
        return

    result = process(str(sample), fast_pdf=True)

    # 1. Invoice Number & Date
    assert result["invoice"]["number"] == "026"
    assert result["invoice"]["date"] == "2026-09-17"

    # 2. Operator Details
    assert result["operator"]["name"] == "Global INcubation SERVices"
    assert result["operator"]["gstin"] == "29AADCG7059H1ZA"
    assert "Bangalore 560008" in result["operator"]["address"]

    # 3. Customer / GoFloaters Details
    assert "SMBSURE BUSINESS SOLUTIONS" in result["gofloaters"]["name"]
    assert result["gofloaters"]["gstin"] == "29AAYCS6808H1ZI"
    assert "560048" in result["gofloaters"]["address"]

    # 4. Tax
    assert result["tax"]["taxable_amount"] == 10000
    assert result["tax"]["cgst"] == 900
    assert result["tax"]["sgst"] == 900
    assert result["tax"]["total"] == 11800

    # 5. Line items
    assert len(result["line_items"]) == 1
    item = result["line_items"][0]
    assert item["quantity"] == 4
    assert item["rate"] == 2500
    assert item["amount"] == 10000
    assert item["hsn_sac"] == "997212"

    # 6. GST compliance validation
    assert result["validation"]["status"] == "valid"
