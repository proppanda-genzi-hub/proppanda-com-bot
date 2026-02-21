from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    # Application Settings
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    
    # Database Settings
    DATABASE_URL: str = ""
    
    # Redis Settings
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SESSION_TTL: int = 86400
    
    # OpenAI Settings
    OPENAI_API_KEY: str = ""
    
    # LocationIQ Settings (for geocoding)
    LOCATION_IQ_KEY: str = ""
    
    # Connection Pool Settings
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    
    # Session Settings
    SESSION_TIMEOUT_MINUTES: int = 30
    
    # Validate database URL format
    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: Optional[str]) -> str:
        if not v:
            raise ValueError("DATABASE_URL is not set in environment variables")
        if not v.startswith(("postgresql://", "postgresql+asyncpg://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must start with postgresql:// or postgresql+asyncpg://")
        # Ensure asyncpg driver is used for async operations
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

# Create settings instance
settings = Settings()
