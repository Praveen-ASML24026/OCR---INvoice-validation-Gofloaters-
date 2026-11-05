"""
Address extraction by POSITIVE evidence only.

An address is a run of consecutive lines/cells that ENDS in a PIN code (or a state
name / "India"). It is given to a party by the GSTIN printed right next to it (or the
GoFloaters name). Ship-To blocks are ignored. If there is no such block the address
stays None - leftover text (item descriptions, headers, bank details) is never used.
"""
import html
import re

from .normalize import (
    GSTIN_PATTERN,
    STATE_NAMES,
    clean,
    clean_party_name,
    is_valid_party_name,
    looks_like_address,
    looks_like_organization,
    state_from_gstin,
    state_from_text,
)

PIN = re.compile(r"\b[1-8]\d{5}\b")
_STATES = "|".join(re.escape(s) for s in sorted(STATE_NAMES, key=len, reverse=True))
STATE_RE = re.compile(r"\b(?:" + _STATES + r"|india)\b", re.I)
# after the PIN an address may still carry "Tamil Nadu" and/or "India"
PIN_TAIL = re.compile(r"\s*,?\s*(?:(?:" + _STATES + r")\b)?\s*,?\s*(?:india\b)?", re.I)

JUNK = re.compile(
    r"\b(invoice|amount|qty|quantity|hsn|sac|rate|description|subject|booking|terms|conditions|"
    r"bank|a/c|account|ifsc|swift|escrow|total|subtotal|cgst|sgst|igst|gst|gstin|tax|date|due|item|"
    r"place of supply|pan|cin|email|e-mail|phone|mobile|tel|website|www|signature|authori[sz]ed|"
    r"balance|notes|payment|checks|drafts|transfers|transfer|favouring|payable|micr|rtgs|neft|"
    r"charges?|utility|utilities|desk|beverages?|printing|prinitng|dedicated|rental|month\s+of|bill\s+for)\b", re.I)
LABEL_ONLY = re.compile(
    r"(?:bill(?:ed|ing)?\s*(?:to|from|by)|ship(?:ping)?\s*to|deliver(?:y)?\s*to|"
    r"billing\s*address|shipping\s*address|registered\s*address|place\s*of\s*supply|place\s*of\s*delivery|"
    r"customer(?:\s*details)?|supplier(?:\s*details)?|party(?:\s*details)?|vendor(?:\s*details)?|"
    r"details\s*of\s*(?:supplier|receiver|buyer|seller|recipient)|buyer|seller|from|to|address)\s*[:\-]?", re.I)
SHIP_LABEL = re.compile(r"(?:ship(?:ping)?|deliver(?:y)?)\s*to", re.I)
ORG_ONLY = re.compile(r"[A-Za-z0-9&.,()' -]{3,80}\b(?:limited|ltd\.?|llp|pvt\.?\s*ltd\.?|private\s+limited|inc\.?)\.?", re.I)
ORG_PREFIX = re.compile(r"^.{3,80}?\b(?:pvt\.?\s*ltd\.?|private\s+limited|limited|llp|inc\.?)\b[\s,.:;-]*", re.I)
LABEL_PREFIX = re.compile(
    r"^\s*(?:trade\s*name|bill(?:ed|ing)?\s*(?:to|from|by)|billing\s*address|shipping\s*address|registered\s*address|"
    r"place\s*of\s*supply|place\s*of\s*delivery|details\s*of\s*(?:supplier|receiver|buyer|seller|recipient)\s*(?:\([^)]*\))?|"
    r"customer(?:\s*details)?|supplier(?:\s*details)?|vendor(?:\s*details)?|party(?:\s*details)?|"
    r"buyer|seller|address|from|to)\s*[:\-]?\s*", re.I)
GST_LABEL = re.compile(r"\b(?:gstin|gst|uin|uid)(?:\s*[/\\&]\s*(?:gstin|gst|uin|uid))*\b\s*[:.\-]?\s*", re.I)
META_WORDS = re.compile(r"\b(?:state(?:\s*name)?|code|uin|uid|gstin?|gst|email|e-mail|phone|tel|mobile|pan|cin)\b", re.I)
HINTS = ("gofloaters", "go floaters", "smbsure", "smb sure", "gofloters", "go floter")
MAX_LINES = 8

