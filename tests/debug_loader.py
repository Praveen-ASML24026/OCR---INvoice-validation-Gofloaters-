"""Rebuilds the extractor's output from a saved --debug .debug.md file (real Docling text + table grids)."""
import ast
from pathlib import Path


def load_debug(path):
    raw = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    markdown, _, grids = raw.partition("=== TABLE GRIDS ===")
    tables = []
    for line in grids.strip().splitlines():
        if line.startswith("table") and ":" in line:
            tables.append({"rows": ast.literal_eval(line.split(":", 1)[1].strip())})
    texts = []
    for l in markdown.splitlines():
        if l.strip() and not l.lstrip().startswith("|"):
            head = l.lstrip().startswith("#")
            texts.append({"text": l.lstrip("# ").strip(), "label": "section_header" if head else "text", "level": None})
    return {"texts": texts, "tables": tables, "pictures": [], "markdown": markdown.strip()}
