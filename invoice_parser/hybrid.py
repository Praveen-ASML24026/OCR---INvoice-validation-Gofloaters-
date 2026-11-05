"""
Hybrid Invoice Processor
Routes PDF documents through ultra-fast native text extraction (~5-30ms)
and routes Images (PNG, JPG, TIFF, WebP) through the existing Docling OCR architecture.
Also falls back to Docling OCR if a PDF is scanned (has no digital text layer).

Usage via CLI:
    python -m invoice_parser.hybrid [inputDir] [outputDir] [--structured]
"""
import argparse
import csv
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pypdfium2 as pdfium

from .converter import SUPPORTED, convert_document
from .extractor import extract_document
from .fallback import apply_fallbacks
from .normalize import normalize_document
from .semantic import build_semantic_candidates
from .validators import validate_document

# Configure dedicated file logging for invoice timestamps (matching main.py)
LOG_FILE = Path("invoice_parser.log").resolve()
logger = logging.getLogger("invoice_parser")
logger.setLevel(logging.INFO)


class UnbufferedFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()


if not any(isinstance(h, logging.FileHandler) and Path(getattr(h, "baseFilename", "")).name == "invoice_parser.log" for h in logger.handlers):
    _fh = UnbufferedFileHandler(LOG_FILE, encoding="utf-8")
    _fh.setLevel(logging.INFO)
    _fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(_fh)

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
PDF_EXTENSIONS = {".pdf"}


def extract_pdf_fast(file_path: Path) -> Dict[str, Any]:
    """
    Extracts embedded digital text from PDF in milliseconds using pypdfium2.
    Returns text, page count, timing in ms, and whether valid text was found.
    """
    start = time.perf_counter()
    doc = pdfium.PdfDocument(file_path)
    try:
        total_pages = len(doc)
        page_texts: List[str] = []

        for page in doc:
            textpage = page.get_textpage()
            text = textpage.get_text_range() or ""
            textpage.close()
            page.close()
            page_texts.append(text)

        full_text = "\n\n".join(page_texts)
    finally:
        doc.close()
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    chars = len(full_text.strip())
    has_text = chars > 0

    return {
        "text": full_text,
        "pages": total_pages,
        "parse_time_ms": elapsed_ms,
        "text_chars": chars,
        "has_text": has_text,
        "engine": "fast_pdf_native",
    }


def extract_image_docling(file_path: Path) -> Dict[str, Any]:
    """
    Routes image files (PNG/JPG/etc.) through the existing Docling OCR pipeline.
    """
    start = time.perf_counter()
    docling_doc = convert_document(file_path)
    extracted = extract_document(docling_doc)
    text = extracted.get("markdown") or "\n".join(t.get("text", "") for t in extracted.get("texts", []))
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    chars = len(text.strip())

    return {
        "text": text,
        "pages": 1,
        "parse_time_ms": elapsed_ms,
        "text_chars": chars,
        "has_text": chars > 0,
        "engine": "docling_ocr",
        "docling_doc": docling_doc,
        "extracted": extracted,
    }


