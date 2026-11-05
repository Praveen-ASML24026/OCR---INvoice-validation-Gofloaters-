"""
Unit and integration tests for GoFloaters validation Rules 1 through 5,
specifically covering Cases 1 through 10.
"""
from invoice_parser.validators import (
    validate_document,
    validate_rule_1_gstin_availability,
    validate_rule_2_gstin_vs_address_state,
    determine_rule_3_transaction_type,
    validate_rule_4_tax_type,
    validate_rule_5_place_of_supply,
)

# Test GSTIN constants across various Indian states
GF_TN_GSTIN = "33AAYCS6808H1ZT"       # 33: Tamil Nadu
GF_KA_GSTIN = "29AAYCS6808H1ZI"       # 29: Karnataka
GF_MH_GSTIN = "27AAYCS6808H1ZM"       # 27: Maharashtra
GF_HR_GSTIN = "06AAYCS6808H1ZQ"       # 06: Haryana
GF_KL_GSTIN = "32AAYCS6808H1ZV"       # 32: Kerala (Unexpected GoFloaters state)

OP_KA_GSTIN = "29AADCG7059H1ZA"       # 29: Karnataka
OP_TN_GSTIN = "33AAECI3042B1ZB"       # 33: Tamil Nadu
OP_UP_GSTIN = "09AFMPA4361B1ZT"       # 09: Uttar Pradesh
OP_DL_GSTIN = "07AAGCN6967N1ZM"       # 07: Delhi
OP_KL_GSTIN = "32EEKPS4329G1ZC"       # 32: Kerala
OP_GJ_GSTIN = "24AAACG1234A1ZK"       # 24: Gujarat
OP_INV_GSTIN = "99INVALID1234Z1"      # 99: Invalid state code


# ===========================================================================
# Case 1 — Same-state valid
# ===========================================================================
def test_case_1_same_state_valid():
    """
    Operator: Karnataka
    GoFloaters: Karnataka
    Tax: CGST + SGST
    Expected: VALID
    """
    doc = {
        "operator": {
            "name": "Operator KA",
            "gstin": OP_KA_GSTIN,
            "address": "MG Road, Bangalore, Karnataka 560001",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_KA_GSTIN,
            "address": "Indiranagar, Bangalore, Karnataka 560038",
        },
        "tax": {"cgst": 90.0, "sgst": 90.0, "igst": None, "total": 1180.0},
        "invoice": {"place_of_supply": "Karnataka (29)"},
    }
    result = validate_document(doc)
    assert result["valid"] is True
    assert result["status"] == "valid"
    assert result["transaction_type"] == "INTRA_STATE"
    assert len(result["errors"]) == 0


# ===========================================================================
# Case 2 — Same-state with IGST
# ===========================================================================
def test_case_2_same_state_with_igst_invalid():
    """
    Operator: Karnataka
    GoFloaters: Karnataka
    Tax: IGST
    Expected: INVALID — Incorrect Tax Type
    """
    doc = {
        "operator": {
            "name": "Operator KA",
            "gstin": OP_KA_GSTIN,
            "address": "MG Road, Bangalore, Karnataka 560001",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_KA_GSTIN,
            "address": "Indiranagar, Bangalore, Karnataka 560038",
        },
        "tax": {"cgst": None, "sgst": None, "igst": 180.0, "total": 1180.0},
        "invoice": {"place_of_supply": "Karnataka (29)"},
    }
    result = validate_document(doc)
    assert result["valid"] is False
    assert result["status"] == "invalid"
    assert result["transaction_type"] == "INTRA_STATE"
    assert any(e["code"] == "INCORRECT_TAX_TYPE" for e in result["errors"])
    assert any("IGST charged for intra-state transaction" in e["message"] for e in result["errors"])


