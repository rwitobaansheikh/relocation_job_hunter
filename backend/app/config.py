from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    hunter_api_key: str = ""
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


settings = Settings()
