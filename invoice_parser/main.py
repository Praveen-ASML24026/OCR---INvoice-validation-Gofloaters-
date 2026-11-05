import argparse
import json
import logging
import time
from pathlib import Path

from .confidence import calculate_confidence_scores
from .converter import SUPPORTED, convert_document
from .extractor import extract_document
from .fallback import apply_fallbacks
from .normalize import normalize_document
from .semantic import build_semantic_candidates
from .spatial import extract_spatial_pdf
from .text_tables import extract_tables_from_text
from .validators import validate_document

# Configure dedicated rotating file logging for invoice timestamps
LOG_FILE = Path("invoice_parser.log").resolve()
logger = logging.getLogger("invoice_parser")
logger.setLevel(logging.INFO)

if not any(isinstance(h, (logging.FileHandler, logging.handlers.RotatingFileHandler)) for h in logger.handlers):
    try:
        from logging.handlers import RotatingFileHandler
        _rfh = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        _rfh.setLevel(logging.INFO)
        _rfh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(_rfh)
    except (OSError, PermissionError):
        # Fallback to stderr on read-only environments
        import sys
        _sh = logging.StreamHandler(sys.stderr)
        _sh.setLevel(logging.INFO)
        _sh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(_sh)


def process(file_path, debug=False, display_name=None, fast_pdf=True, verbose=False, timeout=120.0, abort_event=None, keep_text=False):
    doc_name = display_name or Path(file_path).name
    suffix = Path(file_path).suffix.lower()
    start_time = time.perf_counter()
    vprint = print if verbose else (lambda *args, **kwargs: None)

    logger.info(f"START | {doc_name}")
    vprint(f"\n[Parser] >>> Starting processing for: {doc_name}", flush=True)

    try:
        # Check if file is a digital PDF that can bypass heavy Docling OCR
        is_pdf = suffix == ".pdf"
        use_fast = False
        is_corrupted = False
        raw_pdf_text = ""
        spatial_texts = []
        if is_pdf and fast_pdf:
            try:
                spatial_res = extract_spatial_pdf(file_path)
                is_corrupted = bool(spatial_res.get("corrupted_font"))
                raw_pdf_text = spatial_res["text"]
                spatial_texts = spatial_res["texts"]
                if len(raw_pdf_text.strip()) > 0:
                    use_fast = True
            except Exception as fast_err:
                logger.warning(f"Spatial fast PDF parse failed: {fast_err}")
                if "pdfium" in type(fast_err).__module__.lower() or "pdf" in type(fast_err).__name__.lower():
                    raise ValueError(f"Corrupted or invalid PDF document: {fast_err}") from fast_err
                use_fast = False

        if use_fast:
            # FAST DIGITAL PDF ROUTE: Spatial Layout Parse (No OCR/Docling) (~15-30ms)
            vprint("  [Step 1/6] Running Spatial Layout PDF Parse (No OCR/Docling)...", end="", flush=True)
            t0 = time.perf_counter()
            d_conv = time.perf_counter() - t0
            vprint(f" Done ({d_conv:.4f}s)", flush=True)
            logger.info(f"STEP 1 | {doc_name} | fast_pdf_time={d_conv:.4f}s")

            # Step 2: Structural Extraction from spatial layout stream
            vprint("  [Step 2/6] Extracting text spans & markdown...", end="", flush=True)
            t0 = time.perf_counter()
            parsed_tables = extract_tables_from_text(raw_pdf_text)
            extracted = {
                "texts": spatial_texts if spatial_texts else [{"text": line} for line in raw_pdf_text.splitlines() if line.strip()],
                "tables": parsed_tables,
                "pictures": [],
                "markdown": raw_pdf_text,
                "raw_text": spatial_res.get("raw_stream") or "\n\n".join(spatial_res.get("raw_pages", [])) or raw_pdf_text,
            }
            d_ext = time.perf_counter() - t0
            vprint(f" Done ({d_ext:.4f}s)", flush=True)
            logger.info(f"STEP 2 | {doc_name} | structural_extraction_time={d_ext:.4f}s")
        else:
            # EXISTING DOCLING ARCHITECTURE (IMAGES & SCANNED DOCUMENTS)
            doc_to_convert = file_path
            temp_cleaned_pdf = None
            if is_pdf and is_corrupted:
                from .preprocessor import preprocess_scanned_pdf
                temp_cleaned_pdf = preprocess_scanned_pdf(file_path)
                doc_to_convert = temp_cleaned_pdf

            vprint("  [Step 1/6] Running Document Conversion & OCR (Docling)...", end="", flush=True)
            t0 = time.perf_counter()
            try:
                document = convert_document(doc_to_convert, timeout=timeout, abort_event=abort_event)
            finally:
                if temp_cleaned_pdf is not None and temp_cleaned_pdf.exists():
                    try:
                        temp_cleaned_pdf.unlink(missing_ok=True)
                    except Exception:
                        pass
            d_conv = time.perf_counter() - t0
            vprint(f" Done ({d_conv:.2f}s)", flush=True)
            logger.info(f"STEP 1 | {doc_name} | conversion_ocr_time={d_conv:.2f}s")

            # Step 2: Structural Extraction
            vprint("  [Step 2/6] Extracting tables, text spans & markdown...", end="", flush=True)
            t0 = time.perf_counter()
            extracted = extract_document(document)
            d_ext = time.perf_counter() - t0
            vprint(f" Done ({d_ext:.2f}s)", flush=True)
            logger.info(f"STEP 2 | {doc_name} | structural_extraction_time={d_ext:.2f}s")

        if debug:
            dump = Path(file_path).with_suffix(".debug.md")
            rows = "\n".join(f"table{i}: {t['rows']}" for i, t in enumerate(extracted.get("tables", [])))
            dump.write_text(extracted.get("markdown", "") + "\n\n=== TABLE GRIDS ===\n" + rows, encoding="utf-8")
            vprint(f"  debug dump -> {dump}", flush=True)

        # Step 3: Semantic Detection (EXACT EXISTING ARCHITECTURE)
        vprint("  [Step 3/6] Detecting semantic table labels & candidates...", end="", flush=True)
        t0 = time.perf_counter()
        semantic = build_semantic_candidates(extracted)
        d_sem = time.perf_counter() - t0
        vprint(f" Done ({d_sem:.2f}s)", flush=True)
        logger.info(f"STEP 3 | {doc_name} | semantic_detection_time={d_sem:.2f}s")

        # Step 4: Normalization & Entities (EXACT EXISTING ARCHITECTURE)
        vprint("  [Step 4/6] Normalizing dates, amounts, GSTINs & parties...", end="", flush=True)
        t0 = time.perf_counter()
        normalized = normalize_document(semantic, extracted)
        d_norm = time.perf_counter() - t0
        vprint(f" Done ({d_norm:.2f}s)", flush=True)
        logger.info(f"STEP 4 | {doc_name} | normalization_time={d_norm:.2f}s")

        # Step 5: Fallbacks & Addresses
        vprint("  [Step 5/6] Applying regex fallbacks & address engine...", end="", flush=True)
        t0 = time.perf_counter()
        apply_fallbacks(normalized, extracted)
        d_fall = time.perf_counter() - t0
        vprint(f" Done ({d_fall:.2f}s)", flush=True)
        logger.info(f"STEP 5 | {doc_name} | fallbacks_addresses_time={d_fall:.2f}s")

        # Step 6: Validation
        vprint("  [Step 6/6] Validating GST compliance & business rules...", end="", flush=True)
        t0 = time.perf_counter()
        normalized["validation"] = validate_document(normalized)
        d_val = time.perf_counter() - t0
        vprint(f" Done ({d_val:.2f}s)", flush=True)
        logger.info(f"STEP 6 | {doc_name} | validation_time={d_val:.2f}s")

        # Step 7: Confidence Scoring (Key fields: invoice_number, taxable_amount, gstin, dates)
        try:
            normalized["confidence"] = calculate_confidence_scores(normalized)
        except Exception as conf_err:
            logger.warning(f"Confidence scoring failed: {conf_err}")
            normalized["confidence"] = None

        total_time = time.perf_counter() - start_time
        status = normalized.get("validation", {}).get("status", "unknown")
        logger.info(f"END | {doc_name} | status={status} | processing_time={total_time:.2f}s")

        # Log summary breakdown (only when verbose is True)
        if verbose:
            vprint(f"\n{'='*58}", flush=True)
            vprint(f" PIPELINE TIMING BREAKDOWN ({doc_name})", flush=True)
            vprint(f"{'='*58}", flush=True)
            steps = [
                ("Step 1: Conversion & OCR", d_conv),
                ("Step 2: Structural Extraction", d_ext),
                ("Step 3: Semantic Detection", d_sem),
                ("Step 4: Normalization & Entities", d_norm),
                ("Step 5: Fallbacks & Address Engine", d_fall),
                ("Step 6: Compliance Validation", d_val),
            ]
            for label, duration in steps:
                pct = (duration / total_time * 100) if total_time > 0 else 0
                vprint(f"  {label:<35}: {duration:6.2f}s  ({pct:5.1f}%)", flush=True)
            vprint(f"{'-'*58}", flush=True)
            vprint(f"  {'Total Processing Time':<35}: {total_time:6.2f}s", flush=True)
            vprint(f"{'='*58}\n", flush=True)

        normalized["step_timings_ms"] = {
            "step1_conversion_ocr": round(d_conv * 1000, 1),
            "step2_structural_extraction": round(d_ext * 1000, 1),
            "step3_semantic_detection": round(d_sem * 1000, 1),
            "step4_normalization": round(d_norm * 1000, 1),
            "step5_fallbacks_addresses": round(d_fall * 1000, 1),
            "step6_compliance_validation": round(d_val * 1000, 1),
            "total_elapsed_ms": round(total_time * 1000, 1),
        }

        if keep_text:
            normalized["_text"] = extracted.get("markdown") or extracted.get("raw_text") or ""

        return normalized

    except Exception as e:
        elapsed = time.perf_counter() - start_time
        logger.exception(f"FAILED | {doc_name} | processing_time={elapsed:.2f}s | error={str(e)}")
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="invoice file or a folder of invoices")
    ap.add_argument("--debug", action="store_true", help="write <file>.debug.md with what Docling read")
    ap.add_argument("--verbose", action="store_true", help="show step-by-step progress and timing breakdowns")
    ap.add_argument("--out", help="write JSON result here")
    args = ap.parse_args()

    p = Path(args.path)
    files = sorted(f for f in p.iterdir() if f.suffix.lower() in SUPPORTED) if p.is_dir() else [p]

    results = {}
    for f in files:
        if args.verbose:
            print(f"Processing {f.name} ...")
        try:
            results[f.name] = process(f, debug=args.debug, verbose=args.verbose)
        except Exception as exc:
            results[f.name] = {"error": str(exc)}

    output = results[files[0].name] if len(files) == 1 else results
    text = json.dumps(output, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
