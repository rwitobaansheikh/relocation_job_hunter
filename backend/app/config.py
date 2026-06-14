from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env regardless of process working directory.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM (local Ollama by default; cloud Gemini optional) ---
    llm_provider: str = "ollama"  # ollama | gemini
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: float = 300.0
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    rocketreach_api_key: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    database_url: str = "sqlite:///./job_hunter.db"
    max_jobs_per_search: int = 100
    max_emails_per_company: int = 5
    job_age_hours: int = 48
    uploads_dir: str = "uploads"
    generated_dir: str = "generated"
    static_dir: str = "static"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- Auth / security ---
    # JWT signing secret and access-token lifetime. CHANGE jwt_secret in prod.
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    # Fernet key (urlsafe base64, 32 bytes) for encrypting per-user secrets such
    # as SMTP passwords. If empty, a key is derived from jwt_secret (dev only).
    encryption_key: str = ""
    # Bootstrap admin: created on startup if it does not already exist.
    admin_email: str = ""
    admin_password: str = ""

    # --- Shared-key global rate limits (hybrid model) ---
    # Requests/minute budgeted across ALL users for the shared API keys.
    llm_rate_per_min: int = 60
    gemini_rate_per_min: int = 12
    rocketreach_rate_per_min: int = 10
    # Safety ceiling for daily outbound emails per user (overridable per profile).
    default_daily_send_cap: int = 20
    default_per_domain_cap: int = 2
    default_automation_interval_hours: int = 12
    default_max_tailor_per_run: int = 5
    # Global kill-switch for the automation scheduler (admin-controllable).
    automation_globally_enabled: bool = True
    # Background scheduler: how often to check for due automation runs.
    scheduler_enabled: bool = True
    scheduler_tick_minutes: int = 30

    # --- Billing (Stripe) ---
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""
    # Recurring Price IDs created in the Stripe dashboard (one USD price per
    # tier; Adaptive Pricing handles local-currency conversion at Checkout).
    stripe_price_basic: str = ""
    stripe_price_standard: str = ""
    stripe_price_pro: str = ""
    # Public base URL for Checkout success/cancel + portal return.
    app_base_url: str = "http://localhost:5173"

    # Where "Contact us" messages are delivered (the site owner's inbox).
    contact_email: str = "rwitobaansheikh@gmail.com"
    # Length of the free trial granted to new accounts.
    trial_days: int = 7

    # --- OAuth (Google & LinkedIn) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    # Frontend callback URL after OAuth (defaults to {APP_BASE_URL}/auth/callback when empty)
    oauth_frontend_callback_url: str = ""


settings = Settings()
