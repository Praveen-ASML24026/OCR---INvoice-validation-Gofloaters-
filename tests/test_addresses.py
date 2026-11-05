from invoice_parser.fallback import apply_fallbacks

OP, GF = "33AAECI3042B1ZB", "33AAYCS6808H1ZT"


def blank(op_addr=None, gf_addr=None):
    return {"invoice": {"number": None, "date": None, "due_date": None},
            "operator": {"name": None, "address": op_addr, "state": None, "gstin": None},
            "gofloaters": {"name": None, "address": gf_addr, "state": None, "gstin": None},
            "tax": {"taxable_amount": 960, "cgst": None, "sgst": None, "igst": None, "total": None}}


def run(text, **kw):
    return apply_fallbacks(blank(**kw), {"markdown": text})


ITEM_TABLE = """| # | Item & Description | HSN/SAC | Qty | Rate | Amount |
| 1 | Conference room - Full day | 997212 | 1 | 960.00 | 960.00 |
Subject : Booking ID: GF0926099699"""


def test_address_present_is_found():
    d = run(f"""ISPROUT BUSINESS CENTRE PRIVATE LIMITED
5th Floor, Kocher Jade, SIDCO Estate, Guindy, Chennai Tamil Nadu 600032 India
GSTIN {OP}
| Billed To |
| SMBSure Business Solutions Pvt Ltd |
| 3rd Floor, ABC Towers, Anna Salai, Chennai, Tamil Nadu 600002 |
| GSTIN: {GF} |
{ITEM_TABLE}""")
    assert d["gofloaters"]["address"] == "3rd Floor, ABC Towers, Anna Salai, Chennai, Tamil Nadu 600002"
    assert d["operator"]["address"].endswith("600032 India")


def test_address_absent_never_returns_item_text():
    d = run(f"""Seller TK Business Arcade GSTIN {OP}
| Billed To |
| SMBSure Business Solutions Pvt Ltd |
| GSTIN: {GF} |
{ITEM_TABLE}""")
    assert d["gofloaters"]["address"] is None
    assert d["operator"]["address"] is None
    assert "gofloaters.address not found" in d["warnings"]


def test_name_and_address_in_one_cell():
    d = run(f"| SMBSure Business Solutions Pvt Ltd 3rd Floor, ABC Towers, Anna Salai, Chennai 600002 GSTIN {GF} |\nSeller {OP}")
    assert d["gofloaters"]["address"] == "3rd Floor, ABC Towers, Anna Salai, Chennai 600002"


def test_bank_details_are_not_an_address():
    d = run(f"Seller ACME GSTIN {OP}\nSMBSure GSTIN {GF}\nOur Bank Details:\nHDFC Bank, Jawahar Nagar, Ernakulam\nA/c No. 1234567890")
    assert d["operator"]["address"] is None


def test_table_layer_junk_is_discarded_and_double_address_cut():
    junk = "Subject : Booking ID: GF0926099699 # Item & Description HSN/SAC Qty Rate 1 Conference room 997212"
    assert run("SMBSure GSTIN " + GF, gf_addr=junk)["gofloaters"]["address"] is None
    two = "Guindy, Chennai Tamil Nadu 600032 India 9/1, Millenia park, Perungudi 600096 Tamil Nadu India"
    assert run("x", op_addr=two)["operator"]["address"] == "Guindy, Chennai Tamil Nadu 600032 India"


def test_operator_never_gets_billto_name_or_address():
    addr = "3rd Floor, ABC Towers, Anna Salai, Chennai, Tamil Nadu 600002"
    d = run(f"SMBSure Business Solutions Pvt Ltd\n{addr}\nGSTIN: {GF}\nSeller {OP}",
            op_addr=addr, gf_addr=addr)
    d2 = apply_fallbacks({**blank(op_addr=addr, gf_addr=addr),
                          "operator": {"name": "SMBSure Business Solutions Pvt Ltd", "address": addr, "state": None, "gstin": None}},
                         {"markdown": f"SMBSure Business Solutions Pvt Ltd\n{addr}\nGSTIN: {GF}\nSeller {OP}"})
    for x in (d, d2):
        assert x["operator"]["address"] is None
    assert d2["operator"]["name"] is None
    assert d2["gofloaters"]["address"] == addr
    assert "operator.name not found" in d2["warnings"]


def test_operator_rejects_subtotal_and_maps_wrapped_org_name():
    md = f"""1
Sub Total 960.00
CGST9 (9%) 86.40
SGST9 (9%) 86.40
Total ₹1,132.80
ISPROUT BUSINESS CENTRE
PRIVATE LIMITED
5th Floor, Kocher Jade, SIDCO Industrial Estate, Ambedkar Nagar, Guindy, Chennai Tamil Nadu 600032 India
GSTIN {OP}
| Billed To |
| SMBSure Business Solutions Pvt Ltd |
| GSTIN: {GF} |
{ITEM_TABLE}"""
    bad_doc = {
        **blank(),
        "operator": {"name": "Sub Total 960.00", "address": None, "state": None, "gstin": OP},
    }
    d = apply_fallbacks(bad_doc, {"markdown": md})
    assert "sub total" not in (d["operator"]["name"] or "").lower()
    assert d["operator"]["name"] == "ISPROUT BUSINESS CENTRE PRIVATE LIMITED"
    assert d["operator"]["address"].endswith("600032 India")


