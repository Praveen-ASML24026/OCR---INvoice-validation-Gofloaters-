from invoice_parser.fallback import (
    apply_fallbacks,
    extract_digital_line_items,
    extract_stacked_summary,
)


def blank():
    return {"invoice": {"number": None, "date": None, "due_date": None},
            "operator": {"name": None, "address": None, "state": None, "gstin": None},
            "gofloaters": {"name": None, "address": None, "state": None, "gstin": None},
            "tax": {"taxable_amount": 960, "cgst": None, "sgst": None, "igst": None, "total": None}}


def run(text):
    return apply_fallbacks(blank(), {"markdown": text})


def test_invoice_number_not_read_as_date():
    d = run("| Invoice No: CHN/26-27/0499 | Date: 04/09/2026 |")
    assert d["invoice"]["number"] == "CHN/26-27/0499"
    assert d["invoice"]["date"] == "2026-09-04"


def test_labelled_cgst_sgst():
    d = run("Seller 33AAECI3042B1ZB\nSMBSure 33AAYCS6808H1ZT\nCGST 9% : 86.40\nSGST 9% : 86.40\nGrand Total 1,132.80")
    assert (d["tax"]["cgst"], d["tax"]["sgst"], d["tax"]["total"]) == (86.4, 86.4, 1132.8)


def test_unlabelled_amounts_never_fill_tax_type():
    d = run("Seller 33AAECI3042B1ZB\nSMBSure 33AAYCS6808H1ZT\n| 86.40 | 86.40 |\nAmount 1132.80")
    assert d["tax"]["cgst"] is None and d["tax"]["sgst"] is None and d["tax"]["igst"] is None
    assert any("no explicit CGST" in w for w in d["warnings"])


def test_single_unlabelled_gst_line_is_not_split_or_guessed():
    d = run("Seller 29AAACS1234A1ZX\nSMBSure 33AAYCS6808H1ZT\nGST @18% 172.80")
    assert d["tax"]["igst"] is None and d["tax"]["cgst"] is None and d["tax"]["sgst"] is None
    assert d["evidence"]["unlabelled_gst_total"] == 172.8


def test_explicit_igst_label_is_read():
    d = run("Seller 07AAGCN6967N1ZM\nSMBSure 33AAYCS6808H1ZT\nIGST 18% : 172.80")
    assert d["tax"]["igst"] == 172.8


def test_company_name_detection_rejects_headers_and_fragments():
    from invoice_parser.normalize import looks_like_organization as org
    for bad in ("Item & Description", "PRIVATE LIMITED", "LIMITED", "Reference No. & Date.",
                "Corp. Office.-183/1, 3rd Floor, ABC Road", "Terms & Conditions"):
        assert not org(bad), bad
    for good in ("NUKLEUS OFFICE SOLUTIONS LIMITED", "Dr.C.V.S Ratnam & Associates", "Sector 7 Workspaces Pvt Ltd",
                 "Ofis Spaces Private Limited", "LIFTX INDIA VENTURES LLP"):
        assert org(good), good


def test_ocr_gstin_repair():
    from invoice_parser.normalize import repair_ocr_gstin, find_gstin
    # O -> 0 in state code
    assert repair_ocr_gstin("O9AFMPA4361B1ZT") == "09AFMPA4361B1ZT"
    # O -> 0 in PAN numbers
    assert repair_ocr_gstin("33AAYCS68O8H1ZT") == "33AAYCS6808H1ZT"
    # I -> 1, Z -> 2 in state codes
    assert repair_ocr_gstin("Z7AALFG9603L1ZX") == "27AALFG9603L1ZX"
    # find_gstin directly handles OCR corruptions
    assert find_gstin("GSTIN: O9AFMPA4361B1ZT") == "09AFMPA4361B1ZT"
    assert find_gstin("Supplier GSTIN 33AAYCS68O8H1ZT") == "33AAYCS6808H1ZT"


