# GoFloaters Invoice Parser — Quick API Guide

**Base URL**: `https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai`

---

## 1. Endpoints

| Method     | Endpoint          | Description                                 | Auth Required?        |
| :--------- | :---------------- | :------------------------------------------ | :-------------------- |
| **`POST`** | **`/v1/extract`** | **Extract Invoice Data** (Primary endpoint) | **Yes** (`X-API-Key`) |
| **`GET`**  | **`/health`**     | **Health Check** (Status & config)          | No                    |
| **`GET`**  | **`/docs`**       | **Swagger UI** (Test API in browser)        | No                    |
| **`GET`**  | **`/ui/`**        | **Web Interface** (Drag & drop test)        | No                    |

---

## 2. Authentication

Include your API key in the request headers:

```http
X-API-Key: 
```

_(Or `Authorization: Bearer YOUR_API_KEY`)_

---

## 3. How to Call the API

Send an HTTP **`POST`** request with `multipart/form-data` using field name **`file`**.

### cURL

```bash
curl -X POST "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@invoice.pdf"
```

### Python

```python
import requests

url = "https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract"
headers = {"X-API-Key": "YOUR_API_KEY"}
files = {"file": open("invoice.pdf", "rb")}

response = requests.post(url, headers=headers, files=files)
print(response.json())
```

### Postman

1. Method: **`POST`**
2. URL: `https://qfahuz1qnxzbrotfh9dxrhgq.tools.creflo.ai/v1/extract`
3. Headers: Add `X-API-Key` = `YOUR_API_KEY`
4. Body: Select **form-data** $\rightarrow$ Key: `file` (type: **File**) $\rightarrow$ Select your file.
5. Click **Send**.

---

## 4. Sample Response (`200 OK`)

```json
{
  "status": "ok",
  "request_id": "a5e7d56d7b19",
  "data": {
    "invoice": {
      "number": "NUKDL/26-27/0677",
      "date": "2026-08-17"
    },
    "operator": {
      "name": "NUKLEUS OFFICE SOLUTIONS LIMITED",
      "gstin": "07AAGCN6967N1ZM",
      "state": "Delhi"
    },
    "gofloaters": {
      "name": "SMBSURE BUSINESS SOLUTIONS PRIVATE LIMITED",
      "gstin": "33AAYCS6808H1ZT",
      "state": "Tamil Nadu"
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
      "status": "valid"
    }
  }
}
```

---

## 5. Status Codes

| Code      | Meaning                                              |
| :-------- | :--------------------------------------------------- |
| **`200`** | **Success**: Invoice parsed successfully.            |
| **`400`** | **Bad Request**: File is empty or corrupt.           |
| **`401`** | **Unauthorized**: Missing or invalid `X-API-Key`.    |
| **`415`** | **Unsupported File**: Use PDF, PNG, JPG, or DOCX.    |
| **`429`** | **Rate Limit**: Exceeded 60 calls/minute.            |
| **`500`** | **Server Error**: Unexpected error while processing. |
