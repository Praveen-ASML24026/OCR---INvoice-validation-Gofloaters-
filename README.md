# OCR-Invoice-validation-Gofloaters-
Rule-based invoice parser using Docling + RapidOCR. Extracts operator, GoFloaters, invoice and tax fields from PDF/DOCX/JPEG/PNG invoices, with evidence for each field, and validates GST rules. No LLM.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141.1-009688.svg)](https://fastapi.tiangolo.com/)
[![Docling](https://img.shields.io/badge/Docling-Layout%20Analysis-orange.svg)](https://github.com/DS4SD/docling)
[![RapidOCR](https://img.shields.io/badge/RapidOCR-ONNX%20Runtime-red.svg)](https://github.com/RapidAI/RapidOCR)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📌 Overview

The **GoFloaters Enterprise Invoice Parser (v2.0)** is an automated document layout analysis and statutory Indian GST compliance verification engine. Designed specifically for co-working, commercial leasing, and enterprise expense processing, it converts heterogeneous invoices (scanned PDFs, native vector PDFs, Word documents, smartphone photos) into normalized, audit-ready structured JSON with bounding-box evidence for every extracted value.

The entire pipeline operates deterministically with **zero reliance on generative LLMs**, guaranteeing predictable sub-second latencies, mathematical consistency, zero hallucinations, and high data privacy.

---

## 🏗 System Architecture

```
                          Incoming Invoice Document
                 (PDF, DOCX, PNG, JPG, JPEG, TIFF, BMP)
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │  File Validation & Security  │
                     │  (Magic Bytes & Rate Limit)  │
                     └──────────────┬───────────────┘
                                    │
               ┌────────────────────┴────────────────────┐
               ▼                                         ▼
   ┌───────────────────────┐                 ┌───────────────────────┐
   │ RapidOCR ONNX Pipeline│                 │ IBM Docling Pipeline  │
   │  (High-density Scans) │                 │  (Vector Layout/PDF)  │
   └───────────┬───────────┘                 └───────────┬───────────┘
               └────────────────────┬────────────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │ Spatial Layout Grid & Matcher│
                     │ (Bounding Boxes, Key-Value)  │
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │ Entity Disambiguation Engine │
                     │ (Operator vs GoFloaters Entity)
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │ GST Statutory Compliance     │
                     │ (Place of Supply, Invariants)│
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                      Unified Structured JSON Output
                 (Field Values + Confidence + Evidence)
```

---

## ✨ Key Features

1. **Hybrid Layout Engine**:
   - Primary high-fidelity layout reconstruction using **IBM Docling**.
   - Lightweight high-speed fallback and scanned-document ingestion via **RapidOCR ONNX**.
   - Pure-Python regex and spatial heuristics ensuring robust fallback if OCR engines fail.

2. **Entity Disambiguation**:
   - Accurately discriminates between billing entities (GoFloaters: `SMBSure Business Solutions Pvt Ltd`) and third-party space operators/landlords.
   - Extracts complete legal entity names, GSTINs, PANs, and addresses with confidence scoring.

3. **Statutory Indian GST Compliance Engine**:
   - **GSTIN & PAN Invariants**: Format validation, State Code extraction, and checksums.
   - **Tax Regime Verification**: Automated determination of Intra-State (`CGST` + `SGST`) vs Inter-State (`IGST`) tax based on Supplier State and Place of Supply (POS).
   - **Mathematical Verification**: Strict invariant balancing `Total Amount = Taxable Value + CGST + SGST + IGST + Roundoff`.

4. **Production & Enterprise Security**:
   - Binary magic-byte sniffing preventing MIME spoofing.
   - Sliding-window IP rate limiting (60 req/min).
   - API key authentication with constant-time equality check (`secrets.compare_digest`).
   - Hard execution timeouts (120s guard against catastrophic regex or layout stalls).

5. **Built-in Web Application**:
   - Embedded single-page dashboard at `/ui/` for instant manual inspection, drag-and-drop file uploads, and interactive JSON inspection.

---

## 📁 Repository Structure

```
.
├── invoice_parser/              # Core Python Application Package
│   ├── __init__.py
│   ├── addresses.py             # Spatial address extraction & state resolution
│   ├── api.py                   # FastAPI REST API & route definitions
│   ├── confidence.py            # Extraction confidence calculation models
│   ├── config.py                # Server & pipeline environment settings
│   ├── converter.py             # PDF-to-image and format conversion routines
│   ├── extractor.py             # Top-level unified extraction orchestrator
│   ├── fallback.py              # Pure-python heuristic extraction engine
│   ├── hybrid.py                # Hybrid Docling + RapidOCR coordinator
│   ├── main.py                  # CLI and batch pipeline entry point
│   ├── normalize.py             # Date, currency, string, and number normalizers
│   ├── preprocessor.py          # Image enhancement & binarization preprocessor
│   ├── schemas.py               # Pydantic request & response data models
│   ├── semantic.py              # Semantic keyword & entity dictionaries
│   ├── spatial.py               # 2D Bounding-box spatial layout engine
│   ├── text_tables.py           # Table boundary detector & itemizer
│   ├── validators.py            # Indian GST, PAN, and mathematical validators
│   └── web/
│       └── index.html           # Interactive drag-and-drop Web UI
├── tests/                       # Complete Test Suite (Unit & Integration)
│   ├── test_addresses.py
│   ├── test_api.py
│   ├── test_confidence.py
│   ├── test_gst_engine.py
│   ├── test_hybrid_flow.py
│   └── test_validators.py
├── API_DOCUMENTATION.md         # Full API specification & OpenAPI schema guide
├── API_ENDPOINTS_GUIDE.md       # Quick reference for all endpoints
├── CURL_DOCUMENTATION.md        # Real-world cURL examples with responses
├── PROJECT_REPORT.md            # Academic & Capstone Engineering Report
├── Dockerfile                   # Production multi-stage container build
├── pyproject.toml               # Python project configuration & packaging
├── requirements.txt             # Locked core runtime dependencies
├── requirements-dev.txt         # Development & testing dependencies
├── nixpacks.toml                # Coolify / Railway deployment configuration
└── LICENSE                      # MIT License
```

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.10, 3.11, or 3.12
- `pip` or `poetry`
- System libraries: `libgl1`, `libglib2.0-0` (for OpenCV)

### 1. Local Environment Setup

```bash
# Clone the repository
git clone https://github.com/Praveen-ASML24026/OCR---INvoice-validation-Gofloaters-.git
cd OCR---INvoice-validation-Gofloaters-

# Create and activate a virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Install runtime dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the template configuration file:
```bash
cp .env.example .env
```

Key environment configurations (`.env`):
```ini
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=production
DEBUG=false
API_KEY=your_secure_api_key_here
INVOICE_EXECUTION_TIMEOUT=120
RATE_LIMIT_PER_MINUTE=60
```

### 3. Launch Application Server

```bash
python -m invoice_parser.api
```

The service will start at `http://localhost:8000`:
- **Interactive Web Interface**: [http://localhost:8000/ui/](http://localhost:8000/ui/)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **OpenAPI Schema (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🐳 Docker Deployment

The repository includes a production-ready, security-hardened `Dockerfile` with multi-stage layer caching and pre-warmed model runtimes:

```bash
# Build the Docker image
docker build -t gofloaters-invoice-parser:latest .

# Run the container
docker run -d \
  --name invoice-parser \
  -p 8000:8000 \
  -e API_KEY="your_api_key" \
  gofloaters-invoice-parser:latest
```

---

## 📡 API Reference & cURL Usage

### 1. Unified Extraction (`POST /v1/extract`)

Processes any supported invoice and returns standardized structured data:

```bash
curl -X POST "http://localhost:8000/v1/extract" \
  -H "X-API-Key: your_secure_api_key_here" \
  -F "file=@invoice_sample.pdf"
```

#### Sample Response:
```json
{
  "status": "ok",
  "document_id": "inv_8f7b2a9e",
  "execution_time_ms": 482,
  "data": {
    "invoice_number": {
      "value": "INV-2024-0891",
      "confidence": 0.98,
      "evidence": { "page": 1, "box": [120, 45, 230, 60] }
    },
    "invoice_date": {
      "value": "2024-10-15",
      "confidence": 0.95
    },
    "operator": {
      "name": "Awfis Space Solutions Ltd",
      "gstin": "27AAACA1234A1Z5",
      "state_code": "27",
      "state": "Maharashtra"
    },
    "recipient": {
      "name": "SMBSure Business Solutions Pvt Ltd",
      "gstin": "33AAGCS9876Q1Z2",
      "state_code": "33",
      "state": "Tamil Nadu"
    },
    "tax_analysis": {
      "taxable_amount": 10000.00,
      "cgst_amount": 0.00,
      "sgst_amount": 0.00,
      "igst_amount": 1800.00,
      "total_amount": 11800.00,
      "tax_regime": "INTER_STATE",
      "is_valid": true,
      "math_checksum_matched": true
    }
  }
}
```

---

## 🧪 Running Automated Tests

Run the complete test suite with coverage:

```bash
# Install dev requirements
pip install -r requirements-dev.txt

# Run pytest
pytest tests/ -v
```

---

## 📜 Documentation

Comprehensive guides are available in the repository:
- 📖 [`PROJECT_REPORT.md`](PROJECT_REPORT.md) — Comprehensive Capstone Project Report detailing technical architecture, research, layout algorithms, and benchmark evaluations.
- 📘 [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) — Full API specification, security policies, and error handling guide.
- 📙 [`CURL_DOCUMENTATION.md`](CURL_DOCUMENTATION.md) — cURL cookbook covering every endpoint with real request/response examples.
- 📗 [`API_ENDPOINTS_GUIDE.md`](API_ENDPOINTS_GUIDE.md) — Quick lookup table for microservice integration.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

Developed for **GoFloaters** by **Praveen RS**.
