from invoice_parser.validators import validate_document

GF, OP_SAME, OP_OTHER = "33AAYCS6808H1ZT", "33AAECI3042B1ZB", "32EEKPS4329G1ZC"


def doc(op, **tax):
    return {"operator": {"gstin": op, "state": None}, "gofloaters": {"gstin": GF, "state": None},
            "tax": tax, "missing_after_extraction": []}


def test_valid_same_state():
    d = doc(OP_SAME, cgst=9, sgst=9)
    d["operator"]["state"] = d["gofloaters"]["state"] = "Tamil Nadu"
    d["operator"]["address"] = d["gofloaters"]["address"] = "Guindy, Chennai, Tamil Nadu 600032 India"
    assert validate_document(d)["status"] == "valid"


def test_missing_data_is_incomplete_not_valid():
    d = {"operator": {}, "gofloaters": {"gstin": GF}, "tax": {}, "missing_after_extraction": ["tax.total"]}
    r = validate_document(d)
    assert r["status"] == "invalid" and not r["valid"]      # REQ4: operator GSTIN missing
    d["operator"] = {"gstin": OP_SAME, "state": "Tamil Nadu"}
    d["gofloaters"]["state"] = "Tamil Nadu"
    d["tax"] = {"cgst": 9, "sgst": 9}
    r = validate_document(d)
    assert r["status"] == "incomplete" and not r["valid"]


def test_interstate_with_igst_is_valid_for_any_state():
    # Delhi (07), Telangana (36), Kerala (32) operators billing the Tamil Nadu GSTIN with IGST
    for op in ("07AAGCN6967N1ZM", "36AAACS1234A1Z3", OP_OTHER):
        r = validate_document(doc(op, igst=18))
        assert not r["errors"], (op, r["errors"])


def test_interstate_with_cgst_sgst_flagged_by_req2_with_reason():
    d = doc("07AAGCN6967N1ZM", cgst=9, sgst=9)
    r = validate_document(d)
    assert r["status"] == "invalid" and not any("REQ1" in e for e in r["errors"])
    assert any(i["code"] == "REQ2" and "Delhi" in i["message"] and "IGST was not found" in i["message"]
               and "charged instead" in i["message"] for i in r["issues"])


def test_req2_unverified_when_no_tax_type_found():
    r = validate_document(doc(OP_SAME))
    assert not any(i["code"] == "REQ2" and i["type"] == "error" for i in r["issues"])
    assert any(i["code"] == "REQ2" and i["type"] == "unverified" for i in r["issues"])


def test_missing_gstin_reason_names_the_party():
    d = {"operator": {"state": "Kerala"}, "gofloaters": {"gstin": GF, "state": "Tamil Nadu"},
         "tax": {}, "missing_after_extraction": ["tax.total"]}
    r = validate_document(d)
    text = " ".join(i["message"] for i in r["issues"])
    assert "Operator GSTIN is missing" in text and "total amount could not be found" in text


def _with_addr(d, op_addr, gf_addr, pos=None):
    d["operator"]["address"], d["gofloaters"]["address"] = op_addr, gf_addr
    d["invoice"] = {"place_of_supply": pos}
    return d


def test_req3_unverified_when_addresses_missing():
    r = validate_document(doc(OP_SAME, cgst=9, sgst=9))
    assert any(i["code"] == "REQ3" and i["type"] == "unverified" for i in r["issues"])


def test_req3_tax_structure_vs_addresses_with_pos_as_support():
    d = _with_addr(doc(OP_OTHER, cgst=9, sgst=9), "Kochi, Kerala 682001 India",
                   "Chennai 600096 Tamil Nadu India", pos="Tamil Nadu (33)")
    msgs = [i["message"] for i in validate_document(d)["issues"] if i["code"] == "REQ3"]
    assert any("IGST is expected" in m and "CGST + SGST was charged" in m and "Supporting evidence" in m for m in msgs)


def test_req3_address_conflicts_with_gstin_state():
    d = _with_addr(doc(OP_SAME, cgst=9, sgst=9), "Kochi, Kerala 682001 India", "Chennai 600096 Tamil Nadu India")
    assert any(e.startswith("REQ1") and "Operator address is in Kerala" in e for e in validate_document(d)["errors"])


def test_req3_passes_for_consistent_interstate():
    d = _with_addr(doc(OP_OTHER, igst=18), "Kochi, Kerala 682001 India", "Chennai 600096 Tamil Nadu India")
    assert not any(i["code"] == "REQ3" for i in validate_document(d)["issues"])


def test_math_mismatch_flags_invalid():
    # 12999 vs 11800 (taxable 10000 + 1800 tax != 12999)
    d = doc(OP_SAME, taxable_amount=10000.0, cgst=900.0, sgst=900.0, total=12999.0)
    d["operator"]["state"] = d["gofloaters"]["state"] = "Tamil Nadu"
    d["operator"]["address"] = d["gofloaters"]["address"] = "Chennai, Tamil Nadu 600032"
    r = validate_document(d)
    assert r["status"] == "invalid"
    assert any("TAX_MATHEMATICAL_MISMATCH" in str(e["code"]) for e in r["errors"])


def test_invalid_gstin_checksum_flags_invalid():
    # 33AAECI3042B1ZC has wrong check digit (valid is B)
    d = doc("33AAECI3042B1ZC", cgst=90.0, sgst=90.0, total=1180.0, taxable_amount=1000.0)
    d["operator"]["state"] = d["gofloaters"]["state"] = "Tamil Nadu"
    d["operator"]["address"] = d["gofloaters"]["address"] = "Chennai, Tamil Nadu 600032"
    r = validate_document(d)
    assert r["status"] == "invalid"
    assert any("INVALID_OPERATOR_GSTIN_CHECKSUM" in str(e["code"]) for e in r["errors"])


def test_future_invoice_date_flags_invalid():
    d = doc(OP_SAME, cgst=90.0, sgst=90.0, total=1180.0, taxable_amount=1000.0)
    d["operator"]["state"] = d["gofloaters"]["state"] = "Tamil Nadu"
    d["operator"]["address"] = d["gofloaters"]["address"] = "Chennai, Tamil Nadu 600032"
    d["invoice"] = {"date": "2031-10-09"}
    r = validate_document(d)
    assert r["status"] == "invalid"
    assert any("INVOICE_DATE_IN_FUTURE" in str(e["code"]) for e in r["errors"])
