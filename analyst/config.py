import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://analyst_ro:analyst_ro@localhost:5433/analytics"
    )
    admin_database_url: str = os.getenv(
        "ADMIN_DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/analytics"
    )
    model: str = os.getenv("LLM_MODEL", "gemini-3.8-flash")
    # Tried in order when LLM_MODEL fails (quota used up, overloaded, timeout).
    fallback_models: tuple[str, ...] = tuple(
        m.strip()
        for m in os.getenv(
            "LLM_FALLBACK_MODELS",
            "gemini-3.8-flash,gemini-3.7-flash,gemini-3.1-flash-lite,gemini-flash-lite-latest",
        ).split(",")
        if m.strip()
    )
    requests_per_minute: float = float(os.getenv("LLM_REQUESTS_PER_MINUTE", "4"))
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "60"))
    max_rows: int = int(os.getenv("MAX_ROWS", "1000"))
    statement_timeout_ms: int = int(os.getenv("STATEMENT_TIMEOUT_MS", "15000"))
    max_sql_retries: int = int(os.getenv("MAX_SQL_RETRIES", "2"))
    business_context: str = (Path(__file__).parent / "business_context.txt").read_text(
        encoding="utf-8"
    )


settings = Settings()
