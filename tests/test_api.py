import dataclasses
import pytest
from fastapi.testclient import TestClient

import invoice_parser.api as api
from invoice_parser.config import settings

FAKE = {
    "invoice": {"number": "INV-2026-001", "date": "2026-09-04", "due_date": None},
    "operator": {"gstin": "33AAECI3042B1ZB", "name": "Test Space Operator"},
    "gofloaters": {"gstin": "33AAYCS6808H1ZT", "name": "GoFloaters"},
    "tax": {"taxable_amount": 1000.0, "cgst": 90.0, "sgst": 90.0, "total": 1180.0},
    "line_items": [{"description": "Coworking Desk", "quantity": 1, "rate": 1000.0, "amount": 1000.0}],
    "validation": {"valid": True, "status": "valid", "errors": [], "unverified": []},
    "step_timings_ms": {"total_elapsed_ms": 120.5},
}


def client(monkeypatch):
    monkeypatch.setattr(api, "create_converter", lambda: None)
    monkeypatch.setattr(api, "process", lambda path, **kwargs: FAKE)
    if api.settings is settings:
        monkeypatch.setattr(api, "settings", dataclasses.replace(settings, auth_required=False, api_keys=frozenset()))
    return TestClient(api.app)


def test_health(monkeypatch):
    with client(monkeypatch) as c:
        res = c.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


def test_root_metadata(monkeypatch):
    with client(monkeypatch) as c:
        res = c.get("/")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "endpoints" in data
        assert "health" in data["endpoints"]
        assert "invoice" in data["endpoints"]


def test_method_not_allowed_on_get(monkeypatch):
    with client(monkeypatch) as c:
        res_inv = c.get("/api/invoice", headers={"Accept": "application/json"})
        assert res_inv.status_code == 405
        assert res_inv.json()["status"] == "error"

        res_ext = c.get("/v1/extract", headers={"Accept": "application/json"})
        assert res_ext.status_code == 405
        assert res_ext.json()["status"] == "error"


def test_extract_v1_ok(monkeypatch):
    with client(monkeypatch) as c:
        r = c.post("/v1/extract", files={"file": ("invoice.pdf", b"%PDF-1.4 test document content")})
        assert r.status_code == 200
        json_data = r.json()
        assert json_data["status"] == "ok"
        assert json_data["filename"] == "invoice.pdf"
        assert json_data["data"]["invoice"]["number"] == "INV-2026-001"
        assert r.headers["X-Request-ID"]


def test_api_invoice_ok(monkeypatch):
    with client(monkeypatch) as c:
        r = c.post("/api/invoice", files={"file": ("invoice.pdf", b"%PDF-1.4 test document content")})
        assert r.status_code == 200
        json_data = r.json()
        assert json_data["status"] == "success"
        assert json_data["filename"] == "invoice.pdf"
        assert json_data["data"]["tax"]["total"] == 1180.0


def test_bad_type_and_empty(monkeypatch):
    with client(monkeypatch) as c:
        # Unsupported extension (.exe)
        assert c.post("/v1/extract", files={"file": ("invoice.exe", b"MZtest")}).status_code == 415

        # Empty file
        assert c.post("/v1/extract", files={"file": ("invoice.pdf", b"")}).status_code == 400


def test_disguised_executable_detection(monkeypatch):
    with client(monkeypatch) as c:
        # Windows PE executable disguised as PDF
        r_pe = c.post("/v1/extract", files={"file": ("invoice.pdf", b"MZ\x90\x00\x03\x00\x00\x00")})
        assert r_pe.status_code == 400
        assert "disguised binary" in r_pe.json()["detail"].lower()

        # Linux ELF disguised as PDF
        r_elf = c.post("/v1/extract", files={"file": ("invoice.pdf", b"\x7fELF\x02\x01\x01\x00")})
        assert r_elf.status_code == 400
        assert "disguised binary" in r_elf.json()["detail"].lower()

        # Shell script disguised as PDF
        r_sh = c.post("/v1/extract", files={"file": ("invoice.pdf", b"#!/bin/bash\necho bad")})
        assert r_sh.status_code == 400
        assert "disguised binary" in r_sh.json()["detail"].lower()


