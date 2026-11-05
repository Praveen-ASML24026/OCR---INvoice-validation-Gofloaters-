# GoFloaters Invoice Parser — cURL Requests, Input Specification & Output JSON Guide

A complete developer reference for the **GoFloaters Enterprise Invoice Parser API**, detailing:
- Exact **cURL commands** across Linux, macOS, and Windows.
- Detailed **Input Request specifications** (multipart parameters, headers, and OpenAPI schema).
- Complete **Output JSON response payloads** (success, statutory compliance failures, and error codes).
- Field-by-field **Data Dictionary**.

---

## 1. Environments & Base URLs

| Environment | Base URL | Protocol | Auth Enforced? |
| :--- | :--- | :--- | :--- |
| **Production / Cloud** | `https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai` | HTTPS | Yes (`X-API-Key`) |
| **Local Development** | `http://localhost:8000` | HTTP | No (open/dev mode) |

---

## 2. Authentication Headers

Include your API key in **one** of the following HTTP request headers:

### Header A: `X-API-Key` (Recommended)
```http
X-API-Key: YOUR_API_KEY
```

### Header B: `Authorization: Bearer` (Alternative)
```http
Authorization: Bearer YOUR_API_KEY
```

*(Note: On local development servers where no API keys are configured, authentication headers can be omitted).*

---

## 3. Input Specification (What You Send)

The invoice parser accepts document files uploaded as **`multipart/form-data`**.

> **Note on Input Format:** Because the pipeline performs layout analysis and OCR using IBM Docling and RapidOCR, the input is an **invoice file binary**, not a raw JSON body.

### 3.1. Input Parameters Matrix

| Input Parameter | Type | Required? | Description | Constraints |
| :--- | :--- | :--- | :--- | :--- |
| **`file`** | Binary File | **Yes** | The invoice document to parse. | `.pdf`, `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`, `.docx` |
| **`X-API-Key`** | Header | **Yes** | Secret client authentication token. | Plain text string |
| `max_upload_mb` | Config | Enforced | Maximum document size allowed. | Default: **50 MB** |
| `magic_bytes` | Inspection | Enforced | Automated binary byte inspection. | Disguised scripts/binaries rejected |

### 3.2. Raw HTTP Request Representation
```http
POST /v1/extract HTTP/1.1
Host: qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai
X-API-Key: YOUR_API_KEY
Content-Type: multipart/form-data; boundary=---------------------------974767299852498929531610575

-----------------------------974767299852498929531610575
Content-Disposition: form-data; name="file"; filename="invoice.pdf"
Content-Type: application/pdf

[RAW BINARY DATA OF INVOICE FILE]
-----------------------------974767299852498929531610575--
```

### 3.3. OpenAPI Input Schema (`openapi.json`)
The request schema defined in `/openapi.json` for `POST /v1/extract`:
```json
{
  "requestBody": {
    "content": {
      "multipart/form-data": {
        "schema": {
          "type": "object",
          "required": ["file"],
          "properties": {
            "file": {
              "type": "string",
              "format": "binary",
              "description": "Invoice file (PDF, PNG, JPG, TIFF, BMP, Office doc)"
            }
          }
        }
      }
    },
    "required": true
  }
}
```

---

## 4. Complete cURL Request Commands

### 4.1. Primary Extraction Endpoint (`POST /v1/extract`)
Extracts invoice data, separates vendor from customer, reconciles GST taxes, and returns compliance results.

#### Bash / Linux / macOS / Git Bash
```bash
curl -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@/path/to/invoice.pdf"
```

#### Windows PowerShell
> **Important:** Always execute **`curl.exe`** in PowerShell to avoid the built-in `Invoke-WebRequest` alias:
```powershell
curl.exe -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract" `
  -H "X-API-Key: YOUR_API_KEY" `
  -F "file=@C:\path\to\invoice.pdf"
```

#### Windows Command Prompt (CMD)
```cmd
curl -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract" ^
  -H "X-API-Key: YOUR_API_KEY" ^
  -F "file=@C:\path\to\invoice.pdf"
```

#### Local Development Server
```bash
curl -X POST "http://localhost:8000/v1/extract" \
  -F "file=@invoice.pdf"
```

---

### 4.2. Legacy Express API Parity (`POST /api/invoice`)
Matches Node.js Express REST API format. Returns `"status": "success"` instead of `"ok"`.

```bash
curl -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/api/invoice" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@invoice.pdf"
```

---

### 4.3. Health Check Probe (`GET /health`)
Unauthenticated ops health check for monitoring probes.

```bash
curl -X GET "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/health"
```

---

### 4.4. Service Discovery & Metadata (`GET /`)
```bash
curl -X GET "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/" \
  -H "Accept: application/json"
```

---

### 4.5. Download OpenAPI Specification (`GET /openapi.json`)
```bash
curl -X GET "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/openapi.json" -o openapi.json
```

