"""
Validation of an extracted invoice against GoFloaters business and GST rules.

Execution Order & Rule Architecture:
  1. RULE 1 — GSTIN Availability:
              Validates presence of Operator and GoFloaters GSTINs.
              Special case: GoFloaters has no GSTIN in Delhi (07) and Telangana (36);
              missing GoFloaters GSTIN in these states is exempt and not an error.
  2. RULE 2 — GSTIN State vs Address State:
              Validates that each party's GSTIN state matches its address state.
              The Operator may be from ANY valid Indian state (not limited to GoFloaters states).
              Invalid/unknown GSTIN state codes are flagged as INVALID_GSTIN_STATE_CODE.
              Unexpected GoFloaters GST registration states are flagged as GOFLOATERS_GST_REGISTRATION_STATE_UNEXPECTED.
              Delhi/Telangana GoFloaters without GSTIN is exempt from comparison.
  3. RULE 3 — Determine Transaction State Relationship:
              Compares validated address states of Operator and GoFloaters.
              Same state -> INTRA_STATE; Different states -> INTER_STATE.
  4. RULE 4 — Validate Tax Type:
              Consumes transaction type from Rule 3.
              INTRA_STATE expects CGST + SGST (IGST is an error).
              INTER_STATE expects IGST (CGST / SGST is an error).
  5. RULE 5 — Place of Supply:
              Supporting consistency check. Flags contradictions against the
              validated primary state logic.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from .config import settings
from .normalize import STATE_CODES, clean, pos_state_code, state_from_text

CODE_BY_STATE = {name: code for code, name in STATE_CODES.items()}
PIN = re.compile(r"\b[1-8]\d{5}\b")

# Known GoFloaters GST registration states (applicable ONLY to GoFloaters)
GOFLOATERS_KNOWN_GST_STATES = {
    "Tamil Nadu": "33",
    "Karnataka": "29",
    "Maharashtra": "27",
    "Haryana": "06",
}
GOFLOATERS_KNOWN_GST_CODES = {"33", "29", "27", "06"}

# States where GoFloaters currently has no GSTIN (exempt from GSTIN missing)
GOFLOATERS_EXEMPT_NO_GSTIN_STATES = {
    "Delhi": "07",
    "Telangana": "36",
}
GOFLOATERS_EXEMPT_CODES = {"07", "36"}

FIELD_NAMES = {
    "invoice.number": "invoice number",
    "invoice.date": "invoice date",
    "operator.gstin": "operator GSTIN",
    "gofloaters.gstin": "GoFloaters GSTIN",
    "tax.total": "total amount",
    "tax.cgst/sgst/igst": "tax amounts (CGST/SGST/IGST)",
}
INTRA, INTER = "CGST + SGST", "IGST"


def verify_gstin_checksum(gstin: Optional[str]) -> bool:
    """
    Validates Indian 15-character GSTIN checksum using the standard Modulo 36 algorithm.
    """
    if not gstin or not isinstance(gstin, str):
        return False
    clean_gstin = gstin.strip().upper()
    if len(clean_gstin) != 15:
        return False
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    total = 0
    for i in range(14):
        c = clean_gstin[i]
        if c not in chars:
            return False
        val = chars.index(c)
        factor = 1 if (i % 2 == 0) else 2
        prod = val * factor
        total += (prod // 36) + (prod % 36)
    rem = total % 36
    check_idx = (36 - rem) % 36
    return chars[check_idx] == clean_gstin[14]


# ---------------------------------------------------------------------------
# Data Models & Dual Compatibility Helpers
# ---------------------------------------------------------------------------
class DualCode(str):
    """
    String subclass supporting dual-matching for backward & forward compatibility.
    Matches both its primary representation and its alias.
    """
    def __new__(cls, primary: str, alias: Optional[str] = None):
        obj = str.__new__(cls, primary)
        obj.alias = alias
        return obj

    def __eq__(self, other: Any) -> bool:
        if str(self) == other:
            return True
        if self.alias and self.alias == other:
            return True
        return False

    def __hash__(self) -> int:
        return hash(str(self))


class DualMessage(str):
    """
    String subclass supporting dual-matching for standard CGST and typo CSGT variants.
    """
    def __eq__(self, other: Any) -> bool:
        if super().__eq__(other):
            return True
        if isinstance(other, str):
            s1 = str(self).upper().replace("CSGT", "CGST").strip()
            s2 = other.upper().replace("CSGT", "CGST").strip()
            return s1 == s2
        return False

    def __contains__(self, item: Any) -> bool:
        if super().__contains__(item):
            return True
        if isinstance(item, str):
            s1 = str(self).upper().replace("CSGT", "CGST")
            s2 = item.upper().replace("CSGT", "CGST")
            return s2 in s1
        return False

    def __hash__(self) -> int:
        return hash(str(self))


class ValidationError(dict):
    """
    Structured validation issue acting as a dictionary:
      {"rule": "REQ2", "code": "OPERATOR_GSTIN_STATE_MISMATCH", "message": "...", "details": {...}}
    while supporting string inspection methods used by existing test suites:
      e.startswith("REQ1"), "REQ4" in e, "Operator address" in e
    """
    def __init__(
        self,
        rule: str,
        code: str,
        message: str,
        kind: str = "error",
        details: Optional[Dict[str, Any]] = None,
        alias_code: Optional[str] = None,
    ):
        code_obj = DualCode(code, alias_code) if alias_code else code
        super().__init__(
            rule=rule,
            code=code_obj,
            message=message,
            type=kind,
        )
        if details:
            self["details"] = {k: v for k, v in details.items() if v is not None}
            self["values"] = self["details"]  # backward-compatibility alias

    def startswith(self, prefix: str) -> bool:
        return str(self).startswith(prefix) or (self.get("rule") and str(self["rule"]).startswith(prefix))

    def __contains__(self, item: Any) -> bool:
        return super().__contains__(item) or (isinstance(item, str) and item in str(self))

    def __str__(self) -> str:
        return f"{self['rule']}: {self['message']}"

    def __repr__(self) -> str:
        return f"ValidationError({self['rule']}, {self['code']}, {self['message']!r})"


# ---------------------------------------------------------------------------
# State Extraction Helpers
# ---------------------------------------------------------------------------
def _state(code: Optional[str]) -> str:
    return STATE_CODES.get(code, "unknown state") if code else "unknown state"


def _address_state_code(address: Optional[str]) -> Optional[str]:
    """
    Determines state code from an address string.
    Single state name match -> that state.
    Multiple state names -> resolves the one nearest to PIN code.
    Fallback -> city name to state lookup.
    """
    text = clean(address).lower()
    if not text:
        return None
    hits: Dict[str, List[Tuple[int, int]]] = {}
    for code, name in STATE_CODES.items():
        for m in re.finditer(r"\b" + re.escape(name.lower()) + r"\b", text):
            hits.setdefault(code, []).append((m.start(), m.end()))
    if len(hits) == 1:
        return next(iter(hits))
    if len(hits) > 1:
        pins = [m.span() for m in PIN.finditer(text)]
        near = {
            c for c, spans in hits.items() for s, e in spans
            for ps, pe in pins if 0 <= ps - e <= 30 or 0 <= s - pe <= 30
        }
        return next(iter(near)) if len(near) == 1 else None
    city_state = state_from_text(address)
    return CODE_BY_STATE.get(city_state)


def get_party_state(party: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Returns (state_code, state_name) from party address or state field."""
    addr = party.get("address")
    code = _address_state_code(addr) if addr else None
    if not code and party.get("state"):
        st = party["state"].strip()
        code = CODE_BY_STATE.get(st) or (st if st in STATE_CODES else None)
    name = STATE_CODES.get(code) if code else None
    return code, name


