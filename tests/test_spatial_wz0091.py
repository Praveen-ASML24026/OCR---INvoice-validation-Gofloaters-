from pathlib import Path
from invoice_parser.main import process


def test_spatial_extraction_invoice_wz_0091():
    sample = Path("../useless/Aug 2026/WZ_GST_2627_0091 - Inv-0091_SMBSure.pdf")
    if not sample.exists():
        return

    result = process(str(sample), fast_pdf=True)

    # 1. Invoice Number & Date
    assert result["invoice"]["number"] == "WZ/GST/2627/0091"
    assert result["invoice"]["date"] == "2026-08-14"

    # 2. Operator Details (Workzen)
    assert result["operator"]["name"] == "Workzen Business Centre Private Limited"
    assert result["operator"]["gstin"] == "33AAECW0838K1Z8"
    assert "Chennai-53" in result["operator"]["address"]
    assert "Delivery Note" not in result["operator"]["name"]
    assert "Delivery Note" not in result["operator"]["address"]

    # 3. Customer / GoFloaters Details
    assert "Smbsure Business Solutions Private Limited" in result["gofloaters"]["name"]
    assert result["gofloaters"]["gstin"] == "33AAYCS6808H1ZT"
    assert "Chennai" in result["gofloaters"]["address"]
    assert "Dispatch Doc No" not in result["gofloaters"]["address"]

    # 4. Tax
    assert result["tax"]["taxable_amount"] == 320
    assert result["tax"]["cgst"] == 28.8
    assert result["tax"]["sgst"] == 28.8
    assert result["tax"]["total"] == 378

    # 5. Validation Status
    assert result["validation"]["status"] == "valid"