def test_expanded_invoice_labels():
    from invoice_parser.fallback import INV_NO_LABEL
    for label in ("Voucher No:", "Voucher Number:", "Doc No:", "Document No:", "Bill No:", "PI No:", "Proforma No:"):
        assert INV_NO_LABEL.search(label), f"Failed for {label}"


def test_clean_party_name_prefixes():
    from invoice_parser.normalize import clean_party_name
    assert clean_party_name("Name - GALA PROJECTS LLP CONNEKT-MH") == "GALA PROJECTS LLP CONNEKT-MH"
    assert clean_party_name("PAYMENT DETAILS Name - GALA PROJECTS LLP CONNEKT-MH") == "GALA PROJECTS LLP CONNEKT-MH"
    assert clean_party_name("Name: GALA PROJECTS LLP") == "GALA PROJECTS LLP"
    assert clean_party_name("M/s. ABC Solutions Pvt Ltd") == "ABC Solutions Pvt Ltd"
    assert clean_party_name("Operator - Golden Square") == "Golden Square"
    assert clean_party_name("Supplier: WorkDen Coworking") == "WorkDen Coworking"
    assert clean_party_name("Smbsure Business Solutions Private Limited") == "Smbsure Business Solutions Private Limited"


def test_line_item_table_stop_boundaries():
    from invoice_parser.fallback import extract_digital_line_items
    text = """
Item & Description
Meeting Room (SAC : 997212)
1 2120.00 2120.00
Total 2120.00
CGST(9%) 190.80
SGST(9%) 190.80
Net Amount 2502.00
"""
    items = extract_digital_line_items(text)
    assert len(items) == 1
    assert items[0]["description"] == "Meeting Room (SAC : 997212)"
    assert items[0]["hsn_sac"] == "997212"
    assert items[0]["amount"] == 2120.00
    assert items[0]["quantity"] == 1


def test_clean_party_name_document_titles():
    from invoice_parser.normalize import clean_party_name
    assert clean_party_name("SALES BILL Skyon Office Spaces LLP") == "Skyon Office Spaces LLP"
    assert clean_party_name("TAX INVOICE - CoKarma Spaces Pvt Ltd") == "CoKarma Spaces Pvt Ltd"
    assert clean_party_name("ORIGINAL FOR RECIPIENT Innov8 Coworking Private Limited") == "Innov8 Coworking Private Limited"


def test_choose_operator_does_not_prepend_sales_bill():
    from invoice_parser.normalize import choose_operator
    extracted = {
        "texts": [
            {"text": "Tax Invoice", "label": "title"},
            {"text": "SALES BILL", "label": "text"},
            {"text": "Skyon Office Spaces LLP", "label": "text"},
            {"text": "17/16A, Rajiv Gandhi Street, Moovar Nagar, Polichalur, Chennai-600074", "label": "text"},
            {"text": "GSTIN/UIN: 33AFGFS0045E1ZG", "label": "text"},
        ]
    }
    op = choose_operator(extracted, [])
    assert op["name"] == "Skyon Office Spaces LLP"
    assert op["gstin"] == "33AFGFS0045E1ZG"


def test_single_vendor_gstin_and_inv_prefix():
    text = """SREE DESIGN INFRASTRUCTURE PVT LTD
Prakash Presidium, 110, Mahatma Gandhi Road, Nungambakkam, Chennai - 600034
GST: 33AAACU4245J1ZF
Open desk 2 Seats
INV-0044
Date: 19 August 2026
Due Date: 21 August 2026
PREPARED FOR
GoFloaters
SMBSURE BUSINESS SOLUTIONS PRIVATE LIMITED
salesteam@gofloaters.com
9445492855
Total: 12,036
"""
    d = run(text)
    assert d["invoice"]["number"] == "INV-0044"
    assert d["operator"]["gstin"] == "33AAACU4245J1ZF"
    assert d["gofloaters"]["gstin"] is None


