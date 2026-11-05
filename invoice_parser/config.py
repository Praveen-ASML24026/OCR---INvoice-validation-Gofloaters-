import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class Settings:
    api_keys: frozenset = field(
        default_factory=lambda: frozenset(
            k.strip()
            for k in (os.getenv("INVOICE_API_KEYS", "") or os.getenv("API_KEY", "")).split(",")
            if k.strip()
        )
    )
    auth_required: bool = field(
        default_factory=lambda: (
            os.getenv("AUTH_REQUIRED", "true").lower() in ("true", "1", "yes")
        )
    )
    trust_proxy: bool = field(
        default_factory=lambda: (
            os.getenv("TRUST_PROXY", "false").lower() in ("true", "1", "yes")
        )
    )
    trusted_proxies: frozenset = field(
        default_factory=lambda: frozenset(
            k.strip() for k in os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if k.strip()
        )
    )
    max_upload_mb: int = int(os.getenv("INVOICE_MAX_UPLOAD_MB", "20"))
    log_level: str = os.getenv("INVOICE_LOG_LEVEL", "INFO")
    state_mismatch_exempt: frozenset = field(
        default_factory=lambda: frozenset(
            k.strip() for k in os.getenv("INVOICE_STATE_MISMATCH_EXEMPT", "07,36,32").split(",") if k.strip()
        )
    )
    port: int = int(os.getenv("PORT", "8000"))
    host: str = os.getenv("HOST", "0.0.0.0")
    execution_timeout_ms: int = int(os.getenv("EXECUTION_TIMEOUT_MS", "120000"))
    rate_limit_max: int = int(os.getenv("RATE_LIMIT_MAX", "60"))
    rate_limit_window_s: int = int(os.getenv("RATE_LIMIT_WINDOW_S", "60"))


settings = Settings()