---

## 5. Output JSON Payloads (What You Receive)

### 5.1. Successful Extraction (`200 OK` — Fully Valid & Compliant)

```json
{
  "status": "ok",
  "request_id": "a5e7d56d7b19",
  "filename": "NUKDL_26-27_0677.pdf",
  "elapsed_ms": 61,
  "data": {
    "invoice": {
      "number": "NUKDL/26-27/0677",
      "date": "2026-08-17",
      "due_date": "2026-08-17",
      "place_of_supply": "Delhi (07)"
    },
    "operator": {
      "name": "NUKLEUS OFFICE SOLUTIONS LIMITED",
      "address": "Mezzanine Level Shivaji Stadium Metro Station Connaught Place New Delhi Delhi 110001 India",
      "state": "Delhi",
      "gstin": "07AAGCN6967N1ZM"
    },
    "gofloaters": {
      "name": "SMBSURE BUSINESS SOLUTIONS PRIVATE LIMITED",
      "address": "Millenia Business Park Campus 1A Perungudi Chennai 600096 Tamil Nadu India",
      "state": "Tamil Nadu",
      "gstin": "33AAYCS6808H1ZT"
    },
    "tax": {
      "taxable_amount": 8400.0,
      "cgst": 756.0,
      "sgst": 756.0,
      "igst": null,
      "total": 9912.0
    },
    "line_items": [
      {
        "description": "MEMBERSHIP FEES (SAC: 997212)",
        "quantity": 12.0,
        "rate": 700.0,
        "amount": 8400.0
      }
    ],
    "validation": {
      "valid": true,
      "status": "valid",
      "transaction_type": "INTRA_STATE",
      "summary": "All statutory rules passed.",
      "errors": []
    },
    "confidence": {
      "invoice_number": 0.95,
      "taxable_amount": 1.0,
      "gstin": 1.0,
      "dates": 0.98,
      "overall": 0.98
    },
    "step_timings_ms": {
      "step1_conversion_ocr": 0.0,
      "step2_structural_extraction": 6.1,
      "step3_semantic_detection": 1.9,
      "step4_normalization": 0.8,
      "step5_fallbacks_addresses": 36.3,
      "step6_compliance_validation": 0.5,
      "total_elapsed_ms": 60.7
    }
  }
}
```

---

### 5.2. Non-Compliant Invoice (`200 OK` with Statutory Rule Violations)

When an invoice contains tax mismatches (e.g. charging CGST/SGST on an inter-state transaction or wrong place of supply), the HTTP status is still `200`, but `status` is `"needs_review"` and `validation.valid` is `false`:

```json
{
  "status": "needs_review",
  "request_id": "c8f219b04e21",
  "filename": "INV-INTERSTATE-ERR.pdf",
  "elapsed_ms": 74,
  "data": {
    "invoice": {
      "number": "INV-2026-901",
      "date": "2026-09-01",
      "due_date": null,
      "place_of_supply": "Delhi (07)"
    },
    "operator": {
      "name": "NORTH COWORKING SPACES LTD",
      "address": "Connaught Place, New Delhi 110001",
      "state": "Delhi",
      "gstin": "07AAAAA0000A1Z5"
    },
    "gofloaters": {
      "name": "SMBSURE BUSINESS SOLUTIONS PRIVATE LIMITED",
      "address": "Perungudi, Chennai 600096 Tamil Nadu",
      "state": "Tamil Nadu",
      "gstin": "33AAYCS6808H1ZT"
    },
    "tax": {
      "taxable_amount": 10000.0,
      "cgst": 900.0,
      "sgst": 900.0,
      "igst": null,
      "total": 11800.0
    },
    "line_items": [
      {
        "description": "Desk rental",
        "quantity": 1.0,
        "rate": 10000.0,
        "amount": 10000.0
      }
    ],
    "validation": {
      "valid": false,
      "status": "invalid",
      "transaction_type": "INTER_STATE",
      "summary": "2 rule violation(s): REQ2, REQ3.",
      "errors": [
        {
          "rule": "REQ2",
          "code": "INCORRECT_TAX_TYPE",
          "message": "Incorrect Tax Type — CGST/SGST charged for inter-state transaction: Operator is in Delhi (07) and GoFloaters is in Tamil Nadu (33), so IGST applies, but IGST was not found (CGST 900.0 / SGST 900.0 were charged instead).",
          "type": "error"
        },
        {
          "rule": "REQ3",
          "code": "PLACE_OF_SUPPLY_MISMATCH",
          "message": "Operator location is Delhi and GoFloaters location is Tamil Nadu, so IGST is expected, but CGST + SGST was charged. Supporting evidence: Place of Supply is Delhi (07).",
          "type": "error"
        }
      ]
    },
    "confidence": {
      "overall": 0.85
    }
  }
}
```

---

### 5.3. Health Check Response (`GET /health`)