RE_WALK_STATE_TAGS = re.compile(r"\b(?:tn|mh|ka|dl|ts|wb|gj|up|hr|rj)\s*\(\d{2}\)|\b[A-Za-z]{2,}\s*\(\d{2}\)", re.I)
RE_WALK_CURRENCY = re.compile(r"(?:₹|\$|€|INR|Rs\.?)\s*\d")
RE_WALK_DATE = re.compile(r"\b\d{1,2}[-/.](?:[A-Za-z]{3,}|\d{1,2})[-/.](?:19\d{2}|20\d{2})\b")
RE_PUNCT_NUM_ONLY = re.compile(r"[\d\s.,/-]+")

NOT_OPERATOR_WORDS = (
    "invoice", "tax", "bill", "receipt", "date", "due", "customer", "buyer", "ship",
    "total", "amount", "gst", "sl no", "ifsc", "bank", "account", "a/c", "neft", "rtgs",
    "micr", "swift", "branch", "favouring", "payable", "terms", "conditions", "notes",
    "code", "yesb", "hdfc", "icici", "icic", "sbi", "axis", "kotak", "canara", "punjab", "idbi", "baroda",
    "balance", "payment", "subtotal", "sub total",
    "original copy", "duplicate copy", "triplicate copy", "copy",
    "co-work", "cowork", "coworking", "meeting room", "conference room", "hot desk", "day pass"
)

PHYSICAL_ADDR_WORDS = re.compile(
    r"\b(?:road|street|st\b|rd\b|cross|lane|floor|flr\b|building|bldg\b|nagar|layout|estate|"
    r"sector|block|blk\b|plot|opp\b|opposite|near|house|flat|door|apt\b|apartment|complex|"
    r"premises|industrial|indl\b|ind\.?\s*estate|marg|circle|colony|sarani|bazaar|bazar|chowk|salai)\b", re.I)


def _mark(p):
    no_img = re.sub(r"<!--.*?-->", "", p)
    return clean(re.sub(r"^[#>*\s]+|\*+", "", no_img))                  # markdown markers


def _cells(text):
    """
    Reading-order cells. Markdown tables are read COLUMN by column (merged-cell repeats skipped), so a
    "Bill To" block sitting beside an "Invoice No / Date" block is not interleaved with it.
    """
    out, table = [], []

    def flush():
        rows = [[_mark(c) for c in r] for r in table]
        table.clear()
        for ci in range(max((len(r) for r in rows), default=0)):
            prev = None
            for r in rows:
                v = r[ci] if ci < len(r) else ""
                left = r[ci - 1] if 0 < ci <= len(r) else None
                if v and v != left and v != prev:
                    out.append(v)
                    prev = v

    for line in html.unescape(text).splitlines():
        if not line.strip() or re.fullmatch(r"[\s|:\-]*", line):
            continue
        if line.lstrip().startswith("|"):
            table.append(line.strip().strip("|").split("|"))
            continue
        if table:
            flush()
        p = _mark(line)
        if p:
            out.append(p)
    if table:
        flush()
    return out


ORG_WORDS = re.compile(r"\b(?:pvt|ltd|limited|llp|inc|associates|enterprises|solutions|technologies|services|company)\b", re.I)


def _key(v):
    return re.sub(r"[^a-z0-9]", "", (v or "").lower())


def _is_name_line(line, name):
    """A heading line that is the party's name, not part of its address."""
    scrubbed = LABEL_PREFIX.sub("", clean(line)).strip()
    n, m = _key(scrubbed), _key(name)
    if m and len(n) >= 2 and (n == m or (len(m) >= 3 and m in n) or (len(n) >= 3 and n in m)):
        return True
    if LABEL_ONLY.fullmatch(line.strip()) or LABEL_ONLY.fullmatch(scrubbed):
        return True
    ends_with_org = re.search(ORG_WORDS.pattern + r"\.?\s*$", scrubbed, re.I)
    return bool(ends_with_org) and not PIN.search(scrubbed) and not re.search(r"\d", scrubbed)