# ===========================================================================
# Case 3 — Different-state valid
# ===========================================================================
def test_case_3_different_state_valid():
    """
    Operator: Karnataka
    GoFloaters: Tamil Nadu
    Tax: IGST
    Expected: VALID
    """
    doc = {
        "operator": {
            "name": "Operator KA",
            "gstin": OP_KA_GSTIN,
            "address": "MG Road, Bangalore, Karnataka 560001",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_TN_GSTIN,
            "address": "Guindy, Chennai, Tamil Nadu 600032",
        },
        "tax": {"cgst": None, "sgst": None, "igst": 180.0, "total": 1180.0},
        "invoice": {"place_of_supply": "Tamil Nadu (33)"},
    }
    result = validate_document(doc)
    assert result["valid"] is True
    assert result["status"] == "valid"
    assert result["transaction_type"] == "INTER_STATE"
    assert len(result["errors"]) == 0


# ===========================================================================
# Case 4 — Different-state with CGST + SGST
# ===========================================================================
def test_case_4_different_state_with_cgst_sgst_invalid():
    """
    Operator: Karnataka
    GoFloaters: Tamil Nadu
    Tax: CGST + SGST
    Expected: INVALID — Incorrect Tax Type
    """
    doc = {
        "operator": {
            "name": "Operator KA",
            "gstin": OP_KA_GSTIN,
            "address": "MG Road, Bangalore, Karnataka 560001",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_TN_GSTIN,
            "address": "Guindy, Chennai, Tamil Nadu 600032",
        },
        "tax": {"cgst": 90.0, "sgst": 90.0, "igst": None, "total": 1180.0},
        "invoice": {"place_of_supply": "Tamil Nadu (33)"},
    }
    result = validate_document(doc)
    assert result["valid"] is False
    assert result["status"] == "invalid"
    assert result["transaction_type"] == "INTER_STATE"
    assert any(e["code"] == "INCORRECT_TAX_TYPE" for e in result["errors"])
    assert any("CGST/SGST charged for inter-state transaction" in e["message"] for e in result["errors"])


# ===========================================================================
# Case 5 — Operator from another Indian state (e.g. Kerala, Gujarat)
# ===========================================================================
def test_case_5_operator_from_another_indian_state_valid():
    """
    Operator: Kerala (or Gujarat)
    Operator GSTIN: Kerala GSTIN
    GoFloaters: Tamil Nadu
    Tax: IGST
    Expected: VALID
    Crucial: Must NOT be rejected merely because Kerala is not a GoFloaters state.
    """
    doc = {
        "operator": {
            "name": "Kochi Spaces",
            "gstin": OP_KL_GSTIN,
            "address": "Marine Drive, Kochi, Kerala 682031",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_TN_GSTIN,
            "address": "Guindy, Chennai, Tamil Nadu 600032",
        },
        "tax": {"cgst": None, "sgst": None, "igst": 180.0, "total": 1180.0},
        "invoice": {"place_of_supply": "Tamil Nadu (33)"},
    }
    result = validate_document(doc)
    assert result["valid"] is True
    assert result["status"] == "valid"
    assert result["transaction_type"] == "INTER_STATE"
    assert len(result["errors"]) == 0


# ===========================================================================
# Case 6 — Operator GSTIN/address mismatch
# ===========================================================================
def test_case_6_operator_gstin_address_mismatch():
    """
    Operator: Address = Kerala, Operator GSTIN = Karnataka (29)
    Expected: INVALID — Operator GSTIN State Mismatch
    """
    doc = {
        "operator": {
            "name": "Kochi Spaces",
            "gstin": OP_KA_GSTIN,  # 29 Karnataka
            "address": "Marine Drive, Kochi, Kerala 682031",  # 32 Kerala
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_TN_GSTIN,
            "address": "Guindy, Chennai, Tamil Nadu 600032",
        },
        "tax": {"cgst": None, "sgst": None, "igst": 180.0, "total": 1180.0},
    }
    result = validate_document(doc)
    assert result["valid"] is False
    assert result["status"] == "invalid"
    assert any(e["code"] == "OPERATOR_GSTIN_STATE_MISMATCH" for e in result["errors"])
    mismatch_err = next(e for e in result["errors"] if e["code"] == "OPERATOR_GSTIN_STATE_MISMATCH")
    assert mismatch_err["details"]["address_state"] == "Kerala"
    assert mismatch_err["details"]["gstin_state"] == "Karnataka"


