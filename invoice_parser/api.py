"""
GoFloaters Enterprise Invoice Parser - Production FastAPI Application
Provides complete parity with the REST API architecture:
- Binary magic-byte inspection (detects valid PDF/images/Office docs, blocks disguised binaries/scripts)
- Rate limiting (sliding window per client IP)
- Execution timeouts (default 120s, returns 408 on timeout)
- Configurable API Key / Bearer Token authentication (with open/development mode fallback)
- Unified endpoints:
    - POST /api/invoice (status: 'success')
    - POST /v1/extract (status: 'ok' | 'needs_review')
    - GET / (JSON metadata or web UI redirect)
    - GET /health (unauthenticated ops health probe)
    - GET /api/invoice & /v1/extract (405 Method Not Allowed / UI redirect)
    - Static Web UI mounted at /ui/

Run:   python -m invoice_parser.api
       or: uvicorn invoice_parser.api:app --host 0.0.0.0 --port 8000
Docs:  http://localhost:8000/docs
UI:    http://localhost:8000/ui/
"""
import asyncio
import collections
import contextlib
import logging
import os
import sys
import tempfile
import threading
import time
import uuid
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, Response, Security, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from .config import settings
from .converter import SUPPORTED, create_converter
from .main import logger as pipeline_logger, process

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("invoice_api")

SERVER_START_TIME = time.time()


# --------------------------------------------------------------------------
# Lifespan: Model Warmup
# --------------------------------------------------------------------------
async def _background_warmup():
    log.info("[FastAPI] Background pre-warming Docling / RapidOCR models...")
    try:
        await run_in_threadpool(create_converter)
        log.info("[FastAPI] Models loaded and ready.")
    except Exception as warm_err:
        log.warning("[FastAPI] Model warmup deferred or failed: %s", warm_err)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Spawn warmup in background so Uvicorn binds to port 8000 immediately (<1s)
    asyncio.create_task(_background_warmup())

    port = settings.port
    print(f" GoFloaters Invoice Parser is LIVE!", flush=True)
    print(f" Web UI:       http://localhost:{port}/ui/", flush=True)
    print(f" Swagger Docs: http://localhost:{port}/docs", flush=True)
    print(f" Health Check: http://localhost:{port}/health", flush=True)

    yield