def _scrub(cell):
    """Remove image comments, GSTIN value and its label so they don't count as junk inside an address cell."""
    no_img = re.sub(r"<!--.*?-->", " ", cell or "")
    return clean(GST_LABEL.sub(" ", GSTIN_PATTERN.sub(" ", no_img)))


def _walkable(cell):
    """Can this line be part of an address block (when walking up from the PIN line)?"""
    c = _scrub(cell)
    if not c or len(c) > 260 or JUNK.search(c):
        return False
    if LABEL_ONLY.fullmatch(c) or ORG_ONLY.fullmatch(c):
        return False
    if PIN.search(c):
        return True
    # Stop address boundary walks immediately upon encountering dates, currency prefixes, or state code tags (e.g., TN (33))
    if RE_WALK_STATE_TAGS.search(c) or RE_WALK_CURRENCY.search(c) or RE_WALK_DATE.search(c):
        return False
    return not RE_PUNCT_NUM_ONLY.fullmatch(c)


def _tidy(joined):
    joined = re.sub(r"<!--.*?-->", " ", joined or "")
    joined = GSTIN_PATTERN.sub(" ", joined)
    joined = GST_LABEL.sub(" ", joined)
    joined = re.sub(r"(?i)\bstate\s*name\s*[:\-]?\s*", "", joined)
    joined = re.sub(r"(?i)\s*,?\s*code\s*[:\-]?\s*\d+\b", "", joined)
    joined = LABEL_PREFIX.sub("", clean(joined))
    m = ORG_PREFIX.match(joined)
    if m and PIN.search(joined[m.end():]):
        joined = joined[m.end():]                        # "Acme Pvt Ltd 3rd Floor ..." -> drop the name
    m = PIN.search(joined)
    if m:                                                # address ends at PIN (+ state / India)
        end = m.end() + PIN_TAIL.match(joined, m.end()).end() - m.end()
        joined = joined[:end]
    return clean(joined).strip(" ,;|:-/") or None


def valid_address(addr):
    """Sanity gate for any address, whatever layer produced it."""
    if not addr or len(addr) > 260 or JUNK.search(addr):
        return False
    if PIN.search(addr):
        return True
    st = state_from_text(addr)
    if st:
        rest = re.sub(r"\b\d+\b", " ", STATE_RE.sub(" ", addr))
        rest = META_WORDS.sub(" ", rest)
        return len(re.findall(r"[A-Za-z]{3,}", rest)) >= 2
    return False


def find_blocks(cells):
    blocks, used_until = [], -1
    for i, raw in enumerate(cells):
        cell = _scrub(raw)
        if i <= used_until or not _walkable(raw):
            continue
        if not (PIN.search(cell) or STATE_RE.search(cell) or state_from_text(cell)):
            continue
        end = i
        if i + 1 < len(cells) and re.fullmatch(r"india\.?", cells[i + 1], re.I):
            end = i + 1                                   # country on its own line
        j = i
        while j - 1 >= 0 and i - (j - 1) < MAX_LINES and _walkable(cells[j - 1]) \
                and not PIN.search(_scrub(cells[j - 1])):
            if re.search(r"\b(?:client\s*(?:registered\s*)?address|vendor\s*(?:registered\s*)?address|customer\s*address|supplier\s*address|billing\s*address|shipping\s*address|registered\s*address|place\s*of\s*supply|place\s*of\s*delivery)\b", cells[j - 1], re.I):
                break
            if re.search(r"\b(?:bill(?:ed|ing)?\s*(?:from|by|to)|supplier(?:\s*details)?|vendor(?:\s*details)?|customer(?:\s*details)?|party(?:\s*details)?)\b", cells[j - 1], re.I):
                break
            if LABEL_ONLY.fullmatch(cells[j - 1].strip()) or ORG_ONLY.fullmatch(cells[j - 1].strip()):
                break
            if j - 2 >= 0 and re.search(r"\bplace\s*of\s*supply\b", cells[j - 2], re.I):
                break
            c_prev = _scrub(cells[j - 1])
            if re.search(r"\b[A-Za-z]{2,}\s*\(\d{2}\)", c_prev) or re.search(r"(?:₹|\$|€|INR|Rs\.?)\s*\d", c_prev) or re.search(r"\b\d{1,2}[-/.](?:[A-Za-z]{3,}|\d{1,2})[-/.]\d{2,4}\b", c_prev):
                break
            j -= 1
        addr = _tidy(" ".join(_scrub(c) for c in cells[j: end + 1]))
        if addr and valid_address(addr):
            is_bank = any(
                re.search(r"\b(?:bank\s*address|branch\s*address|bank\s*branch)\b", cells[k], re.I)
                for k in range(max(0, j - 1), end + 1)
            )
            if is_bank:
                continue
            is_ship = any(SHIP_LABEL.search(_scrub(cells[k])) for k in range(max(0, j - 3), j))
            is_bill = any(re.search(r"\b(?:bill\s*to|billed\s*to|buyer|client|customer|invoice\s*to)\b", _scrub(cells[k]), re.I) for k in range(max(0, j - 3), j))
            if is_bill:
                is_ship = False
            block_text = " ".join(cells[j: end + 1]).lower()
            context_text = " ".join(cells[max(0, j - 3): j]).lower()
            if any(h in block_text for h in HINTS) or any(h in context_text for h in HINTS):
                is_ship = False
            blocks.append({"start": j, "end": end, "address": addr, "lines": cells[j: end + 1],
                           "ship_to": is_ship})
            used_until = end
    return blocks


