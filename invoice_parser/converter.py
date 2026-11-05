import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

SUPPORTED = {
    ".pdf", ".docx", ".pptx", ".xlsx",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
}

_ocr_lock = threading.Lock()


class AbortableOCRLock:
    """Acquires the shared OCR lock with abort signal checking to prevent orphaned threads."""
    def __init__(self, lock: threading.Lock, timeout: float = 120.0, abort_event: Optional[threading.Event] = None):
        self.lock = lock
        self.timeout = timeout
        self.abort_event = abort_event
        self.acquired = False

    def __enter__(self):
        start = time.perf_counter()
        while True:
            if self.abort_event and self.abort_event.is_set():
                raise TimeoutError("Execution cancelled before acquiring OCR lock.")
            if self.lock.acquire(timeout=0.25):
                self.acquired = True
                if self.abort_event and self.abort_event.is_set():
                    self.lock.release()
                    self.acquired = False
                    raise TimeoutError("Execution cancelled after acquiring OCR lock.")
                return self
            if (time.perf_counter() - start) >= self.timeout:
                raise TimeoutError(f"Timed out after {self.timeout}s waiting for OCR engine lock.")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.acquired:
            self.lock.release()
            self.acquired = False


@lru_cache(maxsize=2)
def create_converter(force_ocr=False):
    """Built once and reused (loading the models is the slow part)."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    try:  # image support (png/jpg/tiff/bmp) - available in recent Docling
        from docling.document_converter import ImageFormatOption
    except ImportError:  # pragma: no cover
        ImageFormatOption = None

    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = True
    pdf_options.do_table_structure = True
    ocr_options = RapidOcrOptions()
    if force_ocr:
        ocr_options.force_full_page_ocr = True    # a field in older Docling, a writable property in newer ones
    pdf_options.ocr_options = ocr_options

    format_options = {InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)}
    if ImageFormatOption is not None:
        format_options[InputFormat.IMAGE] = ImageFormatOption(pipeline_options=pdf_options)

    # DOCX / XLSX / PPTX use Docling's defaults (no OCR needed).
    return DocumentConverter(format_options=format_options)


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def convert_document(file_path, timeout: float = 120.0, abort_event: Optional[threading.Event] = None):
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if file_path.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Unsupported file type: {file_path.suffix}")

    actual_path = file_path
    temp_cleaned = None
    if file_path.suffix.lower() in IMAGE_EXTENSIONS:
        try:
            from .preprocessor import preprocess_image_file_to_temp
            temp_cleaned = preprocess_image_file_to_temp(file_path)
            actual_path = temp_cleaned
        except Exception:
            actual_path = file_path

    try:
        with AbortableOCRLock(_ocr_lock, timeout=timeout, abort_event=abort_event):
            if abort_event and abort_event.is_set():
                raise TimeoutError("Execution cancelled before starting OCR conversion.")
            document = create_converter().convert(actual_path).document
            if file_path.suffix.lower() == ".pdf":
                bad = _garbled(document)
                if bad:      # broken font mapping (G -> U+FFFD): read the page as an image instead of its text layer
                    try:
                        redo = create_converter(True).convert(actual_path).document
                        if _garbled(redo) < bad:
                            document = redo
                    except Exception:
                        pass
            return document
    finally:
        if temp_cleaned is not None and temp_cleaned.exists():
            try:
                temp_cleaned.unlink(missing_ok=True)
            except Exception:
                pass


def _garbled(document):
    try:
        return document.export_to_markdown().count("\ufffd")
    except Exception:
        return 0
