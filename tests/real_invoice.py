"""Builds the same structure Docling's extractor produces, from a saved text fixture."""
from pathlib import Path

HEADER = ["#", "Item & Description", "HSN/SAC", "Qty", "Rate", "CGST", "SGST", "Amount"]
ITEM_ROWS = [
    ["1", "MEMBERSHIP FEES", "997212", "1.00", "720.00", "64.80 9%", "64.80 9%", "720.00"],
    ["", "Membership Fee for 01 day Passes for 01.09.2026", "", "", "", "", "", "720.00"],  # merged-cell repeat
]


def load(name, table_rows=None):
    lines = [l.rstrip("\n") for l in (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8").splitlines()]
    rows = [HEADER] + (table_rows if table_rows is not None else ITEM_ROWS)
    md_table = "\n".join("| " + " | ".join(r) + " |" for r in rows)
    markdown = "\n".join(lines[:-6] + [md_table] + lines[-6:])
    return {"texts": [{"text": l, "label": None, "level": None} for l in lines if l.strip()],
            "tables": [{"rows": rows}], "pictures": [], "markdown": markdown}