def _distance(block, k):
    """GSTIN printed just after an address is the normal layout; before it costs a little more."""
    return k - block["end"] if k > block["end"] else (block["start"] - k) + 1


def fill_addresses(doc, text):
    """Set operator/gofloaters address from evidence. Strong evidence overrides earlier layers."""
    # Check for side-by-side or labeled vendor & client names
    m_names = re.search(
        r'(?:Vendor|Supplier|Seller|Operator)\s*Name\s*[:\-]?\s*(.*?)\s*(?:Client|Customer|Buyer)\s*Name\s*[:\-]?\s*(.*)',
        text,
        re.I,
    )
    if m_names:
        v_name = clean(m_names.group(1)).strip(" ,;-")
        c_name = clean(m_names.group(2)).strip(" ,;-")
        if v_name and (not doc["operator"].get("name") or doc["operator"]["name"] in ("GoFloaters", "Vendor Registered Address")):
            doc["operator"]["name"] = v_name
        if c_name and (not doc["gofloaters"].get("name") or doc["gofloaters"]["name"] == "GoFloaters"):
            doc["gofloaters"]["name"] = c_name

    # Check for labeled vendor & client addresses
    m_addrs = re.search(
        r'(?:Vendor|Supplier|Seller)\s*(?:Registered\s*)?Address\s*[:\-]?\s*([\s\S]*?)\s*(?:Client|Customer|Buyer)\s*(?:Registered\s*)?Address\s*[:\-]?\s*([\s\S]*?)(?=(?:Vendor|Client|Customer|Buyer)?\s*(?:GST|PAN|SAC|Phone|Email|Billing|\d{2}[A-Z]{4,5})|\Z)',
        text,
        re.I,
    )
    if m_addrs:
        v_addr = clean(" ".join(m_addrs.group(1).split())).strip(" ,;-")
        c_addr = clean(" ".join(m_addrs.group(2).split())).strip(" ,;-")
        if v_addr and valid_address(v_addr) and not doc["operator"].get("address"):
            doc["operator"]["address"] = v_addr
        if c_addr and valid_address(c_addr) and not doc["gofloaters"].get("address"):
            doc["gofloaters"]["address"] = c_addr
        if doc["operator"].get("address") and doc["gofloaters"].get("address"):
            return

    for party in ("operator", "gofloaters"):
        addr = _tidy(doc[party].get("address") or "")   # cut at first PIN: one address only
        doc[party]["address"] = addr if valid_address(addr) else None

    cells = _cells(text)
    gstin_at = {}
    for k, c in enumerate(cells):
        m = GSTIN_PATTERN.search(c.upper())
        if m:
            gstin_at[k] = m.group(0)

    blocks = [b for b in find_blocks(cells) if not b["ship_to"]]
    gstin_party = {doc["gofloaters"].get("gstin"): "gofloaters", doc["operator"].get("gstin"): "operator"}
    gstin_party.pop(None, None)

    ranked = []
    for b in blocks:
        b_state = state_from_text(b["address"])
        context = " ".join(cells[max(0, b["start"] - 3): b["start"]]).lower()
        is_gf = (
            any(h in context for h in HINTS)
            or any(h in b["address"].lower() for h in HINTS)
            or any(h in " ".join(b["lines"]).lower() for h in HINTS)
            or any(re.search(r"\b(?:bill\s*to|billed\s*to|buyer|client|customer|invoice\s*to)\b", cells[k], re.I) for k in range(max(0, b["start"] - 3), b["start"]))
            or bool(doc["gofloaters"].get("name") and len(doc["gofloaters"]["name"]) >= 3 and any(doc["gofloaters"]["name"].lower() in line.lower() for line in b["lines"]))
        )
        for k, g in gstin_at.items():
            party = gstin_party.get(g)
            if not party:
                continue
            if party == "operator" and is_gf:
                continue  # Never bind a customer address block to operator
            d = _distance(b, k)
            g_state = state_from_gstin(g)
            if b_state and g_state:
                if b_state == g_state:
                    d -= 3
                else:
                    d += 15
            is_stub = len(b["address"]) < 20 and not re.search(r"\b(?:estate|street|road|floor|nagar|block|plot|sector|lane|marg|avenue|cross|layout|phase)\b", b["address"], re.I)
            if is_stub:
                d += 5
            max_d = 12 if (b_state and g_state and b_state == g_state) else 6
            if d <= max_d:
                ranked.append((d, -len(b["address"]), b["start"], party, b, "gstin_nearby"))
        if is_gf:
            is_stub = len(b["address"]) < 20 and not re.search(r"\b(?:estate|street|road|floor|nagar|block|plot|sector|lane|marg|avenue|cross|layout|phase)\b", b["address"], re.I)
            d_hint = 6 if is_stub else 1
            g_state = state_from_gstin(doc["gofloaters"].get("gstin"))
            if b_state and g_state:
                if b_state == g_state:
                    d_hint = 0
                else:
                    d_hint = 15
            if doc["operator"].get("name") and len(doc["operator"]["name"]) > 3 and doc["operator"]["name"].lower() in b["address"].lower():
                d_hint += 10
            ranked.append((d_hint, -len(b["address"]), b["start"], "gofloaters", b, "name_hint"))
    ranked.sort(key=lambda r: (r[0], r[1], r[2]))

    owned = {}
    for _, _, _, party, b, how in ranked:
        if party not in owned and all(b is not o[0] for o in owned.values()):
            owned[party] = (b, how)

    if "operator" not in owned:                          # weak: first non-GoFloaters, non-owned block
        taken = [o[0] for o in owned.values()]
        for b in blocks:
            if all(b is not t for t in taken):
                owned["operator"] = (b, "first_block_not_gofloaters")
                break

    evidence = {}
    for party, (b, how) in owned.items():
        strong = how != "first_block_not_gofloaters"
        # Reset invalid party names like "Sub Total 960.00" or "Vendor Registered Address"
        if party == "operator" and doc["operator"].get("name") and not is_valid_party_name(doc["operator"]["name"], for_party="operator"):
            doc["operator"]["name"] = None

        if b["start"] > 0 and (doc[party].get("name") in (None, "", "GoFloaters") or not is_valid_party_name(doc[party].get("name"), for_party=party)):
            head_raw = clean_party_name(clean(LABEL_PREFIX.sub("", cells[b["start"] - 1])))
            head_cand = (head_raw or "").strip(" ,;|:-()")
            if b["start"] > 1:
                prev_raw = clean_party_name(clean(LABEL_PREFIX.sub("", cells[b["start"] - 2])))
                prev_cand = (prev_raw or "").strip(" ,;|:-()")
                comb = f"{prev_cand} {head_cand}".strip()
                if looks_like_organization(comb) and is_valid_party_name(comb, for_party=party):
                    head_cand = comb
            if not is_valid_party_name(head_cand, for_party=party):
                head_cand = ""
            if ORG_ONLY.fullmatch(head_cand) or (len(head_cand) > 3 and ORG_WORDS.search(head_cand) and not PIN.search(head_cand)):
                doc[party]["name"] = head_cand
            elif party == "operator" and is_valid_party_name(head_cand, for_party="operator") and not looks_like_address(head_cand) and 3 <= len(head_cand) <= 60 and not PIN.search(head_cand):
                low_h = head_cand.lower()
                has_letters = len(re.findall(r"[A-Za-z]", head_cand)) >= 3
                is_num_pat = bool(re.search(r"\d+[/_-]\d+", head_cand))
                if has_letters and not is_num_pat and not any(w in low_h for w in NOT_OPERATOR_WORDS) and not re.search(r"\d{3,}", head_cand):
                    doc[party]["name"] = head_cand


        raw_lines = [clean(re.sub(r"<!--.*?-->", "", l)) for l in b["lines"]]
        lines = [l for l in raw_lines if l]
        if len(lines) > 1 and (doc[party].get("name") in (None, "", "GoFloaters") or not is_valid_party_name(doc[party].get("name"), for_party=party)):
            first_cand = clean_party_name(clean(LABEL_PREFIX.sub("", lines[0]))).strip(" ,;|:-()")
            if is_valid_party_name(first_cand, for_party=party):
                if ORG_ONLY.fullmatch(first_cand) or (len(first_cand) > 3 and ORG_WORDS.search(first_cand) and not PIN.search(first_cand)):
                    doc[party]["name"] = first_cand
                elif party == "operator" and 3 <= len(first_cand) <= 60 and not PIN.search(first_cand):
                    low_f = first_cand.lower()
                    has_letters = len(re.findall(r"[A-Za-z]", first_cand)) >= 3
                    is_num_pat = bool(re.search(r"\d+[/_-]\d+", first_cand))
                    if has_letters and not is_num_pat and not PHYSICAL_ADDR_WORDS.search(low_f) and not re.search(r"\d", first_cand) and not any(w in low_f for w in NOT_OPERATOR_WORDS):
                        doc[party]["name"] = first_cand

        while len(lines) > 1 and _is_name_line(_scrub(lines[0]), doc[party].get("name")):
            lines.pop(0)                                  # the letterhead name is not part of the address
        addr = _tidy(" ".join(_scrub(c) for c in lines))
        if addr:
            addr = re.sub(r"\b(Chennai|Mumbai|Kolkata|Bangalore)\s+\1\b", r"\1", addr, flags=re.I)
        b = {**b, "address": addr if addr and valid_address(addr) else b["address"]}
        if strong or not doc[party].get("address"):
            doc[party]["address"] = b["address"]
            evidence[f"{party}.address"] = {"method": how, "lines": lines}
    if evidence:
        doc.setdefault("evidence", {}).update(evidence)
    for party in ("operator", "gofloaters"):
        if doc[party].get("name"):
            doc[party]["name"] = clean_party_name(doc[party]["name"])
        if doc[party].get("address"):
            doc[party]["address"] = clean_party_address(doc[party]["address"], doc[party].get("name"))