# ===========================================================================
# Case 7 — GoFloaters Delhi exception
# ===========================================================================
def test_case_7_gofloaters_delhi_exception():
    """
    GoFloaters: Address = Delhi, GoFloaters GSTIN = Missing
    Operator: Delhi (07)
    Tax: CGST + SGST
    Expected: Do NOT return GSTIN Missing for GoFloaters.
    """
    doc = {
        "operator": {
            "name": "Delhi Workstation",
            "gstin": OP_DL_GSTIN,
            "address": "Connaught Place, New Delhi, Delhi 110001",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": None,  # Missing, but Delhi is exempt
            "address": "Barakhamba Road, New Delhi, Delhi 110001",
        },
        "tax": {"cgst": 90.0, "sgst": 90.0, "igst": None, "total": 1180.0},
        "invoice": {"place_of_supply": "Delhi (07)"},
    }
    result = validate_document(doc)
    assert not any(e["code"] == "GSTIN_MISSING_GOFLOATERS" for e in result["errors"])
    assert not any("GoFloaters GSTIN is missing" in e["message"] for e in result["errors"])


# ===========================================================================
# Case 8 — GoFloaters Telangana exception
# ===========================================================================
def test_case_8_gofloaters_telangana_exception():
    """
    GoFloaters: Address = Telangana, GoFloaters GSTIN = Missing
    Operator: Telangana (36)
    Tax: CGST + SGST
    Expected: Do NOT return GSTIN Missing for GoFloaters.
    """
    doc = {
        "operator": {
            "name": "Hyderabad Cowork",
            "gstin": "36AAACS1234A1Z5",
            "address": "Hitec City, Hyderabad, Telangana 500081",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": None,  # Missing, but Telangana is exempt
            "address": "Madhapur, Hyderabad, Telangana 500081",
        },
        "tax": {"cgst": 90.0, "sgst": 90.0, "igst": None, "total": 1180.0},
        "invoice": {"place_of_supply": "Telangana (36)"},
    }
    result = validate_document(doc)
    assert not any(e["code"] == "GSTIN_MISSING_GOFLOATERS" for e in result["errors"])
    assert not any("GoFloaters GSTIN is missing" in e["message"] for e in result["errors"])


# ===========================================================================
# Case 9 — Unexpected GoFloaters GST state
# ===========================================================================
def test_case_9_unexpected_gofloaters_gst_state():
    """
    GoFloaters has a GSTIN from a state not in {TN, KA, MH, HR} (e.g. Kerala 32).
    Expected: Flag as 'GoFloaters GST Registration State Unexpected',
    while still performing normal GSTIN-state vs address-state validation.
    """
    doc = {
        "operator": {
            "name": "Kochi Spaces",
            "gstin": OP_KL_GSTIN,
            "address": "Marine Drive, Kochi, Kerala 682031",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_KL_GSTIN,  # Valid Kerala GSTIN, but unexpected for GoFloaters
            "address": "Marine Drive, Kochi, Kerala 682031",
        },
        "tax": {"cgst": 90.0, "sgst": 90.0, "igst": None, "total": 1180.0},
        "invoice": {"place_of_supply": "Kerala (32)"},
    }
    result = validate_document(doc)
    assert any(e["code"] == "GOFLOATERS_GST_REGISTRATION_STATE_UNEXPECTED" for e in result["errors"])
    # But GSTIN state (Kerala) == Address state (Kerala), so NO state mismatch error!
    assert not any(e["code"] == "GOFLOATERS_GSTIN_STATE_MISMATCH" for e in result["errors"])


# ===========================================================================
# Case 10 — Invalid GSTIN state code
# ===========================================================================
def test_case_10_invalid_gstin_state_code():
    """
    GSTIN contains an invalid/unrecognized Indian state code (e.g. '99').
    Expected: INVALID — Invalid GSTIN State Code
    """
    doc = {
        "operator": {
            "name": "Fake Vendor",
            "gstin": OP_INV_GSTIN,  # 99 is invalid Indian state code
            "address": "Bangalore, Karnataka 560001",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_KA_GSTIN,
            "address": "Bangalore, Karnataka 560038",
        },
        "tax": {"cgst": 90.0, "sgst": 90.0, "igst": None, "total": 1180.0},
    }
    result = validate_document(doc)
    assert result["valid"] is False
    assert result["status"] == "invalid"
    assert any(e["code"] == "INVALID_GSTIN_STATE_CODE" for e in result["errors"])
    invalid_err = next(e for e in result["errors"] if e["code"] == "INVALID_GSTIN_STATE_CODE")
    assert invalid_err["details"]["state_code"] == "99"


