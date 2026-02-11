"""
환경 변수 및 설정 로드.
"""

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    PROJECT_NAME: str = "Quiz-Generator"
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str | None = None
    OPENAI_TEMPERATURE: float = 0.2
    REQUEST_TIMEOUT: float = 60
    MAX_TRANSCRIPT_CHARS: int = 12000

    # PostgreSQL (pgvector)
    DATABASE_URL: str = "postgresql://app:apppw@localhost:5432/appdb"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