app = FastAPI(
    title="GoFloaters Enterprise Invoice Parser API",
    version="2.0.0",
    description="Production-grade invoice parsing and GST compliance extraction with Docling & RapidOCR.",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------
# Binary Magic-Byte Inspection
# --------------------------------------------------------------------------
def inspect_magic_bytes(file_path: Path) -> dict:
    """
    Inspects binary magic bytes of the uploaded file to ensure authentic
    documents (PDF, image, office) and block disguised executables.
    """
    try:
        size = file_path.stat().st_size
        if size < 4:
            return {"valid": False, "reason": "Uploaded file is empty or corrupted."}

        with open(file_path, "rb") as f:
            buffer = f.read(16)

        if len(buffer) < 4:
            return {"valid": False, "reason": "Uploaded file is empty or corrupted."}

        # Check for disguised executables:
        # Windows PE Executable: 'MZ' (0x4D 0x5A)
        # Linux ELF: 0x7F 'ELF' (0x7F 0x45 0x4C 0x46)
        # Unix Shell Script: '#!' (0x23 0x21)
        if (
            (buffer[0] == 0x4D and buffer[1] == 0x5A)
            or (buffer[0] == 0x7F and buffer[1] == 0x45 and buffer[2] == 0x4C and buffer[3] == 0x46)
            or (buffer[0] == 0x23 and buffer[1] == 0x21)
        ):
            return {
                "valid": False,
                "reason": "Security violation: uploaded file is a disguised binary or executable script.",
            }

        # PDF Magic Bytes: %PDF- (0x25 0x50 0x44 0x46 0x2D)
        if buffer[0:5] == b"%PDF-":
            return {"valid": True, "type": "pdf"}

        # PNG Magic Bytes: 89 50 4E 47 0D 0A 1A 0A
        if buffer[0:8] == b"\x89PNG\r\n\x1a\n":
            return {"valid": True, "type": "png"}

        # JPEG Magic Bytes: FF D8 FF
        if buffer[0:3] == b"\xff\xd8\xff":
            return {"valid": True, "type": "jpeg"}

        # TIFF Magic Bytes: II* (49 49 2A 00) or MM* (4D 4D 00 2A)
        if buffer[0:4] in (b"II*\x00", b"MM\x00*"):
            return {"valid": True, "type": "tiff"}

        # BMP Magic Bytes: BM (0x42 0x4D)
        if buffer[0:2] == b"BM":
            return {"valid": True, "type": "bmp"}

        # WEBP Magic Bytes: RIFF....WEBP
        if buffer[0:4] == b"RIFF" and len(buffer) >= 12 and buffer[8:12] == b"WEBP":
            return {"valid": True, "type": "webp"}

        # Zip-based Office formats (DOCX, XLSX, PPTX): PK\x03\x04 (0x50 0x4B 0x03 0x04)
        if buffer[0:4] == b"PK\x03\x04":
            return {"valid": True, "type": "office_zip"}

        return {
            "valid": False,
            "reason": "Invalid file format. Header bytes do not match a valid PDF, image, or Office document.",
        }
    except Exception as exc:
        return {"valid": False, "reason": f"Failed to inspect file magic bytes: {exc}"}


# --------------------------------------------------------------------------
# In-Memory Sliding-Window Rate Limiter
# --------------------------------------------------------------------------
class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clients: dict = {}
        self.lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> bool:
        if self.max_requests <= 0:
            return True
        now = time.time()
        cutoff = now - self.window_seconds
        with self.lock:
            # Prune idle client entries to eliminate memory leaks
            if len(self.clients) > 50:
                expired = [ip for ip, stamps in self.clients.items() if not stamps or stamps[-1] <= cutoff]
                for ip in expired:
                    del self.clients[ip]

            timestamps = self.clients.get(client_ip, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]
            if len(valid_timestamps) >= self.max_requests:
                self.clients[client_ip] = valid_timestamps
                return False
            valid_timestamps.append(now)
            self.clients[client_ip] = valid_timestamps
            return True


rate_limiter = SlidingWindowRateLimiter(
    max_requests=settings.rate_limit_max,
    window_seconds=settings.rate_limit_window_s,
)


def check_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    # Only trust X-Forwarded-For if configured behind a trusted reverse proxy
    if settings.trust_proxy and client_ip in settings.trusted_proxies:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip_candidate = forwarded.split(",")[0].strip()
            if ip_candidate:
                client_ip = ip_candidate

    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests from this IP. Rate limit of {settings.rate_limit_max} requests per minute exceeded. Please try again shortly.",
        )


# --------------------------------------------------------------------------
# API Key Authentication Dependency
# --------------------------------------------------------------------------
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="API Key provided via X-API-Key header")
bearer_scheme = HTTPBearer(auto_error=False, description="Bearer token provided via Authorization: Bearer <token>")


def authenticate_request(
    x_api_key: Optional[str] = Security(api_key_header),
    bearer_auth: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    request: Request = None,
):
    """
    Validates API key from X-API-Key header or Authorization: Bearer token.
    - If auth is disabled (AUTH_REQUIRED=false and no keys configured), allows request.
    - If auth is required but no keys are configured on the server, rejects with 503.
    - If missing or invalid key, rejects with 401.
    """
    auth_enforced = settings.auth_required
    if not auth_enforced:
        return True

    if not settings.api_keys:
        raise HTTPException(
            status_code=503,
            detail="Authentication is required, but no API keys are configured on the server. Please set INVOICE_API_KEYS in the server environment.",
        )

    token = None
    if x_api_key:
        token = x_api_key.strip()
    elif bearer_auth and bearer_auth.credentials:
        token = bearer_auth.credentials.strip()
    elif request:
        hdr_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
        if hdr_key:
            token = hdr_key.strip()
        else:
            auth_hdr = request.headers.get("authorization", "")
            if auth_hdr.lower().startswith("bearer "):
                token = auth_hdr[7:].strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized. Missing API key. Provide via 'X-API-Key' header or 'Authorization: Bearer <token>'.",
        )

    is_valid = any(secrets.compare_digest(token, allowed_key) for allowed_key in settings.api_keys)
    if is_valid:
        return True

    raise HTTPException(
        status_code=401,
        detail="Unauthorized. Invalid API key. Provide a valid key via 'X-API-Key' header or 'Authorization: Bearer <token>'.",
    )


