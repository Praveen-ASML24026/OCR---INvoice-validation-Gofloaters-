from pathlib import Path
from invoice_parser.main import process


def test_spatial_extraction_osg3_invoice():
    sample = Path(r"C:\Projects\Gofloaters\Invoice-docling\DoclingApi\useless\Aug 2026\OSG3_26-27_00203 - OSG326-2700203.pdf")
    if not sample.exists():
        return

    result = process(str(sample), fast_pdf=True)

    # 1. Invoice Number, Date, Due Date, Place of Supply
    assert result["invoice"]["number"] == "OSG3/26-27/00203"
    assert result["invoice"]["date"] == "2026-08-23"
    assert result["invoice"]["due_date"] == "2026-08-29"
    assert result["invoice"]["place_of_supply"] == "Haryana (06)"

    # 2. Operator & GoFloaters
    assert result["operator"]["name"] == "Ofis Spaces Private Limited"
    assert result["operator"]["gstin"] == "06AADCO8447M1ZX"
    assert result["operator"]["state"] == "Haryana"

    assert result["gofloaters"]["gstin"] == "33AAYCS6808H1ZT"
    assert result["gofloaters"]["state"] == "Tamil Nadu"
    assert "Chennai" in result["gofloaters"]["address"]

    # 3. Line items
    assert len(result["line_items"]) == 2
    assert result["line_items"][0]["description"] == "Day Pass"
    assert result["line_items"][0]["hsn_sac"] == "997212"
    assert result["line_items"][0]["quantity"] == 1
    assert result["line_items"][0]["rate"] == 340
    assert result["line_items"][0]["amount"] == 340

    # 4. Tax
    assert result["tax"]["taxable_amount"] == 680
    assert result["tax"]["cgst"] == 61.2
    assert result["tax"]["sgst"] == 61.2
    assert result["tax"]["total"] == 802.4