# ===========================================================================
# Place of Supply & Multi-Rule Accumulation Tests
# ===========================================================================
def test_rule_5_intra_state_pos_mismatch():
    """
    Operator in Karnataka, GoFloaters in Karnataka (INTRA_STATE).
    Place of Supply is Tamil Nadu (33).
    Expected: PLACE_OF_SUPPLY_MISMATCH error.
    """
    doc = {
        "operator": {
            "name": "Operator KA",
            "gstin": OP_KA_GSTIN,
            "address": "MG Road, Bangalore, Karnataka 560001",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_KA_GSTIN,
            "address": "Indiranagar, Bangalore, Karnataka 560038",
        },
        "tax": {"cgst": 90.0, "sgst": 90.0, "igst": None, "total": 1180.0},
        "invoice": {"place_of_supply": "Tamil Nadu (33)"},
    }
    result = validate_document(doc)
    assert result["valid"] is False
    assert any(e["code"] == "PLACE_OF_SUPPLY_MISMATCH" for e in result["errors"])


def test_rule_5_inter_state_third_party_pos_mismatch():
    """
    Operator in Karnataka, GoFloaters in Tamil Nadu (INTER_STATE).
    Place of Supply is Maharashtra (27) — contradicts both parties!
    Expected: PLACE_OF_SUPPLY_MISMATCH error.
    """
    doc = {
        "operator": {
            "name": "Operator KA",
            "gstin": OP_KA_GSTIN,
            "address": "MG Road, Bangalore, Karnataka 560001",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_TN_GSTIN,
            "address": "Guindy, Chennai, Tamil Nadu 600032",
        },
        "tax": {"cgst": None, "sgst": None, "igst": 180.0, "total": 1180.0},
        "invoice": {"place_of_supply": "Maharashtra (27)"},
    }
    result = validate_document(doc)
    assert result["valid"] is False
    assert any(e["code"] == "PLACE_OF_SUPPLY_MISMATCH" for e in result["errors"])


def test_multi_rule_accumulation_does_not_short_circuit():
    """
    Verify that when multiple rules fail, all errors are returned instead of stopping at the first error.
    Here:
    - Rule 1 fails: Operator GSTIN is missing (GSTIN Missing — Operator).
    - Rule 4 fails: Intra-state transaction (KA & KA), but IGST was charged.
    - Rule 5 fails: Place of supply is Tamil Nadu (33) for intra-state KA.
    """
    doc = {
        "operator": {
            "name": "Operator KA",
            "gstin": None,  # Missing -> Rule 1 error
            "address": "MG Road, Bangalore, Karnataka 560001",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_KA_GSTIN,
            "address": "Indiranagar, Bangalore, Karnataka 560038",
        },
        "tax": {"cgst": 90.0, "sgst": 90.0, "igst": None, "total": 1180.0},  # Tax error -> Rule 4 (CGST+SGST charged for inter-state)
        "invoice": {"place_of_supply": "Tamil Nadu (33)"},  # POS error -> Rule 5
    }
    result = validate_document(doc)
    assert result["valid"] is False
    error_codes = [e["code"] for e in result["errors"]]
    assert "GSTIN_MISSING_OPERATOR" in error_codes
    assert "INCORRECT_TAX_TYPE" in error_codes
    assert "PLACE_OF_SUPPLY_MISMATCH" in error_codes
    assert len(result["errors"]) >= 3