# --------------------------------------------------------------------------
# Request Context Middleware
# --------------------------------------------------------------------------
@app.middleware("http")
async def request_context(request: Request, call_next):
    raw_rid = request.headers.get("X-Request-ID")
    if raw_rid:
        # Sanitize and cap length to 64 chars to prevent header echoing vulnerabilities
        clean_rid = "".join(c for c in raw_rid if c.isalnum() or c in ("-", "_"))[:64]
        request.state.request_id = clean_rid or uuid.uuid4().hex[:12]
    else:
        request.state.request_id = uuid.uuid4().hex[:12]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


# --------------------------------------------------------------------------
# Exception Handlers
# --------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    rid = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "request_id": rid,
            "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "detail": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
    log.exception("[%s] Unhandled server error: %s", rid, exc)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "request_id": rid,
            "message": "Internal processing error. Could not process document.",
            "detail": "An internal error occurred while processing the request.",
        },
    )


# --------------------------------------------------------------------------
# Web UI Static Mount & Discovery Endpoints
# --------------------------------------------------------------------------
WEB_DIR = Path(__file__).parent / "web"
if WEB_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")


@app.get("/", tags=["ops"], include_in_schema=False)
def root(request: Request):
    """
    Redirects browser visitors to /ui/, or returns service metadata JSON for API clients.
    """
    accept = request.headers.get("accept", "").lower()
    if "text/html" in accept and WEB_DIR.is_dir():
        return RedirectResponse("/ui/")

    return {
        "status": "ok",
        "message": "GoFloaters Enterprise Invoice Parser REST API",
        "auth_enabled": bool(settings.api_keys),
        "endpoints": {
            "health": "GET /health",
            "invoice": "POST /api/invoice (multipart/form-data, field: 'file')",
            "extract": "POST /v1/extract (multipart/form-data, field: 'file')",
            "ui": "GET /ui/",
            "docs": "GET /docs",
        },
    }


@app.get("/health", tags=["ops"])
def health():
    """
    Unauthenticated health probe endpoint for Docker / Coolify / K8s monitoring.
    """
    return {
        "status": "ok",
        "uptime": round(time.time() - SERVER_START_TIME),
        "auth_required": settings.auth_required,
        "keys_configured_count": len(settings.api_keys),
        "max_upload_mb": settings.max_upload_mb,
        "rate_limit_max": settings.rate_limit_max,
        "execution_timeout_ms": settings.execution_timeout_ms,
    }


# Helpful browser navigation handler for GET /api/invoice and /v1/extract
@app.get("/api/invoice", tags=["extract"], include_in_schema=False)
@app.get("/v1/extract", tags=["extract"], include_in_schema=False)
def method_not_allowed(request: Request):
    accept = request.headers.get("accept", "").lower()
    if "text/html" in accept and WEB_DIR.is_dir():
        return RedirectResponse("/ui/")

    host = request.headers.get("host") or f"localhost:{settings.port}"
    return JSONResponse(
        status_code=405,
        content={
            "status": "error",
            "message": "Method Not Allowed. Send an HTTP POST request with multipart/form-data (field: 'file'). For browser testing, visit /ui/.",
            "ui_url": f"http://{host}/ui/",
        },
    )