def clean_party_address(addr, party_name=None):
    """Strip party name, entity suffixes, and field prefixes from an address."""
    if not addr or not isinstance(addr, str):
        return addr
    a = clean(addr)
    for _ in range(3):
        a = LABEL_PREFIX.sub("", a).strip(" ,;:-|/")
        a = re.sub(r"(?i)^\s*(?:registration\s*(?:no|number)?|reg\s*no\.?)\s*[-:]?\s*", "", a).strip(" ,;:-|/")

    if party_name and len(party_name) >= 3:
        p_name = clean(party_name)
        if a.lower().startswith(p_name.lower()):
            a = a[len(p_name):].strip(" ,;:-|/")
        else:
            key_p = _key(p_name)
            key_a = _key(a)
            if key_p and key_a.startswith(key_p):
                matched = 0
                cut_idx = 0
                for idx, ch in enumerate(a):
                    if ch.isalnum():
                        matched += 1
                        if matched == len(key_p):
                            cut_idx = idx + 1
                            break
                if cut_idx > 0:
                    a = a[cut_idx:].strip(" ,;:-|/")

    m = ORG_PREFIX.match(a)
    if m and PIN.search(a[m.end():]):
        a = a[m.end():].strip(" ,;:-|/")

    a = LABEL_PREFIX.sub("", a).strip(" ,;:-|/")
    return clean(a) or None

