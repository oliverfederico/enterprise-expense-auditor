"""Configuration and settings for the Expense Policy Compliance Auditor."""

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Automatically load environment variables from .env / app_config.env into os.environ
load_dotenv(".env")
load_dotenv("app_config.env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", "app_config.env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google Gemini LLM settings
    google_api_key: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
    )
    gemini_model: str = Field(default="gemini-3.8-flash")
    gemini_temperature: float = Field(default=0.0)

    # LangSmith Observability & Tracing
    langchain_tracing_v2: bool = Field(
        default_factory=lambda: os.getenv("LANGCHAIN_TRACING_V2", "").lower() in ("true", "1")
        or os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1")
    )
    langchain_endpoint: str = Field(
        default_factory=lambda: os.getenv("LANGCHAIN_ENDPOINT")
        or os.getenv("LANGSMITH_ENDPOINT")
        or "https://api.smith.langchain.com"
    )
    langchain_api_key: str = Field(
        default_factory=lambda: os.getenv("LANGCHAIN_API_KEY")
        or os.getenv("LANGSMITH_API_KEY")
        or ""
    )
    langchain_project: str = Field(
        default_factory=lambda: os.getenv("LANGCHAIN_PROJECT")
        or os.getenv("LANGSMITH_PROJECT")
        or "enterprise-expense-auditor"
    )

    # Policy settings & document location
    policy_document_path: Path = Field(
        default=Path(__file__).parent.parent.parent / "docs" / "policy_document.md"
    )

    # Core Policy Thresholds
    per_diem_daily_limit: float = Field(default=75.00)
    alcohol_max_ratio: float = Field(default=0.20)
    transit_max_minutes_for_rideshare_ban: int = Field(default=15)
    client_entertainment_per_person_limit: float = Field(default=150.00)
    itemized_receipt_required_threshold: float = Field(default=25.00)


settings = Settings()

# Synchronize os.environ so LangChain, LangSmith, and external SDKs pick up tracing immediately
if settings.google_api_key:
    if not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key
    if not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = settings.google_api_key

if settings.langchain_api_key:
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGSMITH_API_KEY"] = settings.langchain_api_key

if settings.langchain_tracing_v2:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"

if settings.langchain_project:
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGSMITH_PROJECT"] = settings.langchain_project

if settings.langchain_endpoint:
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint
    os.environ["LANGSMITH_ENDPOINT"] = settings.langchain_endpoint
