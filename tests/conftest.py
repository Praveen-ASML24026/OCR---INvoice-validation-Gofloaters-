"""Lets the tests run on machines without Docling installed (CI); real runs use the real package."""
import sys
import types

try:
    import docling  # noqa: F401
except ImportError:
    def stub(name, **attrs):
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        sys.modules[name] = mod
    anything = type("X", (), {"__init__": lambda self, *a, **k: None})
    stub("docling")
    stub("docling.datamodel")
    stub("docling.datamodel.base_models", InputFormat=types.SimpleNamespace(PDF=1, IMAGE=2))
    stub("docling.datamodel.pipeline_options", PdfPipelineOptions=anything, RapidOcrOptions=anything)
    stub("docling.document_converter", DocumentConverter=anything, PdfFormatOption=anything, ImageFormatOption=anything)