def test_authentication_with_api_key(monkeypatch):
    monkeypatch.setattr(api, "settings", dataclasses.replace(settings, api_keys=frozenset(["secret-test-key"]), auth_required=True))
    with client(monkeypatch) as c:
        # Unauthorized without key
        r_unauth = c.post("/v1/extract", files={"file": ("invoice.pdf", b"%PDF-1.4 content")})
        assert r_unauth.status_code == 401
        assert "missing api key" in r_unauth.json()["detail"].lower()

        # Unauthorized with wrong key
        r_wrong = c.post(
            "/v1/extract",
            headers={"X-API-Key": "wrong-key"},
            files={"file": ("invoice.pdf", b"%PDF-1.4 content")},
        )
        assert r_wrong.status_code == 401
        assert "invalid api key" in r_wrong.json()["detail"].lower()

        # Authorized with X-API-Key
        r_auth_x = c.post(
            "/v1/extract",
            headers={"X-API-Key": "secret-test-key"},
            files={"file": ("invoice.pdf", b"%PDF-1.4 content")},
        )
        assert r_auth_x.status_code == 200

        # Authorized with Authorization: Bearer
        r_auth_bearer = c.post(
            "/api/invoice",
            headers={"Authorization": "Bearer secret-test-key"},
            files={"file": ("invoice.pdf", b"%PDF-1.4 content")},
        )
        assert r_auth_bearer.status_code == 200


def test_authentication_required_but_no_server_keys_configured(monkeypatch):
    # If auth_required is True, but admin forgot to set any API keys in environment -> 503
    monkeypatch.setattr(api, "settings", dataclasses.replace(settings, api_keys=frozenset(), auth_required=True))
    with client(monkeypatch) as c:
        r = c.post("/v1/extract", files={"file": ("invoice.pdf", b"%PDF-1.4 content")})
        assert r.status_code == 503
        assert "no api keys are configured" in r.json()["detail"].lower()


def test_rate_limit_not_bypassed_by_fake_x_forwarded_for(monkeypatch):
    monkeypatch.setattr(api.rate_limiter, "max_requests", 3)
    monkeypatch.setattr(api.rate_limiter, "clients", {})
    with client(monkeypatch) as c:
        # Send 3 allowed requests with different fake X-Forwarded-For headers
        for i in range(3):
            r = c.post(
                "/v1/extract",
                headers={"X-Forwarded-For": f"198.51.100.{i+1}"},
                files={"file": ("invoice.pdf", b"%PDF-1.4 content")},
            )
            assert r.status_code == 200

        # 4th request must be rejected with 429 even with another fake IP
        r_blocked = c.post(
            "/v1/extract",
            headers={"X-Forwarded-For": "198.51.100.99"},
            files={"file": ("invoice.pdf", b"%PDF-1.4 content")},
        )
        assert r_blocked.status_code == 429
        assert "too many requests" in r_blocked.json()["detail"].lower()


def test_request_id_length_capped_and_sanitized(monkeypatch):
    with client(monkeypatch) as c:
        long_malicious_rid = "A" * 200 + "<script>alert(1)</script>"
        r = c.post(
            "/v1/extract",
            headers={"X-Request-ID": long_malicious_rid},
            files={"file": ("invoice.pdf", b"%PDF-1.4 content")},
        )
        assert r.status_code == 200
        echoed_rid = r.headers.get("X-Request-ID")
        assert len(echoed_rid) <= 64
        assert "<" not in echoed_rid
        assert ">" not in echoed_rid


def test_500_error_does_not_leak_internals(monkeypatch):
    secret_leak_msg = "SecretPathError: /var/secrets/api_private_key.pem not accessible"
    def raise_secret(*args, **kwargs):
        raise RuntimeError(secret_leak_msg)

    with client(monkeypatch) as c:
        monkeypatch.setattr(api, "process", raise_secret)
        r = c.post("/v1/extract", files={"file": ("invoice.pdf", b"%PDF-1.4 content")})
        assert r.status_code in (422, 500)
        data = r.json()
        assert secret_leak_msg not in data.get("detail", "")
        assert secret_leak_msg not in data.get("message", "")


def test_corrupt_pdf_returns_422(monkeypatch):
    def raise_corrupt(*args, **kwargs):
        raise ValueError("Corrupted or invalid PDF document: Data format error")

    with client(monkeypatch) as c:
        monkeypatch.setattr(api, "process", raise_corrupt)
        r = c.post("/v1/extract", files={"file": ("invoice.pdf", b"%PDF-1.4 content")})
        assert r.status_code == 422
        assert "corrupted" in r.json()["detail"].lower()

