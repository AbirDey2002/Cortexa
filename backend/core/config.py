from pydantic_settings import BaseSettings
from pydantic import model_validator
from .env_config import (
    get_database_config,
    get_azure_config,
    get_smtp_config,
    get_auth0_config,
    env_config,
    get_config_value,
    get_aws_config,
)
import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend/.env is loaded into process env before any os.getenv calls
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
try:
    load_dotenv(_ENV_PATH, override=True)
except Exception:
    # fallback to default loader
    load_dotenv(override=True)


class DatabasePoolConfigs:
    POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
    MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "50"))
    POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "60"))
    POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))
    POOL_PRE_PING = os.getenv("DB_POOL_PRE_PING", "true").lower() == "true"
    ECHO = os.getenv("DB_ECHO", "false").lower() == "true"

class OCRServiceConfigs:
    NUM_FILES_PER_BACKGROUND_TASK = int(os.getenv("OCR_NUM_FILES_PER_TASK", "2"))
    NUM_WORKERS = int(os.getenv("OCR_NUM_WORKERS", "20"))
    MAX_RETRIES = int(os.getenv("OCR_MAX_RETRIES", "3"))
    BATCH_SIZE = int(os.getenv("OCR_BATCH_SIZE", "1"))
    
    # Security: Control OCR text logging to prevent sensitive content exposure
    LOG_OCR_TEXT = os.getenv("LOG_OCR_TEXT", "false").lower() == "true"
    OCR_TEXT_LOG_MAX_LENGTH = int(os.getenv("OCR_TEXT_LOG_MAX_LENGTH", "200"))  # Limit logged text length


class FileProcessingConfigs:
    """Security: File upload limits and allowed types"""
    # Max file size in bytes (default: 50MB)
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(50 * 1024 * 1024)))
    
    # Allowed file extensions
    ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".md"}
    
    # Allowed MIME types
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "text/plain",
        "text/markdown"
    }


class AgentLogConfigs:
    # Toggle logging of agent system prompts and raw outputs (ANSI yellow)
    LOG_AGENT_SYSTEM_PROMPT = os.getenv("LOG_AGENT_SYSTEM_PROMPT", "false").lower() == "true"
    LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH = int(os.getenv("LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH", "10000"))
    LOG_AGENT_RAW_OUTPUT = os.getenv("LOG_AGENT_RAW_OUTPUT", "false").lower() == "true"
    LOG_AGENT_RAW_OUTPUT_MAX_LENGTH = int(os.getenv("LOG_AGENT_RAW_OUTPUT_MAX_LENGTH", "20000"))


class Settings(BaseSettings):
    _db_config = get_database_config()
    _azure_config = get_azure_config()
    _smtp_config = get_smtp_config()
    _auth0_config = get_auth0_config()
    _aws_config = get_aws_config()

    DB_USER: str = _db_config["DB_USER"]
    DB_PASSWORD: str = _db_config["DB_PASSWORD"]
    DB_HOST: str = _db_config["DB_HOST"]
    DB_PORT: str = _db_config["DB_PORT"]
    DB_NAME: str = _db_config["DB_NAME"]
    DB_SSL_MODE: str = _db_config.get("DB_SSL_MODE", "disable")

    @model_validator(mode="after")
    def adjust_host_for_docker(self) -> "Settings":
        # Check RUN_MODE
        run_mode = os.getenv("RUN_MODE", "local").lower()
        # print(f"DEBUG: Model Validator called. HOST={self.DB_HOST}, RUN_MODE={run_mode}")
        if run_mode == "docker" and self.DB_HOST in ("localhost", "127.0.0.1", "0.0.0.0"):
             self.DB_HOST = "host.docker.internal"
        return self

    # PF removed

    AZURE_SUBSCRIPTION_ID: str = _azure_config.get("AZURE_SUBSCRIPTION_ID", "")
    AZURE_CONTAINER_NAME: str = _azure_config.get("AZURE_CONTAINER_NAME", "uploads")
    AZURE_CONNECTION_STRING: str = _azure_config.get("AZURE_CONNECTION_STRING", "")
    AZURE_CONTAINER_URL: str = os.getenv(
        "AZURE_CONTAINER_URL",
        f"https://example.blob.core.windows.net/{_azure_config.get('AZURE_CONTAINER_NAME', 'uploads')}",
    )

    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    AWS_ACCESS_KEY_ID: str = _aws_config.get("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = _aws_config.get("AWS_SECRET_ACCESS_KEY", "")
    AWS_SESSION_TOKEN: str = _aws_config.get("AWS_SESSION_TOKEN", "")
    AWS_REGION: str = _aws_config.get("AWS_REGION", "us-east-1")
    S3_BUCKET_NAME: str = _aws_config.get("S3_BUCKET_NAME", "")

    FILE_STORAGE_PROVIDER: str = os.getenv(
        "FILE_STORAGE_PROVIDER",
        "local" if env_config.environment.lower() == "local" else "azure",
    )

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"


settings = Settings()


class DatabaseConfigs:
    _ssl_params = f"?sslmode={settings.DB_SSL_MODE}" if settings.DB_SSL_MODE else ""
    DATABASE_URL = (
        f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/"
        f"{settings.DB_NAME}{_ssl_params}"
    )


class AzureBlobStorageConfigs:
    SUBSCRIPTION_ID = settings.AZURE_SUBSCRIPTION_ID
    CONTAINER_NAME = settings.AZURE_CONTAINER_NAME
    CONTAINER_URL = settings.AZURE_CONTAINER_URL
    CONNECTION_STRING = settings.AZURE_CONNECTION_STRING


class S3StorageConfigs:
    ACCESS_KEY_ID = settings.AWS_ACCESS_KEY_ID
    SECRET_ACCESS_KEY = settings.AWS_SECRET_ACCESS_KEY
    SESSION_TOKEN = settings.AWS_SESSION_TOKEN
    REGION = settings.AWS_REGION
    BUCKET_NAME = settings.S3_BUCKET_NAME


class FileStorageConfigs:
    PROVIDER = settings.FILE_STORAGE_PROVIDER


class HostingConfigs:
    HOST = settings.HOST
    PORT = settings.PORT
    URL = f"http://{HOST}:{PORT}"


class CORSConfigs:
    """CORS configuration for API security"""
    # Get allowed origins from environment variable
    # Format: comma-separated list of origins
    # Example: http://localhost:5173,https://yourdomain.com
    _origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:8080")
    ALLOWED_ORIGINS = [origin.strip() for origin in _origins_str.split(",") if origin.strip()]
    
    # In development, allow all origins if explicitly set
    ALLOW_ALL = os.getenv("CORS_ALLOW_ALL", "false").lower() == "true"
    
    @classmethod
    def get_allowed_origins(cls):
        """Get the list of allowed origins for CORS."""
        if cls.ALLOW_ALL:
            return ["*"]
        return cls.ALLOWED_ORIGINS


class RateLimitConfigs:
    """Rate limiting configuration"""
    ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))


class SecurityConfigs:
    """Security-related configurations"""
    # Environment type
    ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
    IS_PRODUCTION = ENVIRONMENT in ["prod", "production"]
    
    # Encryption key validation
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

