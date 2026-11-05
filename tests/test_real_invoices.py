"""
Regression tests built from REAL Docling output (files saved with `--debug`).
Add one fixture + one test per invoice you fix:  copy <invoice>.debug.md into tests/fixtures/.
"""
from pathlib import Path

import pytest
from debug_loader import load_debug

from invoice_parser.fallback import apply_fallbacks
from invoice_parser.normalize import normalize_document
from invoice_parser.semantic import build_semantic_candidates
from invoice_parser.validators import validate_document

FIXTURES = Path(__file__).parent / "fixtures"


def run(name):
    ex = load_debug(FIXTURES / name)
    doc = normalize_document(build_semantic_candidates(ex), ex)
    apply_fallbacks(doc, ex)
    doc["validation"] = validate_document(doc)
    return doc


ALL = sorted(p.name for p in FIXTURES.glob("*.debug.md"))


@pytest.mark.parametrize("name", ALL)
def test_operator_never_carries_billto_data(name):
    d = run(name)
    op, gf = d["operator"], d["gofloaters"]
    assert "smbsure" not in (op["name"] or "").lower() and "gofloaters" not in (op["name"] or "").lower()
    assert op["address"] is None or op["address"] != gf["address"]
    assert op["gstin"] is None or op["gstin"] != gf["gstin"]


def test_003_proforma_operator_on_top_billto_beside():
    d = run("003_proforma.debug.md")
    assert d["operator"] == {"name": "Dr.C.V.S Ratnam & Associates",           # &amp; unescaped
                             "address": "Golden Square, # 579, 32nd D Cross 10 th Main Jayanagar 4 th Block Bangalore - 560027",
                             "state": "Karnataka", "gstin": None}              # proforma: no operator GSTIN printed
    assert d["gofloaters"]["address"] == "12th Floor, Crescent 3, Prestige Shantiniketan Whitefield, Bengaluru Karnataka 560048"
    assert d["gofloaters"]["gstin"] == "29AAYCS6808H1ZI"
    assert d["invoice"]["number"] == "003" and d["invoice"]["date"] == "2026-09-02"
    assert (d["tax"]["cgst"], d["tax"]["sgst"], d["tax"]["igst"]) == (None, None, None)   # only an unlabelled "GST" row
    assert d["tax"]["total"] == 1130 and len(d["line_items"]) == 1
    assert any("REQ4" in e for e in d["validation"]["errors"])


def test_ckbg_487_billto_on_top_operator_at_bottom():
    d = run("ckbg_487.debug.md")
    assert d["operator"]["name"] == "CoKarma" and d["operator"]["state"] == "Telangana"
    assert d["operator"]["address"].endswith("Hyderabad Telangana - 500016")
    assert d["gofloaters"]["address"] == "A-6 Industrial Estate, Mogappair West, Chennai, Tamil Nadu, 600037"
    assert d["gofloaters"]["gstin"] == "33AAYCS6808H1ZT"
    assert d["invoice"]["date"] == "2026-09-04" and d["invoice"]["place_of_supply"] == "36 - Telangana"
    assert d["invoice"]["number"] is None            # garbled by the PDF font (U+FFFD): null, never a date
    assert d["tax"]["cgst"] is None                  # label garbled ("C\ufffdST"): not guessed


def test_nukleus_0801_real_docling_text():
    d = run("nukleus_0801.debug.md")
    assert d["operator"]["gstin"] == "07AAGCN6967N1ZM" and d["operator"]["state"] == "Delhi"
    assert d["operator"]["address"].endswith("New Delhi Delhi 110001 India")
    assert d["gofloaters"]["address"] == ("Millenia Business Park Campus -1A, 2nd Floor, 9/1A MGR Main Road, "
                                          "Kodandarama Nagar, Perungudi, Chennai 600096 Tamil Nadu India")
    assert d["tax"] == {"taxable_amount": 720, "cgst": 64.8, "sgst": 64.8, "igst": None, "total": 849.6}
    assert d["invoice"]["place_of_supply"] == "Delhi (07)"
    assert d["invoice"]["number"] is None            # the number is inside an image, not in Docling's text
    codes = {i["code"] for i in d["validation"]["issues"] if i["type"] == "error"}
    assert codes == set()                            # Delhi operator, Delhi POS -> CGST+SGST is valid