def test_cowork_is_never_operator_name():
    from invoice_parser.normalize import is_valid_party_name, choose_operator
    assert not is_valid_party_name("co-work")
    assert not is_valid_party_name("cowork")
    assert not is_valid_party_name("coworking")
    assert not is_valid_party_name("meeting room")

    extracted = {
        "texts": [
            {"text": "Vaanagam", "label": "title"},
            {"text": "Near Lakshmi Mills Junction, Coimbatore - 641 037", "label": "text"},
            {"text": "Tenant Details: GoFloaters", "label": "text"},
            {"text": "co-work", "label": "text"},
            {"text": "3-seater Meeting Room", "label": "text"},
        ]
    }
    op = choose_operator(extracted, [])
    assert op["name"] != "co-work"
    assert op["name"] == "Vaanagam"


def test_cgst9_sgst9_extraction():
    text = (
        "Sub Total 8,400.00\n"
        "CGST9 (9%) 756.00\n"
        "SGST9 (9%) 756.00\n"
        "Total 9,912.00\n"
    )
    b = {"invoice": {"number": None, "date": None, "due_date": None},
         "operator": {"name": None, "address": None, "state": None, "gstin": None},
         "gofloaters": {"name": None, "address": None, "state": None, "gstin": None},
         "tax": {"taxable_amount": None, "cgst": None, "sgst": None, "igst": None, "total": None}}
    d = apply_fallbacks(b, {"markdown": text})
    assert d["tax"]["taxable_amount"] == 8400.0
    assert d["tax"]["cgst"] == 756.0
    assert d["tax"]["sgst"] == 756.0
    assert d["tax"]["total"] == 9912.0


def test_interleaved_tax_summary_with_rounding_and_footer():
    text = (
        "Total Taxable Amount\n"
        "960.00\n"
        "CGST9 (9%)\n"
        "86.40\n"
        "SGST9 (9%)\n"
        "86.40\n"
        "Rounding\n"
        "0.20\n"
        "Total\n"
        "1,133.00\n"
        "Balance Due\n"
        "1,133.00\n"
        "Total In Words: Indian Rupee One Thousand One Hundred Thirty-Three Only\n"
        "1\n"
        "Director\n"
        "2\n"
    )
    b = {"invoice": {"number": None, "date": None, "due_date": None},
         "operator": {"name": None, "address": None, "state": None, "gstin": None},
         "gofloaters": {"name": None, "address": None, "state": None, "gstin": None},
         "tax": {"taxable_amount": None, "cgst": None, "sgst": None, "igst": None, "total": None}}
    d = apply_fallbacks(b, {"markdown": text})
    assert d["tax"]["taxable_amount"] == 960.0
    assert d["tax"]["cgst"] == 86.40
    assert d["tax"]["sgst"] == 86.40
    assert d["tax"]["total"] == 1133.0

def test_stacked_summary_tax_order_independence():
    # SGST first
    text_sgst_first = (
        "SI\nParticulars\n1\nOFFICE SPACE RENT INCOME\nSGST Output @9%\nCGST Output @ 9%\n"
        "Round Off\nHSN/SAC\nRate\nAmount\n998594\n832.00\n74.88\n74.88\n0.24\n₹ 982.00"
    )
    res_sgst = extract_stacked_summary(text_sgst_first)
    assert res_sgst == {"taxable_amount": 832.0, "cgst": 74.88, "sgst": 74.88, "total": 982.0}

    # CGST first
    text_cgst_first = (
        "SI\nParticulars\n1\nOFFICE SPACE RENT INCOME\nCGST Output @ 9%\nSGST Output @9%\n"
        "Round Off\nHSN/SAC\nRate\nAmount\n998594\n832.00\n74.88\n74.88\n0.24\n₹ 982.00"
    )
    res_cgst = extract_stacked_summary(text_cgst_first)
    assert res_cgst == {"taxable_amount": 832.0, "cgst": 74.88, "sgst": 74.88, "total": 982.0}


