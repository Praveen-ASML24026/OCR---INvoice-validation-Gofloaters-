from pathlib import Path
from invoice_parser.main import process

AUG_DIR = Path(r"C:\Projects\Gofloaters\Invoice-docling\DoclingApi\useless\Aug 2026")


def test_inv_002867_extraction_and_validation():
    pdf_path = AUG_DIR / "2867 - INV-002867.pdf"
    if not pdf_path.exists():
        return
    res = process(str(pdf_path))
    assert res["invoice"]["number"] == "INV-002867"
    assert res["operator"]["name"] == "UpStart Business Solutions Pvt Ltd"
    assert res["operator"]["gstin"] == "29AADCI1790F3ZG"
    assert res["gofloaters"]["gstin"] == "33AAYCS6808H1ZT"
    assert "Prestige Shantiniketan" in (res["gofloaters"]["address"] or "")
    assert res["tax"]["taxable_amount"] == 3000.0
    assert res["tax"]["igst"] == 540.0
    assert res["tax"]["total"] == 3540.0
    assert res["validation"]["valid"] is True
    assert res["validation"]["status"] == "valid"
    assert len(res["validation"]["errors"]) == 0


def test_cwvdl_extraction_and_validation():
    pdf_path = AUG_DIR / "CWVDL26270700691 - CWVDL26270700691-DEL.pdf"
    if not pdf_path.exists():
        return
    res = process(str(pdf_path))
    assert res["invoice"]["number"] == "CWVDL26270700691"
    assert res["operator"]["name"] == "Innov8 Workspaces India Limited"
    assert res["operator"]["gstin"] == "07AACCO9563F1Z8"
    assert res["gofloaters"]["gstin"] == "33AAYCS6808H1ZT"
    # Ensure GoFloaters address was cleanly extracted without place of supply corruption
    gf_addr = res["gofloaters"]["address"] or ""
    assert "Millenia" in gf_addr and "Chennai" in gf_addr
    assert not gf_addr.startswith("Delhi")
    assert not gf_addr.startswith("BILLING ADDRESS")
    # Verify exact math amounts
    assert res["tax"]["taxable_amount"] == 1920.0
    assert res["tax"]["cgst"] == 172.8
    assert res["tax"]["sgst"] == 172.8
    assert res["tax"]["total"] == 2265.6