# --------------------------------------------------------------------------
# Core Extraction Engine
# --------------------------------------------------------------------------
async def execute_invoice_extraction(
    request: Request,
    file: UploadFile,
    is_extract_mode: bool,
) -> dict:
    """
    Processes an invoice file through the full parsing pipeline:
    1. Validates file extension
    2. Streams file to disk up to size limit
    3. Verifies binary magic-bytes & checks against disguised executables
    4. Executes invoice_parser.main.process with timeout guard and abort signals
    5. Cleans up temporary disk assets safely
    """
    rid = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
    filename = file.filename or "invoice"
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed formats: {sorted(SUPPORTED)}",
        )

    start_time = time.perf_counter()
    timeout_seconds = settings.execution_timeout_ms / 1000.0
    limit_bytes = settings.max_upload_mb * 1024 * 1024

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = Path(temp_file.name)
    abort_event = threading.Event()

    try:
        # Stream file to disk while enforcing max upload size
        size = 0
        try:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum upload limit of {settings.max_upload_mb} MB.",
                    )
                temp_file.write(chunk)
            temp_file.flush()
        finally:
            temp_file.close()

        if size == 0:
            raise HTTPException(status_code=400, detail="Invoice file is required and cannot be empty.")

        # 1. Binary Magic-Byte Security Check
        magic_check = inspect_magic_bytes(temp_path)
        if not magic_check["valid"]:
            raise HTTPException(status_code=400, detail=magic_check["reason"])

        pipeline_logger.info(f"UPLOAD RECEIVED | {filename} | size={size} bytes")

        # 2. Worker Execution Function
        def run_parser_process():
            with contextlib.redirect_stdout(sys.stderr):
                return process(
                    str(temp_path),
                    display_name=filename,
                    timeout=timeout_seconds,
                    abort_event=abort_event,
                )

        # 3. Execute with execution timeout guard
        try:
            parsed_data = await asyncio.wait_for(
                run_in_threadpool(run_parser_process),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            abort_event.set()
            pipeline_logger.error(f"UPLOAD TIMED OUT | {filename} | timeout={timeout_seconds}s")
            raise HTTPException(
                status_code=408,
                detail=f"Invoice processing timed out after {int(timeout_seconds)} seconds.",
            )
        except (FileNotFoundError, ValueError, RuntimeError) as val_err:
            pipeline_logger.exception(f"UPLOAD FAILED | {filename} | error={val_err}")
            raise HTTPException(
                status_code=422,
                detail="The uploaded document is corrupted, unreadable, or invalid.",
            )

        elapsed_ms = (
            parsed_data.get("step_timings_ms", {}).get("total_elapsed_ms")
            if isinstance(parsed_data.get("step_timings_ms"), dict)
            else round((time.perf_counter() - start_time) * 1000, 1)
        )

        valid_status = "ok" if parsed_data.get("validation", {}).get("status") == "valid" else "needs_review"
        pipeline_logger.info(f"UPLOAD COMPLETED | {filename} | status={valid_status} | total_api_time={elapsed_ms}ms")

        return {
            "status": valid_status if is_extract_mode else "success",
            "request_id": rid,
            "filename": filename,
            "elapsed_ms": int(elapsed_ms),
            "data": parsed_data,
        }

    finally:
        # Guaranteed cleanup of uploaded temporary file
        try:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
        except Exception as clean_err:
            log.warning(f"Failed to cleanup temp file {temp_path}: {clean_err}")


# --------------------------------------------------------------------------
# API Extraction Endpoints
# --------------------------------------------------------------------------
@app.post(
    "/api/invoice",
    tags=["extract"],
    summary="Extract and validate invoice data (Express REST API compatible)",
    dependencies=[Depends(check_rate_limit), Depends(authenticate_request)],
)
async def extract_invoice_legacy(
    request: Request,
    file: UploadFile = File(..., description="Invoice file (PDF, PNG, JPG, TIFF, BMP, Office doc)"),
):
    """
    Primary endpoint returning standard enterprise status ('success' or error).
    Matches Node.js Express REST API POST /api/invoice specification.
    """
    return await execute_invoice_extraction(request, file, is_extract_mode=False)


@app.post(
    "/v1/extract",
    tags=["extract"],
    summary="Extract and validate invoice data (v1 specification)",
    dependencies=[Depends(check_rate_limit), Depends(authenticate_request)],
)
async def extract_invoice_v1(
    request: Request,
    file: UploadFile = File(..., description="Invoice file (PDF, PNG, JPG, TIFF, BMP, Office doc)"),
):
    """
    Extraction endpoint returning compliance status ('ok' or 'needs_review').
    Matches REST API POST /v1/extract specification.
    """
    return await execute_invoice_extraction(request, file, is_extract_mode=True)


# --------------------------------------------------------------------------
# Direct CLI Runner
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    print(f"\n[FastAPI] Starting GoFloaters Invoice Parser API on http://{settings.host}:{settings.port}")
    print(f"[FastAPI] Web UI: http://localhost:{settings.port}/ui/")
    print(f"[FastAPI] Swagger Docs: http://localhost:{settings.port}/docs")
    print(f"[FastAPI] Rate Limiting: {settings.rate_limit_max} req / {settings.rate_limit_window_s}s")
    print(f"[FastAPI] Execution Timeout: {settings.execution_timeout_ms / 1000}s")
    print(f"[FastAPI] Auth Required: {bool(settings.api_keys)}\n")

    uvicorn.run(
        "invoice_parser.api:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
