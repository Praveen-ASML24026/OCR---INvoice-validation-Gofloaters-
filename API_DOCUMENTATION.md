# GoFloaters Enterprise Invoice Parser — API Documentation & Developer Manual

**Production Base URL**: `https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai`  
**Interactive Web Interface**: [`https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/ui/`](https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/ui/)  
**Interactive OpenAPI / Swagger**: [`https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/docs`](https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/docs) *(includes Authorize 🔒 dialog)*  
**ReDoc Schema Documentation**: [`https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/redoc`](https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/redoc)

---

## 1. System Overview

The **GoFloaters Enterprise Invoice Parser (v2.0)** is an automated document extraction and Indian GST statutory compliance validation service. Built with FastAPI, IBM Docling layout analysis, RapidOCR ONNX runtime, and an extensive spatial/heuristic extraction engine, it turns PDFs and invoice images into structured, compliance-audited JSON in milliseconds.

### Core Capabilities
- **Multi-Format Ingestion**: Supports `.pdf` (fast native digital text stream and OCR for scans), `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`, and `.docx`.
- **Entity Disambiguation**: Intelligently separates vendor/operator entities from the GoFloaters billing entity (`SMBSure Business Solutions Pvt Ltd`).
- **GST Statutory Compliance Engine**: Verifies GSTIN format, state code alignment, intra-state vs inter-state tax rules (CGST + SGST vs IGST), Place of Supply reconciliation, and mathematical tax checksums.
- **Enterprise Security**: Binary magic-byte validation, sliding-window rate limiting (60 req/min), constant-time token verification (`secrets.compare_digest`), and execution timeout guards (120s).

---

## 2. API Endpoints Catalog

| Method | Endpoint | Description | Content-Type | Auth Enforced |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | Ops health probe & active server configuration | `application/json` | No |
| `GET` | `/` | Root discovery metadata (browser redirects to `/ui/`) | `application/json` / `text/html` | No |
| `GET` | `/ui/` | Visual drag-and-drop web application | `text/html` | No |
| `GET` | `/docs` | Interactive Swagger UI with **Authorize 🔒** dialog | `text/html` | No |
| `GET` | `/redoc` | Interactive ReDoc schema browser | `text/html` | No |
| `POST` | `/v1/extract` | **Primary Unified Extraction Endpoint** (`ok` \| `needs_review`) | `multipart/form-data` | Yes (when configured) |
| `POST` | `/api/invoice` | **Legacy REST API Parity Endpoint** (`success` \| error) | `multipart/form-data` | Yes (when configured) |

---

## 3. Authentication Flow (`X-API-Key` & Bearer)

### 3.1. How Authentication Works
1. **Server-Side Configuration**:
   - The server inspects the `INVOICE_API_KEYS` (or `API_KEY`) environment variable.
   - Setting `INVOICE_API_KEYS` automatically activates authentication (`auth_required: true`).
   - If `INVOICE_API_KEYS` is left empty, the server operates in open/development mode.
2. **Fail-Closed 503 Guard**:
   - If `AUTH_REQUIRED=true` is set, but no API keys are configured on the server, requests are blocked with HTTP `503 Service Unavailable` rather than silently allowing unauthenticated access.
3. **Constant-Time Verification**:
   - Tokens are validated using `secrets.compare_digest` to prevent side-channel timing attacks.

### 3.2. Setting Up API Keys in Coolify (Admin)
1. Open your **Coolify Dashboard** $\rightarrow$ select the **Invoice Parser Application**.
2. Navigate to **Environment Variables**.
3. Add:
   ```env
   INVOICE_API_KEYS="gf_test_your_secret_api_key_here"
   ```
   *(For multiple client keys, separate them with commas: `INVOICE_API_KEYS="clientA_key,clientB_key"`)*
4. Click **Save** and **Redeploy**.

### 3.3. How End-Users Pass the Key
Users must provide their key in either of two HTTP request headers:

#### Option A: `X-API-Key` Header (Recommended)
```http
X-API-Key: gf_test_your_secret_api_key_here
```

#### Option B: `Authorization: Bearer` Header
```http
Authorization: Bearer gf_test_your_secret_api_key_here
```

---

## 4. Detailed Endpoint Specifications

### 4.1. Health Check Probe (`GET /health`)
Used by monitoring platforms (Coolify, Docker, Kubernetes) and client diagnostics.

- **URL**: `GET https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/health`
- **Response `200 OK`**:
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