def test_validation_result_structure():
    """
    Verify the structured validation result format adheres to user requirements:
    {
        "valid": bool,
        "errors": [
            {
                "rule": str,
                "code": str,
                "message": str,
                "details": dict
            }
        ]
    }
    """
    doc = {
        "operator": {
            "name": "Operator KL",
            "gstin": OP_KA_GSTIN,  # 29 KA
            "address": "Marine Drive, Kochi, Kerala 682031",  # 32 KL
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_TN_GSTIN,
            "address": "Guindy, Chennai, Tamil Nadu 600032",
        },
        "tax": {"cgst": None, "sgst": None, "igst": 180.0, "total": 1180.0},
    }
    result = validate_document(doc)
    assert "valid" in result
    assert "errors" in result
    assert isinstance(result["errors"], list)
    for err in result["errors"]:
        assert "rule" in err
        assert "code" in err
        assert "message" in err
        assert "details" in err
        assert isinstance(err["details"], dict)


def test_lumped_gst_instead_of_cgst_and_sgst_flagged_as_error():
    """
    When an intra-state invoice mentions tax generically as GST rather than explicit CGST and SGST,
    an explicit error must be thrown: 'They mentioned the tax as GST instead of CGST and SGST'.
    """
    doc = {
        "operator": {
            "name": "Operator TN",
            "gstin": OP_TN_GSTIN,
            "address": "Madurai, Tamil Nadu 625016",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_TN_GSTIN,
            "address": "Chennai, Tamil Nadu 600096",
        },
        "tax": {"taxable_amount": 4000.0, "cgst": None, "sgst": None, "igst": None, "total": 4720.0},
        "evidence": {"unlabelled_gst_total": 720.0},
        "missing_after_extraction": ["tax.cgst/sgst/igst"],
    }
    result = validate_document(doc)
    assert result["valid"] is False
    assert result["status"] == "invalid"
    assert any(e["code"] == "INCORRECT_TAX_TYPE" for e in result["errors"])
    assert any("They mentioned the tax as GST instead of CGST and SGST" in e["message"] for e in result["errors"])
    assert any("They mentioned the tax as GST instead of CSGT AND SGST" in e["message"] for e in result["errors"])


def test_lumped_gst_mention_flagged_as_error_even_without_numeric_amount():
    """
    When an invoice mentions GST as the tax format, even if exact numeric amount wasn't isolated,
    an intra-state transaction must still flag 'They mentioned the tax as GST instead of CGST and SGST'.
    """
    doc = {
        "operator": {
            "name": "Operator KA",
            "gstin": "29AABCE7586M1ZV",
            "address": "Bangalore, Karnataka 560016",
        },
        "gofloaters": {
            "name": "SMBSure",
            "gstin": "29AAYCS6808H1ZI",
            "address": "Bengaluru, Karnataka 560048",
        },
        "tax": {"taxable_amount": 1500.0, "cgst": None, "sgst": None, "igst": None, "total": 1770.0},
        "evidence": {"has_lumped_gst_mention": True},
        "missing_after_extraction": ["tax.cgst/sgst/igst"],
    }
    result = validate_document(doc)
    assert result["valid"] is False
    assert result["status"] == "invalid"
    assert any(e["code"] == "INCORRECT_TAX_TYPE" for e in result["errors"])
    assert any("They mentioned the tax as GST instead of CGST and SGST" in e["message"] for e in result["errors"])


def test_lumped_gst_inter_state_flagged_as_error():
    """
    When an inter-state invoice mentions tax generically as GST rather than explicit IGST,
    an explicit error must be thrown: 'They mentioned the tax as GST instead of IGST'.
    """
    doc = {
        "operator": {
            "name": "Operator DL",
            "gstin": "07AAAAA0000A1Z5",
            "address": "Connaught Place, New Delhi 110001",
        },
        "gofloaters": {
            "name": "GoFloaters",
            "gstin": GF_TN_GSTIN,
            "address": "Chennai, Tamil Nadu 600096",
        },
        "tax": {"taxable_amount": 2000.0, "cgst": None, "sgst": None, "igst": None, "total": 2360.0},
        "evidence": {"unlabelled_gst_total": 360.0},
        "missing_after_extraction": ["tax.cgst/sgst/igst"],
    }
    result = validate_document(doc)
    assert result["valid"] is False
    assert result["status"] == "invalid"
    assert any(e["code"] == "INCORRECT_TAX_TYPE" for e in result["errors"])
    assert any("They mentioned the tax as GST instead of IGST" in e["message"] for e in result["errors"])