def test_columnar_line_item_and_stacked_summary_recovery():
    text = (
        "SI\nParticulars\nNo\n1\nOFFICE SPACE RENT INCOME\nSGST Output @9%\nCGST Output @ 9%\n"
        "Round Off\nHSN/SAC\nRate\nAmount\nQuantity\nper\n998594\n832.00\n74.88\n74.88\n0.24\n₹ 982.00"
    )
    items = extract_digital_line_items(text)
    assert len(items) == 1
    assert items[0]["description"] == "OFFICE SPACE RENT INCOME"
    assert items[0]["hsn_sac"] == "998594"
    assert items[0]["amount"] == 832.0

    b = {
        "invoice": {"number": None, "date": None, "due_date": None},
        "operator": {"name": None, "address": None, "state": None, "gstin": None},
        "gofloaters": {"name": None, "address": None, "state": None, "gstin": None},
        "tax": {"taxable_amount": None, "cgst": None, "sgst": None, "igst": None, "total": None},
    }
    d = apply_fallbacks(b, {"markdown": text})
    assert d["tax"]["taxable_amount"] == 832.0
    assert d["tax"]["cgst"] == 74.88
    assert d["tax"]["sgst"] == 74.88
    assert d["tax"]["total"] == 982.0
    assert len(d["line_items"]) == 1






def test_labeled_gstin_merged_with_trailing_text():
    from invoice_parser.normalize import find_gstin
    # Verify find_gstin extracts 15-char GSTIN even when trailing text is glued without spaces
    assert find_gstin("GSTIN 01ADVPH4537K1ZCHead Office") == "01ADVPH4537K1ZC"
    assert find_gstin("GST NO: 29AADCI1790F3ZG(Karnataka)") == "29AADCI1790F3ZG"

    txt = '''
    Prism Creationz
    Second Floor Trade Zone Building Wazir Bagh Srinagar Jammu and Kashmir 190008 India
    GSTIN 01ADVPH4537K1ZCHead Office
    Bill To: SMBSURE BUSINESS SOLUTIONS PRIVATE LIMITED
    600096 Tamil Nadu India
    GSTIN 33AAYCS6808H1ZT
    '''
    doc = {
        "invoice": {"number": None, "date": None, "due_date": None},
        "operator": {"name": None, "address": None, "state": None, "gstin": None},
        "gofloaters": {"name": None, "address": None, "state": None, "gstin": None},
        "tax": {"taxable_amount": None, "cgst": None, "sgst": None, "igst": None, "total": None},
    }
    res = apply_fallbacks(doc, {"markdown": txt, "text": txt})
    assert res["operator"]["gstin"] == "01ADVPH4537K1ZC"
    assert res["gofloaters"]["gstin"] == "33AAYCS6808H1ZT"


def test_prevent_false_swap_when_total_equals_tax_sum():
    # When total was extracted as the tax sum (e.g. 648 = 324 + 324) and base is 3600,
    # the parser must NOT swap them. It should compute total = 4248.0
    doc = {
        "invoice": {"number": "PW/COI/26-27/063", "date": "2026-07-10", "due_date": None},
        "operator": {"name": "AMERITORE", "address": "COIMBATORE", "state": "Tamil Nadu", "gstin": "33AAPCA1486J1ZF"},
        "gofloaters": {"name": "SMBSURE", "address": "Chennai", "state": "Tamil Nadu", "gstin": "33AAYCS6808H1ZT"},
        "tax": {"taxable_amount": 3600.0, "cgst": 324.0, "sgst": 324.0, "igst": None, "total": 648.0},
    }
    from invoice_parser.fallback import derive_fields
    derive_fields(doc)
    assert doc["tax"]["taxable_amount"] == 3600.0
    assert doc["tax"]["total"] == 4248.0
    assert doc["tax"]["cgst"] == 324.0
    assert doc["tax"]["sgst"] == 324.0