### 4.2. Primary Extraction Endpoint (`POST /v1/extract`)
Extracts all structured data and performs full statutory GST compliance auditing.

- **URL**: `POST https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract`
- **Headers**:
  - `Content-Type: multipart/form-data`
  - `X-API-Key: <YOUR_API_KEY>`
- **Form Body**:
  - `file` *(Binary, Required)*: The invoice document (`.pdf`, `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`, `.docx`).

#### Complete Response Payload (`200 OK`):
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
      "address": "Mezzanine Level Shivaji Stadium Metro Station Baba Kharak Singh Rd, Connaught Place New Delhi Delhi 110001 India",
      "state": "Delhi",
      "gstin": "07AAGCN6967N1ZM"
    },
    "gofloaters": {
      "name": "SMBSURE BUSINESS SOLUTIONS PRIVATE LIMITED",
      "address": "Millenia Business Park Campus –1A, 2nd Floor, 9/1A MGR Main Road, Kodandarama Nagar, Perungudi, Chennai 600096 Tamil Nadu India",
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
        "description": "MEMBERSHIP FEES Membership Fee for 12 day",
        "hsn_sac": "997212",
        "quantity": 12.0,
        "rate": 700.0,
        "amount": 8400.0
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
          "message": "Incorrect Tax Type — CGST/SGST charged for inter-state transaction: Operator is in Delhi (07) and GoFloaters is in Tamil Nadu (33), so IGST applies, but IGST was not found (CGST 756.0 / SGST 756.0 were charged instead).",
          "type": "error"
        },
        {
          "rule": "REQ3",
          "code": "PLACE_OF_SUPPLY_MISMATCH",
          "message": "Operator location is Delhi and GoFloaters location is Tamil Nadu, so IGST is expected, but CGST + SGST was charged. Supporting evidence: Place of Supply is Delhi (07), which points to CGST + SGST.",
          "type": "error"
        }
      ],
      "unverified": [],
      "issues": []
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

### 4.3. Legacy Compatible Endpoint (`POST /api/invoice`)
Matches Node.js Express REST API specification. Returns `status: "success"` on successful extraction instead of `"ok"`.

- **URL**: `POST https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/api/invoice`
- **Method**: `POST`
- **Body**: `multipart/form-data` with form field `file`

---

## 5. Data Dictionary

### `data.invoice`
| Field | Type | Description |
| :--- | :--- | :--- |
| `number` | `string \| null` | Cleaned alphanumeric invoice identifier (e.g. `NUKDL/26-27/0677`). |
| `date` | `string \| null` | Normalized ISO date string (`YYYY-MM-DD`). |
| `due_date` | `string \| null` | Normalized payment due date (`YYYY-MM-DD`). |
| `place_of_supply`| `string \| null` | Place of supply state name and code (e.g. `Delhi (07)`). |

### `data.operator` & `data.gofloaters` (Party Models)
| Field | Type | Description |
| :--- | :--- | :--- |
| `name` | `string \| null` | Legal entity or business trade name. |
| `address` | `string \| null` | Extracted physical billing/registered office address. |
| `state` | `string \| null` | State name derived from GSTIN state code or address. |
| `gstin` | `string \| null` | 15-character statutory GST identification number. |

### `data.tax`
| Field | Type | Description |
| :--- | :--- | :--- |
| `taxable_amount` | `float \| null` | Subtotal or base assessable value before taxes. |
| `cgst` | `float \| null` | Central GST amount. Supports concatenated rate labels (e.g. `CGST9`). |
| `sgst` | `float \| null` | State/UT GST amount. Supports concatenated rate labels (e.g. `SGST9`). |
| `igst` | `float \| null` | Integrated GST amount (e.g. `IGST18`). |
| `total` | `float \| null` | Final invoice total payable. |

### `data.validation`
| Field | Type | Description |
| :--- | :--- | :--- |
| `valid` | `boolean` | `true` if all business rules passed; `false` if any statutory errors exist. |
| `status` | `string` | `"valid"`, `"invalid"`, or `"incomplete"`. |
| `transaction_type`| `string` | `"INTRA_STATE"` (CGST + SGST expected) or `"INTER_STATE"` (IGST expected). |
| `errors` | `array` | Detailed list of rule violations (code, rule name, and plain-English explanation). |

---

## 6. Client Code Implementations

