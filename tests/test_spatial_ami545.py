from pathlib import Path
from invoice_parser.main import process


def test_spatial_extraction_invoice_ami545():
    sample = Path("../useless/Aug 2026/ INV-AMI-545 - INV-AMI-545.pdf")
    if not sample.exists():
        return

    result = process(str(sample), fast_pdf=True)

    # 1. Invoice Number & Date
    assert result["invoice"]["number"] == "INV-AMI-545"
    assert result["invoice"]["date"] == "2026-08-19"
    assert "Uttar Pradesh" in result["invoice"]["place_of_supply"]

    # 2. Operator Details
    assert result["operator"]["name"] == "AMIGO"
    assert result["operator"]["gstin"] == "09AFMPA4361B1ZT"
    assert "Noida" in result["operator"]["address"]
    assert "201301" in result["operator"]["address"]

    # 3. Customer / GoFloaters Details (Bill To address accurately extracted, distinct from Ship To)
    assert "SMBSure Business Solutions" in result["gofloaters"]["name"]
    assert result["gofloaters"]["gstin"] == "33AAYCS6808H1ZT"
    assert result["gofloaters"]["address"] is not None
    assert "Mogappair West" in result["gofloaters"]["address"]
    assert "CHENNAI" in result["gofloaters"]["address"]
    assert "600037" in result["gofloaters"]["address"]
    assert "Tamil Nadu" in result["gofloaters"]["address"]
    # Ensure parallel Ship To (NOIDA / C-25) did not corrupt customer address
    assert "NOIDA" not in result["gofloaters"]["address"]
    assert "C-25" not in result["gofloaters"]["address"]

    # 4. Tax
    assert result["tax"]["taxable_amount"] == 1996
    assert result["tax"]["cgst"] == 179.64
    assert result["tax"]["sgst"] == 179.64
    assert result["tax"]["total"] == 2355.28

    # 5. Line items
    assert len(result["line_items"]) >= 1
    item = result["line_items"][0]
    assert item["quantity"] == 1
    assert item["amount"] == 1996

    # 6. GST compliance validation (Amigo UP charged CGST+SGST, Place of Supply is UP -> valid)
    assert result["validation"]["status"] == "valid"
    assert result["validation"]["valid"] is True
    assert result["missing_after_extraction"] == []
