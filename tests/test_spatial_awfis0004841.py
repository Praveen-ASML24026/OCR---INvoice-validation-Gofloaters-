from pathlib import Path
from invoice_parser.main import process


def test_spatial_extraction_invoice_awfis_0004841():
    sample = Path("../useless/Aug 2026/SP_33_27_0004841 - Awfis_Chennai_03062026.pdf")
    if not sample.exists():
        return

    result = process(str(sample), fast_pdf=True)

    # 1. Invoice Number & Date
    assert result["invoice"]["number"] == "SP/33/27/0004841"
    assert result["invoice"]["date"] == "2026-08-03"

    # 2. Operator Details (Awfis)
    assert result["operator"]["name"] == "Awfis Space Solutions Limited"
    assert result["operator"]["gstin"] == "33AANCA1175G1ZU"
    assert "TVH Beliciaa Towers" in result["operator"]["address"]
    assert "Tamil Nadu" in result["operator"]["address"]
    assert "Aurobindo Marg" not in result["operator"]["address"]
    assert "New Delhi" not in result["operator"]["address"]

    # 3. Customer / GoFloaters Details
    assert result["gofloaters"]["name"] == "SMBSURE BUSINESS SOLUTIONS PRIVATE LIMITED"
    assert result["gofloaters"]["gstin"] == "33AAYCS6808H1ZT"
    assert "Millenia Business Park" in result["gofloaters"]["address"]

    # 4. Tax
    assert result["tax"]["taxable_amount"] == 1800
    assert result["tax"]["cgst"] == 162
    assert result["tax"]["sgst"] == 162
    assert result["tax"]["total"] == 2124

    # 5. Validation Status
    assert result["validation"]["status"] == "valid"
    assert len(result["validation"]["errors"]) == 0