### 6.1. cURL (Command Line)
```bash
# Health Check
curl -s https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/health

# Extract Invoice with X-API-Key
curl -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract" \
  -H "X-API-Key: gf_test_your_secret_api_key_here" \
  -F "file=@/path/to/invoice.pdf"

# Extract Invoice with Authorization: Bearer
curl -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract" \
  -H "Authorization: Bearer gf_test_your_secret_api_key_here" \
  -F "file=@/path/to/invoice.pdf"
```

---

### 6.2. Python (`requests`)
```python
import requests

API_URL = "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract"
API_KEY = "gf_test_your_secret_api_key_here"
FILE_PATH = "sample_invoice.pdf"

headers = {
    "X-API-Key": API_KEY
}

with open(FILE_PATH, "rb") as f:
    files = {"file": (FILE_PATH, f, "application/pdf")}
    response = requests.post(API_URL, headers=headers, files=files, timeout=120)

if response.status_code == 200:
    data = response.json()
    invoice = data["data"]["invoice"]
    tax = data["data"]["tax"]
    validation = data["data"]["validation"]

    print("Status:", data["status"])
    print(f"Invoice Number: {invoice['number']} ({invoice['date']})")
    print(f"Taxable: ₹{tax['taxable_amount']} | Total: ₹{tax['total']}")
    print(f"Compliance: {'PASSED' if validation['valid'] else 'FAILED'}")
    if not validation["valid"]:
        for err in validation["errors"]:
            print(f" - [{err.get('code')}] {err.get('message')}")
else:
    print(f"Error {response.status_code}: {response.text}")
```

---

### 6.3. Node.js / TypeScript (`fetch` & `FormData`)
```typescript
import * as fs from 'fs';
import * as path from 'path';

async function parseInvoice(filePath: string) {
  const url = 'https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract';
  const apiKey = 'gf_test_your_secret_api_key_here';

  const fileBuffer = fs.readFileSync(filePath);
  const blob = new Blob([fileBuffer]);

  const formData = new FormData();
  formData.append('file', blob, path.basename(filePath));

  const response = await fetch(url, {
    method: 'POST',
    body: formData,
    headers: {
      'X-API-Key': apiKey,
    },
  });

  if (!response.ok) {
    const errorJson = await response.json();
    throw new Error(`Extraction failed (${response.status}): ${JSON.stringify(errorJson)}`);
  }

  const result = await response.json();
  console.log('Invoice No:', result.data.invoice.number);
  console.log('Taxes:', result.data.tax);
  return result;
}

parseInvoice('./sample_invoice.pdf').catch(console.error);
```

---

### 6.4. Postman Setup
1. **Method**: `POST`
2. **URL**: `https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract`
3. **Headers tab**:
   - `X-API-Key`: `gf_test_your_secret_api_key_here`
4. **Body tab**:
   - Select `form-data`
   - Key: `file` (Change field type from `Text` to `File`)
   - Value: Select your `.pdf` or image.
5. Click **Send**.

---

## 7. HTTP Status Codes & Troubleshooting

| HTTP Status | Name | Cause & Resolution |
| :--- | :--- | :--- |
| **`400 Bad Request`** | Invalid/Corrupted File | Uploaded file was 0 bytes, corrupted, or failed binary magic-byte inspection (e.g., an executable disguised as `.pdf`). |
| **`401 Unauthorized`** | Missing or Invalid Key | Provided API key was missing, misspelled, or unauthorized. Provide via `X-API-Key` or `Authorization: Bearer`. |
| **`405 Method Not Allowed`** | GET sent to POST Route | Visited `/api/invoice` or `/v1/extract` via browser `GET`. Send an HTTP `POST` with `multipart/form-data`, or use the web UI at `/ui/`. |
| **`408 Request Timeout`** | Execution Timeout | Processing exceeded the 120-second timeout limit. Inspect document size/page count. |
| **`413 Payload Too Large`** | Size Limit Exceeded | Document exceeds the 50 MB upload limit. |
| **`415 Unsupported Media Type`** | Invalid Extension | Extension is not in `.pdf`, `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`, `.docx`. |
| **`422 Unprocessable Entity`** | Parsing Malformation | Document has unrecoverable corruption or syntax errors during OCR parsing. |
| **`429 Too Many Requests`** | Rate Limit Exceeded | Exceeded 60 requests per minute from your IP. Implement exponential backoff retry. |
| **`503 Service Unavailable`** | Auth Not Configured | Server has `AUTH_REQUIRED=true`, but no `INVOICE_API_KEYS` have been configured in the environment. |
| **`500 Internal Server Error`** | Unhandled Error | Unexpected server error. Check `request_id` in server logs for diagnosis. |