def test_multiline_wrapped_address_and_metadata_scrubbing():
    from invoice_parser.addresses import valid_address
    # Metadata only lines must never be valid addresses
    assert not valid_address("/UIN: State Name : West Bengal, Code : 19")
    assert not valid_address("State Name : Tamil Nadu, Code : 33")

    # Real multiline invoice test
    raw = """Tax Invoice
Ideapod Workstation LLP
Prasad House
16, Sudder Street, Kolkata
GSTIN/UIN: 19AAJFI9411J1Z0
State Name : West Bengal, Code : 19
Buyer (Bill to)
SMB SURE BUSINESS SOL. PVT. LTD.
A6, Industrial Estate, Mogappair West, Chennai
Chennai 600037
GSTIN/UIN: 33AAYCS6808H1ZT
State Name : Tamil Nadu, Code : 33
Invoice No IW/0474/26-27
"""
    d = apply_fallbacks(blank(), {"markdown": raw})
    assert d["operator"]["address"] == "Prasad House 16, Sudder Street, Kolkata"
    assert d["gofloaters"]["address"] == "A6, Industrial Estate, Mogappair West, Chennai 600037"


def test_operator_name_not_overwritten_by_bank_details():
    raw = """
NAME - AMIGO
YES BANK
ACCOUNT NUMBER 001661900002164
IFSC CODE : YESB0000016
Amigo
C25 Sector 8
Noida Uttar Pradesh 201301
India
GSTIN 09AFMPA4361B1ZT
TAX INVOICE
Bill To
SMBSure Business Solutions Pvt. Ltd.
A6, INDUSTRIAL ESTATE, Mogappair West
CHENNAI 600037 Tamil Nadu India
GSTIN 33AAYCS6808H1ZT
"""
    d = apply_fallbacks(blank(), {"markdown": raw})
    assert d["operator"]["name"] == "Amigo"
    assert d["operator"]["address"] == "C25 Sector 8 Noida Uttar Pradesh 201301 India"
    assert d["operator"]["gstin"] == "09AFMPA4361B1ZT"


def test_operator_name_wrapped_corporate_suffix():
    raw = """
LAVERO INFRA SERVICES PRIVATE
LIMITED

Work Studio Coworking
7th Floor, ROODRAKSH MALL, Bhangagarh, behind Smart Bazar
Guwahati Assam 781005 India
GSTIN 18AADCL7099L1ZR

Bill To
SMBSURE BUSINESS SOLUTIONS PRIVATE LIMITED
9/1, Millenia Business Park, Campus lA, MGR Main Road, Perungudi
Chennai 600096 Tamil Nadu India
GSTIN 33AAYCS6808H1ZT
"""
    from invoice_parser.semantic import build_semantic_candidates
    from invoice_parser.normalize import normalize_document
    ex = {
        "texts": [{"text": line} for line in raw.strip().splitlines() if line.strip()],
        "tables": [],
        "markdown": raw,
        "raw_text": raw,
    }
    sem = build_semantic_candidates(ex)
    doc = normalize_document(sem, ex)
    d = apply_fallbacks(doc, ex)
    assert d["operator"]["name"] == "LAVERO INFRA SERVICES PRIVATE LIMITED"


def test_clean_party_address_removes_party_name_and_billing_label():
    from invoice_parser.addresses import clean_party_address

    # Name at start of address
    addr1 = "Awfis Space Solutions Limited, Podium Floor, Ambience Mall, Gurugram, Haryana 122002"
    assert clean_party_address(addr1, "Awfis Space Solutions Limited") == "Podium Floor, Ambience Mall, Gurugram, Haryana 122002"

    # Label and name at start of address
    addr2 = "Billing From: Workzen Business Centre Private Limited 73C, 74C, 2nd Floor, Chennai - 600053"
    assert clean_party_address(addr2, "Workzen Business Centre Private Limited") == "73C, 74C, 2nd Floor, Chennai - 600053"

    # Label only
    addr3 = "Billed By: 44 VN Industrial Estate, Coimbatore - 641004"
    assert clean_party_address(addr3) == "44 VN Industrial Estate, Coimbatore - 641004"


def test_operator_name_and_address_strict_separation():
    raw = """
Billing From:
Awfis Space Solutions Limited
Podium Floor, Ambience Mall, NH-8
Gurugram, Haryana 122002
GSTIN 06AANCA1175G1Z0

Billed To:
SMBSURE BUSINESS SOLUTIONS PRIVATE LIMITED
9/1, Millenia Business Park, Campus 1A
Chennai 600096 Tamil Nadu
GSTIN 33AAYCS6808H1ZT
"""
    from invoice_parser.semantic import build_semantic_candidates
    from invoice_parser.normalize import normalize_document
    ex = {
        "texts": [{"text": line} for line in raw.strip().splitlines() if line.strip()],
        "tables": [],
        "markdown": raw,
        "raw_text": raw,
    }
    sem = build_semantic_candidates(ex)
    doc = normalize_document(sem, ex)
    d = apply_fallbacks(doc, ex)
    assert d["operator"]["name"] == "Awfis Space Solutions Limited"
    assert not d["operator"]["address"].startswith("Awfis Space Solutions")
    assert not d["operator"]["address"].lower().startswith("billing from")
    assert "Podium Floor" in d["operator"]["address"]