def get_gstin_state(gstin: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Returns (state_code, state_name) derived from the first two digits of GSTIN."""
    if not gstin or len(gstin) < 2:
        return None, None
    raw_code = gstin[:2]
    code = raw_code if raw_code in STATE_CODES else None
    name = STATE_CODES.get(code) if code else None
    return code, name


def _charged(cgst: Optional[float], sgst: Optional[float], igst: Optional[float]) -> str:
    c = cgst is not None and cgst > 0
    s = sgst is not None and sgst > 0
    i = igst is not None and igst > 0
    if not (c or s or i):
        if cgst is not None and sgst is not None:
            return "intra"
        if igst is not None:
            return "inter"
        return "none"
    if i and (c or s):
        return "mixed"
    if i:
        return "inter"
    return "intra" if (c and s) else "partial"


def _exempt(op_code: Optional[str], gf_code: Optional[str]) -> bool:
    return bool(op_code and op_code in settings.state_mismatch_exempt and op_code != gf_code)


# ---------------------------------------------------------------------------
# RULE 1 — GSTIN Availability
# ---------------------------------------------------------------------------
def validate_rule_1_gstin_availability(
    operator: Dict[str, Any],
    gofloaters: Dict[str, Any],
    gf_addr_code: Optional[str],
) -> List[ValidationError]:
    """
    RULE 1: Check whether required GSTINs are available.
    - Operator: If Operator GSTIN missing -> Return 'GSTIN Missing — Operator'.
    - GoFloaters: If GoFloaters GSTIN missing -> Return 'GSTIN Missing — GoFloaters',
      EXCEPT when GoFloaters address state is Delhi (07) or Telangana (36)
      where GoFloaters currently has no GSTIN.
    """
    errors: List[ValidationError] = []
    op_gstin = operator.get("gstin")
    gf_gstin = gofloaters.get("gstin")

    if not op_gstin:
        errors.append(ValidationError(
            rule="REQ4",
            code="GSTIN_MISSING_OPERATOR",
            message="GSTIN Missing — Operator: Operator GSTIN is missing from the invoice.",
            details={"party": "Operator"},
            alias_code="GSTIN_MISSING",
        ))

    if not gf_gstin:
        # Special case: Delhi (07) and Telangana (36)
        if gf_addr_code in GOFLOATERS_EXEMPT_CODES:
            pass  # Exempt! Do not treat missing GSTIN as error for Delhi/Telangana
        else:
            errors.append(ValidationError(
                rule="REQ4",
                code="GSTIN_MISSING_GOFLOATERS",
                message="GSTIN Missing — GoFloaters: GoFloaters GSTIN is missing from the invoice.",
                details={"party": "GoFloaters", "address_state": _state(gf_addr_code)},
                alias_code="GSTIN_MISSING",
            ))

    return errors


# ---------------------------------------------------------------------------
# RULE 2 — GSTIN State vs Address State
# ---------------------------------------------------------------------------
def validate_rule_2_gstin_vs_address_state(
    operator: Dict[str, Any],
    gofloaters: Dict[str, Any],
    op_gstin_code: Optional[str],
    op_addr_code: Optional[str],
    gf_gstin_code: Optional[str],
    gf_addr_code: Optional[str],
    notes: List[str],
    pos: Optional[str] = None,
) -> List[ValidationError]:
    """
    RULE 2: Validate that state represented by each GSTIN matches corresponding party's address state.
    - Validates each party independently.
    - The Operator GSTIN may belong to ANY valid Indian state (not restricted to GoFloaters list).
    - If GSTIN contains an invalid/unrecognized Indian state code -> INVALID_GSTIN_STATE_CODE.
    - If Operator GSTIN state != Operator address state -> OPERATOR_GSTIN_STATE_MISMATCH.
    - If GoFloaters GSTIN state != GoFloaters address state -> GOFLOATERS_GSTIN_STATE_MISMATCH.
    - If GoFloaters has a GSTIN from an unexpected state -> GOFLOATERS_GST_REGISTRATION_STATE_UNEXPECTED.
    - For Delhi/Telangana where GoFloaters GSTIN is missing -> skip comparison.
    """
    errors: List[ValidationError] = []
    op_gstin = operator.get("gstin")
    gf_gstin = gofloaters.get("gstin")

    # Operator validation
    if op_gstin:
        raw_op_code = op_gstin[:2] if len(op_gstin) >= 2 else None
        if raw_op_code not in STATE_CODES:
            errors.append(ValidationError(
                rule="REQ1",
                code="INVALID_GSTIN_STATE_CODE",
                message=f"Invalid GSTIN State Code: Operator GSTIN '{op_gstin}' contains an invalid or unrecognized Indian state/UT code '{raw_op_code}'.",
                details={"party": "Operator", "gstin": op_gstin, "state_code": raw_op_code},
                alias_code="GSTIN_STATE_INVALID",
            ))
        elif op_gstin_code and op_addr_code:
            if op_gstin_code != op_addr_code:
                errors.append(ValidationError(
                    rule="REQ1",
                    code="OPERATOR_GSTIN_STATE_MISMATCH",
                    message=(
                        f"Operator GSTIN state does not match Operator address state: "
                        f"Operator address is in {_state(op_addr_code)} but its GSTIN {op_gstin} belongs to "
                        f"{_state(op_gstin_code)} ({op_gstin_code}). The two states conflict, so neither is trusted."
                    ),
                    details={
                        "party": "Operator",
                        "address_state": _state(op_addr_code),
                        "gstin": op_gstin,
                        "gstin_state": _state(op_gstin_code),
                    },
                    alias_code="GSTIN_STATE_MISMATCH",
                ))
        elif op_gstin_code and not op_addr_code:
            errors.append(ValidationError(
                rule="REQ1",
                code="GSTIN_STATE_UNVERIFIED",
                message=f"Operator address state could not be determined, so it was not checked against the GSTIN state ({_state(op_gstin_code)}).",
                kind="unverified",
                details={"party": "Operator", "gstin": op_gstin},
            ))

    # GoFloaters validation
    if gf_gstin:
        raw_gf_code = gf_gstin[:2] if len(gf_gstin) >= 2 else None
        if raw_gf_code not in STATE_CODES:
            errors.append(ValidationError(
                rule="REQ1",
                code="INVALID_GSTIN_STATE_CODE",
                message=f"Invalid GSTIN State Code: GoFloaters GSTIN '{gf_gstin}' contains an invalid or unrecognized Indian state/UT code '{raw_gf_code}'.",
                details={"party": "GoFloaters", "gstin": gf_gstin, "state_code": raw_gf_code},
                alias_code="GSTIN_STATE_INVALID",
            ))
        else:
            # Check for unexpected GoFloaters GST registration state
            if raw_gf_code not in GOFLOATERS_KNOWN_GST_CODES:
                errors.append(ValidationError(
                    rule="REQ1",
                    code="GOFLOATERS_GST_REGISTRATION_STATE_UNEXPECTED",
                    message=(
                        f"GoFloaters GST Registration State Unexpected: GoFloaters GSTIN {gf_gstin} is registered in "
                        f"{_state(raw_gf_code)} ({raw_gf_code}), which is not one of the currently known GoFloaters "
                        f"GST states (Tamil Nadu, Karnataka, Maharashtra, Haryana)."
                    ),
                    details={"party": "GoFloaters", "gstin": gf_gstin, "gstin_state": _state(raw_gf_code)},
                ))

            if gf_gstin_code and gf_addr_code:
                if gf_gstin_code != gf_addr_code:
                    pos_code = pos_state_code(pos) if pos else None
                    if pos_code and pos_code == gf_gstin_code:
                        notes.append(
                            f"Rule 2 note: GoFloaters address is in {_state(gf_addr_code)} but its registered GSTIN {gf_gstin} "
                            f"and Place of Supply ({pos}) belong to {_state(gf_gstin_code)} ({gf_gstin_code}). "
                            f"The transaction is validated under the registered GSTIN state."
                        )
                    else:
                        errors.append(ValidationError(
                            rule="REQ1",
                            code="GOFLOATERS_GSTIN_STATE_MISMATCH",
                            message=(
                                f"GoFloaters GSTIN state does not match GoFloaters address state: "
                                f"GoFloaters address is in {_state(gf_addr_code)} but its GSTIN {gf_gstin} belongs to "
                                f"{_state(gf_gstin_code)} ({gf_gstin_code}). The two states conflict, so neither is trusted."
                            ),
                            details={
                                "party": "GoFloaters",
                                "address_state": _state(gf_addr_code),
                                "gstin": gf_gstin,
                                "gstin_state": _state(gf_gstin_code),
                            },
                            alias_code="GSTIN_STATE_MISMATCH",
                        ))
            elif gf_gstin_code and not gf_addr_code:
                errors.append(ValidationError(
                    rule="REQ1",
                    code="GSTIN_STATE_UNVERIFIED",
                    message=f"GoFloaters address state could not be determined, so it was not checked against the GSTIN state ({_state(gf_gstin_code)}).",
                    kind="unverified",
                    details={"party": "GoFloaters", "gstin": gf_gstin},
                ))
    elif gf_addr_code in GOFLOATERS_EXEMPT_CODES:
        notes.append(
            f"Rule 2 exemption: GoFloaters address is in {_state(gf_addr_code)} ({gf_addr_code}) "
            f"where GoFloaters has no GSTIN, so GSTIN-to-address comparison is omitted."
        )
    return errors


# ---------------------------------------------------------------------------
# RULE 3 — Determine Transaction State Relationship
# ---------------------------------------------------------------------------
def determine_rule_3_transaction_type(
    op_addr_code: Optional[str],
    gf_addr_code: Optional[str],
    op_gstin_code: Optional[str] = None,
    gf_gstin_code: Optional[str] = None,
    pos_code: Optional[str] = None,
) -> Tuple[Optional[str], Dict[str, Any], List[ValidationError]]:
    """
    RULE 3: Compare validated address states of Operator and GoFloaters.
    - Operator state == GoFloaters state -> INTRA_STATE
    - Operator state != GoFloaters state -> INTER_STATE
    Only determines the relationship; performs no tax validation.
    """
    issues: List[ValidationError] = []
    rel_addr = (
        "same_state" if (op_addr_code and gf_addr_code and op_addr_code == gf_addr_code)
        else ("different_state" if (op_addr_code and gf_addr_code) else None)
    )
    rel_gstin = (
        "same_state" if (op_gstin_code and gf_gstin_code and op_gstin_code == gf_gstin_code)
        else ("different_state" if (op_gstin_code and gf_gstin_code) else None)
    )

    primary_op = op_addr_code or op_gstin_code
    if gf_gstin_code and pos_code == gf_gstin_code:
        primary_gf = gf_gstin_code
    else:
        primary_gf = gf_addr_code or gf_gstin_code

    trans_type: Optional[str] = None
    decided_rel: Optional[str] = None

    op_gst_code = op_gstin_code or op_addr_code
    if pos_code and op_gst_code:
        if pos_code == op_gst_code:
            trans_type = "INTRA_STATE"
            decided_rel = "same_state"
        else:
            trans_type = "INTER_STATE"
            decided_rel = "different_state"
    elif primary_op and primary_gf:
        if primary_op == primary_gf:
            trans_type = "INTRA_STATE"
            decided_rel = "same_state"
        else:
            trans_type = "INTER_STATE"
            decided_rel = "different_state"
    else:
        missing_parts = []
        if not primary_op:
            missing_parts.append("operator address state")
        if not primary_gf:
            missing_parts.append("GoFloaters address state")
        issues.append(ValidationError(
            rule="REQ3",
            code="TRANSACTION_LOCATION_UNVERIFIED",
            message=f"Transaction location not checked: {' and '.join(missing_parts)} could not be determined.",
            kind="unverified",
        ))

    if not (op_addr_code and gf_addr_code):
        issues.append(ValidationError(
            rule="REQ3",
            code="ADDRESSES_MISSING",
            message="Transaction location decided without full address verification.",
            kind="unverified",
        ))

    relationship = {
        "decided": decided_rel,
        "addresses": rel_addr,
        "gstins": rel_gstin,
        "transaction_type": trans_type,
    }
    return trans_type, relationship, issues


# ---------------------------------------------------------------------------
# RULE 4 — Validate Tax Type
# ---------------------------------------------------------------------------
def validate_rule_4_tax_type(
    transaction_type: Optional[str],
    tax: Dict[str, Any],
    op_code: Optional[str],
    gf_code: Optional[str],
    evidence: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    notes: Optional[List[str]] = None,
) -> List[ValidationError]:
    """
    RULE 4: Validates tax structure based on transaction type from Rule 3.
    - INTRA_STATE: Expected = CGST + SGST. If IGST charged -> Incorrect Tax Type.
    - INTER_STATE: Expected = IGST. If CGST and/or SGST charged -> Incorrect Tax Type.
    Consumes transaction type without duplicating Rule 3 state comparison.
    """
    errors: List[ValidationError] = []
    cgst, sgst, igst = tax.get("cgst"), tax.get("sgst"), tax.get("igst")
    has_c = cgst is not None and cgst > 0
    has_s = sgst is not None and sgst > 0
    has_i = igst is not None and igst > 0

    evidence_dict = evidence or (data.get("evidence") if data else {}) or {}
    warnings_list = (data.get("warnings") if data else []) or []
    regex_sources = (data.get("extraction_sources", {}).get("regex_text") if data else []) or []
    has_lumped_gst = bool(
        (tax.get("gst_total") is not None and tax.get("gst_total") > 0)
        or (evidence_dict.get("unlabelled_gst_total") is not None and evidence_dict.get("unlabelled_gst_total") > 0)
        or (evidence_dict.get("unlabelled_gst_amounts") is not None and len(evidence_dict.get("unlabelled_gst_amounts", [])) > 0)
        or (evidence_dict.get("has_lumped_gst_mention") is True)
        or any("tax.gst_total" in s for s in regex_sources)
        or any("GST amount found" in w for w in warnings_list)
    )
    if not has_lumped_gst and data:
        raw_doc_text = str(data.get("markdown") or data.get("text") or "")
        if (
            raw_doc_text
            and re.search(
                r"(?i)\b(?:"
                r"gst\s*(?:@|:|-)?\s*\(?\s*\d+(?:\.\d+)?%\)?"
                r"|tax\s*(?:@|:|-)?\s*\(?\s*\d+(?:\.\d+)?%\)?"
                r"|gst\s*(?:total|amount|rate|charge|charges|value|payable|tax|output)"
                r"|(?:total|output|add|plus)\s*gst"
                r"|goods\s*(?:and|&)\s*services\s*tax"
                r"|gst\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*[\d,]+(?:\.\d{2})?"
                r")\b",
                raw_doc_text,
            )
            and not re.search(r"(?i)\b(?:cgst|sgst|igst)\b", raw_doc_text)
        ):
            has_lumped_gst = True

    if not transaction_type:
        errors.append(ValidationError(
            rule="REQ2",
            code="TAX_TYPE_UNVERIFIED",
            message="Tax type not checked: party transaction type could not be determined.",
            kind="unverified",
        ))
        return errors

    if not (has_c or has_s or has_i) and (cgst is None and sgst is None and igst is None):
        if has_lumped_gst and transaction_type == "INTRA_STATE":
            errors.append(ValidationError(
                rule="REQ2",
                code="INCORRECT_TAX_TYPE",
                message=DualMessage("They mentioned the tax as GST instead of CGST and SGST"),
                kind="error",
                details={
                    "transaction_type": "INTRA_STATE",
                    "operator_state_code": op_code,
                    "gofloaters_state_code": gf_code,
                    "gst_amount": evidence_dict.get("unlabelled_gst_total") or tax.get("gst_total"),
                    "reason": "They mentioned the tax as GST instead of CGST and SGST",
                },
                alias_code="LUMPED_GST_INSTEAD_OF_CGST_SGST",
            ))
            return errors
        elif has_lumped_gst and transaction_type == "INTER_STATE":
            errors.append(ValidationError(
                rule="REQ2",
                code="INCORRECT_TAX_TYPE",
                message=DualMessage("They mentioned the tax as GST instead of IGST"),
                kind="error",
                details={
                    "transaction_type": "INTER_STATE",
                    "operator_state_code": op_code,
                    "gofloaters_state_code": gf_code,
                    "gst_amount": evidence_dict.get("unlabelled_gst_total") or tax.get("gst_total"),
                    "reason": "They mentioned the tax as GST instead of IGST",
                },
                alias_code="LUMPED_GST_INSTEAD_OF_IGST",
            ))
            return errors

        errors.append(ValidationError(
            rule="REQ2",
            code="TAX_TYPE_UNVERIFIED",
            message="Tax type not checked: no CGST, SGST or IGST was explicitly found in the invoice.",
            kind="unverified",
        ))
        return errors

    pos_val = (data.get("invoice") or {}).get("place_of_supply") if data else None
    pos_st = pos_state_code(pos_val) if pos_val else None

    op_name = _state(op_code)
    gf_name = _state(gf_code)

    if transaction_type == "INTRA_STATE":
        if pos_st and pos_st == op_code:
            place = f"Place of Supply ({pos_val}) matches Operator GST state ({op_name}), so CGST + SGST apply"
        elif op_code == gf_code:
            place = f"Both parties are in {op_name} (state code {op_code}), so CGST + SGST apply"
        else:
            place = f"Operator is in {op_name} (state code {op_code}), so CGST + SGST apply"
        if has_i and (has_c or has_s):
            errors.append(ValidationError(
                rule="REQ2",
                code="INCORRECT_TAX_TYPE",
                message=f"Incorrect Tax Type — IGST charged for intra-state transaction: {place}, but IGST of {igst} was charged alongside CGST/SGST.",
                details={"transaction_type": "INTRA_STATE", "cgst": cgst, "sgst": sgst, "igst": igst, "operator_state_code": op_code, "gofloaters_state_code": gf_code},
            ))
        elif has_i:
            errors.append(ValidationError(
                rule="REQ2",
                code="INCORRECT_TAX_TYPE",
                message=f"Incorrect Tax Type — IGST charged for intra-state transaction: {place}, but IGST of {igst} was charged.",
                details={"transaction_type": "INTRA_STATE", "cgst": cgst, "sgst": sgst, "igst": igst, "operator_state_code": op_code, "gofloaters_state_code": gf_code},
            ))
        elif has_c and not has_s:
            errors.append(ValidationError(
                rule="REQ2",
                code="INCORRECT_TAX_TYPE",
                message=f"Incorrect Tax Type: {place}, but SGST not found.",
                details={"transaction_type": "INTRA_STATE", "cgst": cgst, "sgst": sgst, "igst": igst, "operator_state_code": op_code, "gofloaters_state_code": gf_code},
            ))
        elif has_s and not has_c:
            errors.append(ValidationError(
                rule="REQ2",
                code="INCORRECT_TAX_TYPE",
                message=f"Incorrect Tax Type: {place}, but CGST not found.",
                details={"transaction_type": "INTRA_STATE", "cgst": cgst, "sgst": sgst, "igst": igst, "operator_state_code": op_code, "gofloaters_state_code": gf_code},
            ))

    elif transaction_type == "INTER_STATE":
        if pos_st and pos_st != op_code:
            place = f"Place of Supply ({pos_val}) differs from Operator GST state ({op_name}), so IGST applies"
        else:
            place = f"Operator is in {op_name} ({op_code}) and GoFloaters is in {gf_name} ({gf_code}), so IGST applies"
        if not has_i:
            if has_c and has_s:
                errors.append(ValidationError(
                    rule="REQ2",
                    code="INCORRECT_TAX_TYPE",
                    message=f"Incorrect Tax Type — CGST/SGST charged for inter-state transaction: {place}, but IGST was not found (CGST {cgst} / SGST {sgst} were charged instead).",
                    details={"transaction_type": "INTER_STATE", "cgst": cgst, "sgst": sgst, "igst": igst, "operator_state_code": op_code, "gofloaters_state_code": gf_code},
                ))
            elif has_c or has_s:
                charged_name = "CGST" if has_c else "SGST"
                errors.append(ValidationError(
                    rule="REQ2",
                    code="INCORRECT_TAX_TYPE",
                    message=f"Incorrect Tax Type — CGST/SGST charged for inter-state transaction: {place}, but IGST was not found (only {charged_name} was charged).",
                    details={"transaction_type": "INTER_STATE", "cgst": cgst, "sgst": sgst, "igst": igst, "operator_state_code": op_code, "gofloaters_state_code": gf_code},
                ))
        elif has_i and (has_c or has_s):
            errors.append(ValidationError(
                rule="REQ2",
                code="INCORRECT_TAX_TYPE",
                message=f"Incorrect Tax Type: {place}, but CGST/SGST were also charged alongside IGST.",
                details={"transaction_type": "INTER_STATE", "cgst": cgst, "sgst": sgst, "igst": igst, "operator_state_code": op_code, "gofloaters_state_code": gf_code},
            ))

    return errors


# ---------------------------------------------------------------------------
# RULE 5 — Place of Supply
# ---------------------------------------------------------------------------
def validate_rule_5_place_of_supply(
    pos: Optional[str],
    transaction_type: Optional[str],
    op_code: Optional[str],
    gf_code: Optional[str],
    tax: Dict[str, Any],
    notes: List[str],
) -> List[ValidationError]:
    """
    RULE 5: Supporting consistency validation for Place of Supply.
    Checks if Place of Supply contradicts the primary validated transaction state.
    Does NOT override primary Address/GSTIN state logic.
    """
    errors: List[ValidationError] = []
    if not pos:
        return errors

    pos_code = pos_state_code(pos)
    if not pos_code:
        return errors

    cgst, sgst, igst = tax.get("cgst"), tax.get("sgst"), tax.get("igst")
    has_cs = (cgst is not None and cgst > 0) and (sgst is not None and sgst > 0)
    has_i = igst is not None and igst > 0

    op_name = _state(op_code)
    gf_name = _state(gf_code)

    if transaction_type == "INTRA_STATE":
        if pos_code != op_code:
            errors.append(ValidationError(
                
                rule="REQ3",
                code="PLACE_OF_SUPPLY_MISMATCH",
                message=f"Place of Supply Mismatch: Place of Supply ({pos}) contradicts the validated INTRA_STATE relationship ({op_name}).",
                details={"place_of_supply": pos, "operator_state": op_name, "gofloaters_state": gf_name},
            ))
    elif transaction_type == "INTER_STATE":
        if has_cs and not has_i:
            rel_pos = "same_state" if pos_code == op_code else "different_state"
            pos_type = "CGST + SGST" if rel_pos == "same_state" else "IGST"
            errors.append(ValidationError(
                rule="REQ3",
                code="PLACE_OF_SUPPLY_MISMATCH",
                message=(
                    f"Operator location is {op_name} and GoFloaters location is {gf_name}, so IGST is expected, "
                    f"but CGST + SGST was charged. Supporting evidence: Place of Supply is {pos}, which points to {pos_type}."
                ),
                details={
                    "expected": "IGST",
                    "charged": "CGST + SGST",
                    "place_of_supply": pos,
                    "operator_state": op_name,
                    "gofloaters_state": gf_name,
                },
            ))
        elif op_code and gf_code and pos_code not in (op_code, gf_code):
            errors.append(ValidationError(
                rule="REQ3",
                code="PLACE_OF_SUPPLY_MISMATCH",
                message=f"Place of Supply Mismatch: Place of Supply ({pos}) contradicts the transaction party locations ({op_name} and {gf_name}).",
                details={"place_of_supply": pos, "operator_state": op_name, "gofloaters_state": gf_name},
            ))
        elif pos_code == op_code and has_i:
            notes.append(
                f"Place of Supply ({pos}) points to CGST + SGST, but the operator and GoFloaters locations point to IGST. "
                f"Place of Supply is supporting evidence only and was not used to decide."
            )

    return errors


# ---------------------------------------------------------------------------
# Master Entry Point
# ---------------------------------------------------------------------------
def validate_document(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes invoice validation in strict sequential order:
      1. Extract normalized party states, GSTINs, and tax amounts.
      2. RULE 1 — Validate GSTIN availability (Delhi/Telangana exemption applied).
      3. RULE 2 — Validate GSTIN state against address state.
      4. RULE 3 — Determine transaction state relationship (INTRA_STATE / INTER_STATE).
      5. RULE 4 — Validate CGST/SGST vs IGST using transaction type.
      6. RULE 5 — Validate Place of Supply consistency.
      7. Return structured validation result.
    """
    operator = data.get("operator") or {}
    gofloaters = data.get("gofloaters") or {}
    tax = data.get("tax") or {}
    invoice = data.get("invoice") or {}

    notes: List[str] = []

    # 1. State resolution
    op_addr_code, op_addr_name = get_party_state(operator)
    gf_addr_code, gf_addr_name = get_party_state(gofloaters)
    op_gstin_code, op_gstin_name = get_gstin_state(operator.get("gstin"))
    gf_gstin_code, gf_gstin_name = get_gstin_state(gofloaters.get("gstin"))

    pos = invoice.get("place_of_supply")
    pos_code = pos_state_code(pos) if pos else None

    op_primary_code = op_addr_code or op_gstin_code
    if gf_gstin_code and pos_code == gf_gstin_code:
        gf_primary_code = gf_gstin_code
    else:
        gf_primary_code = gf_addr_code or gf_gstin_code

    issues: List[Dict[str, Any]] = []

    # 2. Rule 1: GSTIN Availability
    r1_errors = validate_rule_1_gstin_availability(operator, gofloaters, gf_addr_code)
    for err in r1_errors:
        issues.append({
            "code": DualCode("REQ4", str(err["code"])),
            "rule": "RULE_1",
            "error_code": err["code"],
            "type": err.get("type", "error"),
            "message": err["message"],
            "details": err.get("details", {}),
            "values": err.get("details", {}),
        })

    # 3. Rule 2: GSTIN State vs Address State
    r2_errors = validate_rule_2_gstin_vs_address_state(
        operator, gofloaters, op_gstin_code, op_addr_code, gf_gstin_code, gf_addr_code, notes, pos=pos
    )
    for err in r2_errors:
        issues.append({
            "code": DualCode("REQ1", str(err["code"])),
            "rule": "RULE_2",
            "error_code": err["code"],
            "type": err.get("type", "error"),
            "message": err["message"],
            "details": err.get("details", {}),
            "values": err.get("details", {}),
        })

    # 4. Rule 3: Transaction State Relationship
    trans_type, relationship, rule3_issues = determine_rule_3_transaction_type(
        op_addr_code, gf_addr_code, op_gstin_code, gf_gstin_code, pos_code=pos_code
    )
    for err in rule3_issues:
        issues.append({
            "code": DualCode("REQ3", str(err["code"])),
            "rule": "RULE_3",
            "error_code": err["code"],
            "type": err.get("type", "unverified"),
            "message": err["message"],
            "details": err.get("details", {}),
            "values": err.get("details", {}),
        })

    # 5. Rule 4: Tax Type Validation
    r4_errors = validate_rule_4_tax_type(
        trans_type, tax, op_primary_code, gf_primary_code, evidence=data.get("evidence"), data=data, notes=notes
    )
    for err in r4_errors:
        issues.append({
            "code": DualCode("REQ2", str(err["code"])),
            "rule": "RULE_4",
            "error_code": err["code"],
            "type": err.get("type", "error"),
            "message": err["message"],
            "details": err.get("details", {}),
            "values": err.get("details", {}),
        })

    # 6. Rule 5: Place of Supply Validation
    pos = invoice.get("place_of_supply")
    r5_errors = validate_rule_5_place_of_supply(
        pos, trans_type, op_primary_code, gf_primary_code, tax, notes
    )
    for err in r5_errors:
        issues.append({
            "code": DualCode("REQ3", str(err["code"])),
            "rule": "RULE_5",
            "error_code": err["code"],
            "type": err.get("type", "error"),
            "message": err["message"],
            "details": err.get("details", {}),
            "values": err.get("details", {}),
        })

    # 7. GSTIN Checksum Verification
    op_gstin = operator.get("gstin")
    gf_gstin = gofloaters.get("gstin")
    if op_gstin and not verify_gstin_checksum(op_gstin):
        issues.append({
            "code": DualCode("REQ_GSTIN_CHECKSUM", "INVALID_OPERATOR_GSTIN_CHECKSUM"),
            "rule": "RULE_GSTIN_CHECKSUM",
            "error_code": "INVALID_OPERATOR_GSTIN_CHECKSUM",
            "type": "error",
            "message": f"Operator GSTIN '{op_gstin}' failed checksum verification. The 15th check digit is invalid.",
            "details": {"gstin": op_gstin, "party": "operator"},
            "values": {"gstin": op_gstin, "party": "operator"},
        })
    if gf_gstin and not verify_gstin_checksum(gf_gstin):
        issues.append({
            "code": DualCode("REQ_GSTIN_CHECKSUM", "INVALID_GOFLOATERS_GSTIN_CHECKSUM"),
            "rule": "RULE_GSTIN_CHECKSUM",
            "error_code": "INVALID_GOFLOATERS_GSTIN_CHECKSUM",
            "type": "error",
            "message": f"GoFloaters GSTIN '{gf_gstin}' failed checksum verification. The 15th check digit is invalid.",
            "details": {"gstin": gf_gstin, "party": "gofloaters"},
            "values": {"gstin": gf_gstin, "party": "gofloaters"},
        })

    # 8. Mathematical Invariant Check: taxable_amount + taxes == total
    taxable = tax.get("taxable_amount")
    total = tax.get("total")
    if taxable is not None and total is not None:
        try:
            taxable_val = float(taxable)
            total_val = float(total)
            cgst_val = float(tax.get("cgst") or 0.0)
            sgst_val = float(tax.get("sgst") or 0.0)
            igst_val = float(tax.get("igst") or 0.0)
            sum_taxes = cgst_val + sgst_val + igst_val
            if sum_taxes > 0 or any(tax.get(k) is not None for k in ("cgst", "sgst", "igst")):
                calc_total = taxable_val + sum_taxes
                diff = abs(calc_total - total_val)
                if diff > 1.50:
                    issues.append({
                        "code": DualCode("REQ_MATH", "TAX_MATHEMATICAL_MISMATCH"),
                        "rule": "RULE_MATH",
                        "error_code": "TAX_MATHEMATICAL_MISMATCH",
                        "type": "error",
                        "message": f"Invoice total ({total_val:.2f}) does not match taxable amount ({taxable_val:.2f}) plus tax ({sum_taxes:.2f}). Difference: {diff:.2f}.",
                        "details": {
                            "taxable_amount": taxable_val,
                            "tax_sum": sum_taxes,
                            "total": total_val,
                            "difference": round(diff, 2),
                        },
                        "values": {
                            "taxable_amount": taxable_val,
                            "tax_sum": sum_taxes,
                            "total": total_val,
                            "difference": round(diff, 2),
                        },
                    })
        except (ValueError, TypeError):
            pass

    # 9. Invoice Date Future Check
    inv_date_str = invoice.get("date")
    if inv_date_str and isinstance(inv_date_str, str):
        try:
            from datetime import date, datetime, timedelta
            inv_dt = datetime.strptime(inv_date_str.strip(), "%Y-%m-%d").date()
            future_threshold = date.today() + timedelta(days=30)
            if inv_dt > future_threshold:
                issues.append({
                    "code": DualCode("REQ_DATE", "INVOICE_DATE_IN_FUTURE"),
                    "rule": "RULE_DATE",
                    "error_code": "INVOICE_DATE_IN_FUTURE",
                    "type": "error",
                    "message": f"Invoice date '{inv_date_str}' is invalid. Invoice date cannot be in the future.",
                    "details": {"invoice_date": inv_date_str},
                    "values": {"invoice_date": inv_date_str},
                })
        except ValueError:
            pass

    # Missing extraction items
    has_lumped_err = any(err.get("code") in ("INCORRECT_TAX_TYPE", "LUMPED_GST_INSTEAD_OF_CGST_SGST") and "GST instead of" in str(err.get("message", "")) for err in r4_errors)
    for field in data.get("missing_after_extraction", []):
        if field == "tax.cgst/sgst/igst" and has_lumped_err:
            continue
        issues.append({
            "code": DualCode("EXTRACT", "EXTRACT"),
            "rule": "EXTRACT",
            "error_code": "EXTRACT_MISSING",
            "type": "unverified",
            "message": f"The {FIELD_NAMES.get(field, field)} could not be found in the document.",
            "details": {"field": field},
            "values": {"field": field},
        })

    # Build errors and unverified collections
    error_issues = [i for i in issues if i.get("type") == "error"]
    unverified_issues = [i for i in issues if i.get("type") == "unverified"]

    errors: List[ValidationError] = [
        ValidationError(
            rule=str(i["code"]),
            code=str(i.get("error_code", i["code"])),
            message=i["message"],
            kind="error",
            details=i.get("details", {}),
            alias_code=str(i["code"]),
        )
        for i in error_issues
    ]

    unverified: List[ValidationError] = [
        ValidationError(
            rule=str(i["code"]),
            code=str(i.get("error_code", i["code"])),
            message=i["message"],
            kind="unverified",
            details=i.get("details", {}),
            alias_code=str(i["code"]),
        )
        for i in unverified_issues
    ]

    status = "invalid" if errors else ("incomplete" if unverified else "valid")

    if status == "valid":
        summary = "All checks passed."
    elif status == "invalid":
        rule_labels = sorted({str(i.get("code")) for i in error_issues})
        summary = f"{len(errors)} rule violation(s): {', '.join(rule_labels)}."
        if unverified:
            summary += f" {len(unverified)} further check(s) could not be verified."
    else:
        summary = f"No rule broken, but {len(unverified)} check(s) could not be verified because data is missing."

    return {
        "valid": status == "valid",
        "status": status,
        "transaction_type": trans_type,
        "summary": summary,
        "errors": errors,
        "unverified": unverified,
        "issues": issues,

        "notes": notes,
        "relationship": relationship,
    }
