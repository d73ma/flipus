from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str
    SECRET_KEY_PREVIOUS: str = ""  # Optional: dual-key rotation grace window
    ALGORITHM: str = "HS256"
    # FASE 3-S3.S8 — diperpendek dari 8 jam (480) ke 15 menit, dikompensasi
    # dengan refresh token 7 hari. Best practice OWASP JWT cheat sheet:
    # access token < 30 min, refresh token > 1 hari, refresh stored server-side.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PII_ENCRYPTION_KEY: str
    # FASE 3-S2.T3 — dual-key rotation window untuk PII Fernet.
    # Saat rotasi:
    #   1. Set PII_ENCRYPTION_KEY = new_key (encrypt pakai new_key)
    #   2. Set PII_ENCRYPTION_KEY_PREVIOUS = old_key (decrypt fallback)
    #   3. Jalankan maintenance script `rotate_pii_to_new_key.py` untuk
    #      re-encrypt semua ciphertext existing ke new_key
    #   4. Kosongkan PII_ENCRYPTION_KEY_PREVIOUS setelah selesai.
    PII_ENCRYPTION_KEY_PREVIOUS: str = ""
    LICENSE_TENANT_SIGNATURE_SALT: str = "UKIKT_FLIPUS_2026_NATAAN_RATAHAN_SALT"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5vl:7b"
    GEMINI_API_KEY: str = ""
    # Override via env GEMINI_MODEL. Default ke 1.5-flash (paling stabil sejak 2024).
    # Valid: gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash, gemini-2.5-flash, dll.
    # Catatan: nama seperti "gemini-3.6-flash" bukan release resmi Google.
    GEMINI_MODEL: str = "gemini-1.5-flash"

    DATABASE_URL_LOCAL: str = "sqlite:///./flipus_local.db"
    DATABASE_URL_CLOUD: str = "postgresql://user:pass@localhost/flipus_cloud"

    WA_API_URL: str = "https://api.fonnte.com/send"
    WA_API_TOKEN: str = ""

    DEFAULT_UNI: str = "Uni Konferens Indonesia Kawasan Timur (UKIKT)"

    # ===== Security hardening (v1.4) =====
    LOGIN_MAX_ATTEMPTS: int = 5  # failed attempts before lockout
    LOGIN_LOCKOUT_MINUTES: int = 15  # lockout duration in minutes
    # DEFAULT TRUE: production-ready. Sensitive roles wajib 2FA.
    # Flip ke False HANYA untuk demo/seed awal dengan disable 2FA di seed.
    ENFORCE_2FA_FOR_SENSITIVE_ROLES: bool = True

    # ===== CORS (v1.5) =====
    # Comma-separated list of allowed origins. Default: localhost dev only.
    # Production: set ALLOWED_ORIGINS=https://gmahk.flipus.org,https://flipus.org
    # LAN origins (192.168.x.x, 10.x.x.x, 172.16-31.x.x) auto-allowed via regex di main.py
    # untuk demo offline multi-device di Wi-Fi lokal.
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    # ===== FASE 3-S3.S1 — Logging =====
    # Log level untuk root logger. Valid: DEBUG, INFO, WARNING, ERROR.
    # Default INFO untuk production. Set DEBUG via env LOG_LEVEL=DEBUG untuk
    # verbose development. JSONFormatter handles structure (see app/core/logger.py).
    LOG_LEVEL: str = "INFO"

    # ===== Admin endpoints (v1.5) =====
    # Shared secret untuk endpoint kritis (POST /seed, /register-tenant, /restore-db).
    # Set via ADMIN_BOOTSTRAP_TOKEN di .env (generate dengan `openssl rand -hex 32`).
    # Kalau kosong, endpoint tetap diproteksi dengan require_admin_bootstrap().
    ADMIN_BOOTSTRAP_TOKEN: str = ""

    # ===== Fonnte reliability (v1.5) =====
    WA_BLAST_RATE_PER_SEC: float = 1.1  # sleep antar call (Fonnte ~60 req/min)
    WA_BLAST_MAX_RETRIES: int = 3
    WA_BLAST_RETRY_BACKOFF: float = 2.0  # exponential: 2s, 4s, 8s

settings = Settings()
