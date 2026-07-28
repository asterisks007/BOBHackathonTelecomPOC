"""
Application configuration loaded from environment variables.

All IBM service credentials and runtime flags are read from .env (development)
or real env vars (production). NEVER hardcode credentials here.
"""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object — instantiated once per process via get_settings()."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Runtime mode ──────────────────────────────────────────────────────────
    use_mock: bool = Field(default=True, description="Use mocked IBM services when True")

    # ── API Server ────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    allowed_origins: str = Field(default="http://localhost:5173")

    # ── watsonx.ai ────────────────────────────────────────────────────────────
    watsonx_api_key: str = Field(default="")
    watsonx_project_id: str = Field(default="")
    watsonx_url: str = Field(default="https://us-south.ml.cloud.ibm.com")

    # ── IBM NLU ───────────────────────────────────────────────────────────────
    nlu_api_key: str = Field(default="")
    nlu_url: str = Field(default="")

    # ── IBM Cloudant ──────────────────────────────────────────────────────────
    cloudant_url: str = Field(default="")
    cloudant_api_key: str = Field(default="")
    cloudant_db_incidents: str = Field(default="incidents")
    cloudant_db_tickets: str = Field(default="tickets")
    cloudant_db_audit: str = Field(default="audit_trail")
    cloudant_db_knowledge: str = Field(default="knowledge_base")

    # ── Watson Orchestrate & Webhook Security ───────────────────────────
    watson_orchestrate_url: str = Field(default="")
    watson_orchestrate_api_key: str = Field(default="")
    backend_api_key: str = Field(default="")

    # ── ChromaDB (local) ──────────────────────────────────────────────────────
    chroma_persist_dir: str = Field(default="./chroma_data")
    chroma_collection_kb: str = Field(default="telecom_knowledge_base")
    chroma_collection_patterns: str = Field(default="outage_patterns")

    @property
    def allowed_origins_list(self) -> List[str]:
        """Return allowed CORS origins as a list (split on comma)."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def validate_live_credentials(self) -> List[str]:
        """Return list of missing credential names when USE_MOCK=False."""
        missing = []
        if not self.use_mock:
            if not self.watsonx_api_key:
                missing.append("WATSONX_API_KEY")
            if not self.watsonx_project_id:
                missing.append("WATSONX_PROJECT_ID")
            if not self.nlu_api_key:
                missing.append("NLU_API_KEY")
            if not self.cloudant_url:
                missing.append("CLOUDANT_URL")
        return missing


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
