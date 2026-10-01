from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All config comes from environment variables / .env (never hard-code keys)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openai/gpt-4o-mini"
    llm_temperature: float = 0.0

    batch_max_concurrency: int = 5
    max_upload_rows: int = 200
    sample_csv_path: str = "data/sample_vendor_rows.csv"

    # Supabase (Postgres). Use the service-role key; it stays on the server.
    supabase_url: str = ""
    supabase_service_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