def process_hybrid_document(
    file_path: Path,
    fallback_scanned_to_docling: bool = True,
    extract_structured_data: bool = False,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main routing flow:
    - If PDF:
        1. Fast text extraction (~5-30ms).
        2. If PDF has text -> completes immediately.
        3. If PDF has NO text (scanned) and fallback enabled -> routes to Docling OCR.
    - If Image (PNG, JPG, etc.):
        Routes directly through existing Docling OCR architecture.
    """
    path = Path(file_path)
    doc_name = display_name or path.name
    suffix = path.suffix.lower()
    start_total = time.perf_counter()

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported file format: {suffix}")

    logger.info(f"START | {doc_name} | flow=hybrid")

    # Flow 1: PDF Files
    if suffix in PDF_EXTENSIONS:
        res = extract_pdf_fast(path)
        d_fast = res["parse_time_ms"] / 1000.0
        logger.info(f"STEP 1 | {doc_name} | fast_pdf_time={d_fast:.4f}s | chars={res['text_chars']} | pages={res['pages']}")

        # If digital PDF with text, we are done
        if res["has_text"]:
            if extract_structured_data:
                res["structured"] = parse_text_to_structured(res["text"])
            total_time = time.perf_counter() - start_total
            logger.info(f"END | {doc_name} | engine=fast_pdf_native | status=ok | processing_time={total_time:.4f}s")
            return res

        # Scanned PDF without text layer: Fallback to existing Docling architecture
        if fallback_scanned_to_docling:
            logger.info(f"FALLBACK | {doc_name} | scanned_pdf_to_docling_ocr")
            t0 = time.perf_counter()
            docling_res = extract_image_docling(path)
            d_docling = time.perf_counter() - t0
            logger.info(f"STEP 1_FALLBACK | {doc_name} | conversion_ocr_time={d_docling:.2f}s")
            docling_res["engine"] = "docling_ocr_scanned_pdf_fallback"
            if extract_structured_data:
                docling_res["structured"] = run_existing_pipeline_on_extracted(
                    docling_res["extracted"]
                )
            total_time = time.perf_counter() - start_total
            logger.info(f"END | {doc_name} | engine=docling_ocr_scanned_pdf_fallback | status=ok | processing_time={total_time:.2f}s")
            return docling_res

        total_time = time.perf_counter() - start_total
        logger.info(f"END | {doc_name} | engine=fast_pdf_native | status=no_text | processing_time={total_time:.4f}s")
        return res

    # Flow 2: Image Files -> Existing Architecture
    if suffix in IMAGE_EXTENSIONS:
        t0 = time.perf_counter()
        res = extract_image_docling(path)
        d_conv = time.perf_counter() - t0
        logger.info(f"STEP 1 | {doc_name} | conversion_ocr_time={d_conv:.2f}s")
        if extract_structured_data:
            res["structured"] = run_existing_pipeline_on_extracted(res["extracted"])
        total_time = time.perf_counter() - start_total
        logger.info(f"END | {doc_name} | engine=docling_ocr | status=ok | processing_time={total_time:.2f}s")
        return res

    # Other Office formats (DOCX, XLSX, HTML) -> Existing Architecture
    res = extract_image_docling(path)
    total_time = time.perf_counter() - start_total
    logger.info(f"END | {doc_name} | engine=docling_default | status=ok | processing_time={total_time:.2f}s")
    return res


def run_existing_pipeline_on_extracted(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Runs Step 3 to Step 6 of existing architecture."""
    semantic = build_semantic_candidates(extracted)
    normalized = normalize_document(semantic, extracted)
    apply_fallbacks(normalized, extracted)
    normalized["validation"] = validate_document(normalized)
    return normalized


def parse_text_to_structured(text: str) -> Dict[str, Any]:
    """
    Parses fast extracted text directly through our fallback regex and validation rules.
    """
    extracted = {
        "texts": [{"text": line} for line in text.splitlines() if line.strip()],
        "tables": [],
        "pictures": [],
        "markdown": text,
    }
    doc = {
        "invoice": {"number": None, "date": None, "due_date": None, "place_of_supply": None},
        "operator": {"name": None, "address": None, "state": None, "gstin": None},
        "gofloaters": {"name": None, "address": None, "state": None, "gstin": None},
        "tax": {"taxable_amount": None, "cgst": None, "sgst": None, "igst": None, "total": None},
        "line_items": [],
    }
    apply_fallbacks(doc, extracted)
    doc["validation"] = validate_document(doc)
    return doc


def process_directory(
    input_dir: Path,
    output_dir: Path,
    extract_structured: bool = False,
) -> None:
    """
    Batch processes all documents in input_dir, writes <name>.txt to output_dir,
    and produces report.csv matching user's exact reporting specification.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    allowed = PDF_EXTENSIONS | IMAGE_EXTENSIONS
    files = sorted(f for f in input_path.iterdir() if f.suffix.lower() in allowed and f.is_file())

    if not files:
        print(f"No supported PDF or image files found in {input_path}")
        return

    print(f"\n[Hybrid Flow] Found {len(files)} files to process in {input_path}...")
    print(f"[Hybrid Flow] Writing outputs to {output_path}...\n")

    headers = ["file", "file_type", "pages", "parse_time_ms", "text_chars", "has_text", "engine", "status", "error"]
    rows: List[List[Any]] = [headers]

    for file in files:
        file_type = "pdf" if file.suffix.lower() == ".pdf" else "image"
        start = time.perf_counter()
        try:
            res = process_hybrid_document(
                file,
                fallback_scanned_to_docling=True,
                extract_structured_data=extract_structured,
            )
            text = res.get("text", "")
            pages = res.get("pages", 1)
            ms = res.get("parse_time_ms", round((time.perf_counter() - start) * 1000, 2))
            chars = res.get("text_chars", len(text.strip()))
            has_text = res.get("has_text", chars > 0)
            engine = res.get("engine", "hybrid")
            status = "ok" if has_text else "no_text"

            # Write <name>.txt
            out_txt = output_path / f"{file.stem}.txt"
            out_txt.write_text(text, encoding="utf-8")

            rows.append([file.name, file_type, pages, ms, chars, has_text, engine, status, ""])
            icon = "✓" if has_text else "⚠"
            detail = f"[{engine}] {pages} pages, {ms} ms, {chars} chars"
            if not has_text:
                detail += " — likely scanned"
            print(f"{icon} {file.name} ({detail})")

        except Exception as err:
            ms = round((time.perf_counter() - start) * 1000, 2)
            rows.append([file.name, file_type, "", ms, 0, False, "error", "error", str(err)])
            print(f"✗ {file.name} [ERROR: {err}]")

    report_path = output_path / "report.csv"
    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print(f"\n✓ Hybrid processing complete. Report saved → {report_path}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid PDF Fast / Image Docling Invoice Processor")
    parser.add_argument("input_path", nargs="?", default="./invoices", help="Input directory or single file")
    parser.add_argument("output_path", nargs="?", default="./output", help="Output directory for .txt and report.csv")
    parser.add_argument("--structured", action="store_true", help="Also extract and validate structured invoice fields")
    args = parser.parse_args()

    inp = Path(args.input_path)
    out = Path(args.output_path)

    if inp.is_file():
        # Single file execution
        res = process_hybrid_document(inp, extract_structured_data=args.structured)
        print(f"File: {inp.name}")
        print(f"Engine: {res['engine']}")
        print(f"Time: {res['parse_time_ms']} ms")
        print(f"Chars: {res['text_chars']}")
        print(f"Has Text: {res['has_text']}")
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{inp.stem}.txt").write_text(res["text"], encoding="utf-8")
        print(f"Saved text to: {out / f'{inp.stem}.txt'}")
    else:
        process_directory(inp, out, extract_structured=args.structured)


if __name__ == "__main__":
    main()