```json
{
  "status": "ok",
  "uptime": 14520,
  "auth_required": true,
  "keys_configured_count": 1,
  "max_upload_mb": 50,
  "rate_limit_max": 60,
  "execution_timeout_ms": 120000
}
```

---

### 5.4. Root Metadata Response (`GET /`)

```json
{
  "status": "ok",
  "message": "GoFloaters Enterprise Invoice Parser REST API",
  "auth_enabled": true,
  "endpoints": {
    "health": "GET /health",
    "invoice": "POST /api/invoice (multipart/form-data, field: 'file')",
    "extract": "POST /v1/extract (multipart/form-data, field: 'file')",
    "ui": "GET /ui/",
    "docs": "GET /docs"
  }
}
```

---

## 6. HTTP Error JSON Payloads

When an error occurs, the API returns a standardized JSON error body:

### 6.1. Missing / Invalid API Key (`401 Unauthorized`)
```json
{
  "detail": "Invalid or missing API key."
}
```

### 6.2. Empty or Corrupted Upload (`400 Bad Request`)
```json
{
  "detail": "Invoice file is required and cannot be empty."
}
```

### 6.3. Disallowed File Format (`415 Unsupported Media Type`)
```json
{
  "detail": "Unsupported file type '.exe'. Allowed formats: ['.bmp', '.docx', '.jpeg', '.jpg', '.pdf', '.png', '.tiff']"
}
```

### 6.4. File Size Exceeded (`413 Payload Too Large`)
```json
{
  "detail": "File exceeds maximum upload limit of 50 MB."
}
```

### 6.5. Rate Limit Exceeded (`429 Too Many Requests`)
```json
{
  "detail": "Rate limit exceeded. Maximum 60 requests per minute allowed."
}
```

### 6.6. Processing Timeout (`408 Request Timeout`)
```json
{
  "detail": "Invoice processing timed out after 120 seconds."
}
```

---

## 7. Output Data Dictionary

### `data.invoice`
| Field | Type | Description |
| :--- | :--- | :--- |
| `number` | `string \| null` | Cleaned invoice identifier (e.g. `NUKDL/26-27/0677`). |
| `date` | `string \| null` | Normalized ISO invoice date (`YYYY-MM-DD`). |
| `due_date` | `string \| null` | Normalized ISO payment due date (`YYYY-MM-DD`). |
| `place_of_supply`| `string \| null` | State name and 2-digit GST state code (e.g. `Delhi (07)`). |

### `data.operator` & `data.gofloaters` (Party Models)
| Field | Type | Description |
| :--- | :--- | :--- |
| `name` | `string \| null` | Extracted business entity or trade name. |
| `address` | `string \| null` | Full physical or registered office address. |
| `state` | `string \| null` | Extracted Indian state name. |
| `gstin` | `string \| null` | 15-character statutory GST identification number. |

### `data.tax`
| Field | Type | Description |
| :--- | :--- | :--- |
| `taxable_amount` | `float \| null` | Total assessable value before taxes. |
| `cgst` | `float \| null` | Central GST amount. |
| `sgst` | `float \| null` | State/UT GST amount. |
| `igst` | `float \| null` | Integrated GST amount. |
| `total` | `float \| null` | Final invoice total payable. |

### `data.line_items[]`
| Field | Type | Description |
| :--- | :--- | :--- |
| `description` | `string` | Service or product description. |
| `hsn_sac` | `string \| null` | HSN / SAC statutory code. |
| `quantity` | `float \| null` | Extracted quantity. |
| `rate` | `float \| null` | Extracted unit rate. |
| `amount` | `float \| null` | Line item total amount. |

### `data.validation`
| Field | Type | Description |
| :--- | :--- | :--- |
| `valid` | `boolean` | `true` if all statutory rules passed; `false` if violations exist. |
| `status` | `string` | `"valid"`, `"invalid"`, or `"incomplete"`. |
| `transaction_type`| `string` | `"INTRA_STATE"` (CGST + SGST expected) or `"INTER_STATE"` (IGST expected). |
| `summary` | `string` | Plain-English summary of compliance status. |
| `errors` | `array` | Detailed list of rule violations. |

---

## 8. Practical cURL Recipes

### Recipe 1: Save Extracted JSON Directly to a File
```bash
curl -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@invoice.pdf" \
  -o result.json
```

### Recipe 2: Format & Pretty-Print Output with `jq`
```bash
curl -s -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@invoice.pdf" | jq .
```

### Recipe 3: Filter Only Tax and Validation with `jq`
```bash
curl -s -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@invoice.pdf" | jq '.data | {tax: .tax, validation: .validation}'
```

### Recipe 4: Print HTTP Status Code with Response
```bash
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@invoice.pdf"
```

### Recipe 5: Full Verbose Debugging Mode
```bash
curl -v -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@invoice.pdf"
```
