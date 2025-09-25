import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class EnvConfig:
    """
    Minimal environment configuration helpers to mirror the reference app's
    env_config interface. Provides typed getters for DB, Azure, and misc configs.
    """

    def __init__(self) -> None:
        # Environment name (default/local/dev/qa/prod)
        self.environment = os.getenv("ENVIRONMENT", "default")


env_config = EnvConfig()


def get_config_value(key: str, default: str | None = None) -> str:
    return os.getenv(key, default or "")


def get_database_config() -> dict:
    return {
        "DB_USER": os.getenv("DB_USER", "postgres"),
        "DB_PASSWORD": os.getenv("DB_PASSWORD", "postgres"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
        "DB_NAME": os.getenv("DB_NAME", "cortexa"),
        "DB_SSL_MODE": os.getenv("DB_SSL_MODE", "disable"),
    }


def get_azure_config() -> dict:
    return {
        "AZURE_SUBSCRIPTION_ID": os.getenv("AZURE_SUBSCRIPTION_ID", ""),
        "AZURE_CONTAINER_NAME": os.getenv("AZURE_CONTAINER_NAME", "uploads"),
        "AZURE_CONNECTION_STRING": os.getenv("AZURE_CONNECTION_STRING", ""),
    }


def get_pf_config() -> dict:
    return {
        "PF_BASE_URL": os.getenv("PF_BASE_URL", ""),
        "PF_PROFILES": os.getenv("PF_PROFILES", "{}"),
        "PF_USERNAME": os.getenv("PF_USERNAME", ""),
        "PF_PASSWORD": os.getenv("PF_PASSWORD", ""),
        "ASSET_ID": os.getenv("ASSET_ID", ""),
        "API_KEY": os.getenv("API_KEY", ""),
        "PF_USER_ID": os.getenv("PF_USER_ID", ""),
        "PF_API_KEY": os.getenv("PF_API_KEY", ""),
        "PF_TENANT_ID": os.getenv("PF_TENANT_ID", ""),
    }


def get_smtp_config() -> dict:
    return {
        "SMTP_SERVER": os.getenv("SMTP_SERVER", ""),
        "SMTP_PORT": os.getenv("SMTP_PORT", "25"),
        "SMTP_USERNAME": os.getenv("SMTP_USERNAME", ""),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD", ""),
    }


def get_auth0_config() -> dict:
    return {
        "AUTH0_DOMAIN": os.getenv("AUTH0_DOMAIN", ""),
        "AUTH0_CLIENT_ID": os.getenv("AUTH0_CLIENT_ID", ""),
    }


def get_aws_config() -> dict:
    return {
        "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_SESSION_TOKEN": os.getenv("AWS_SESSION_TOKEN", ""),
        "AWS_REGION": os.getenv("AWS_REGION", "us-east-1"),
        "S3_BUCKET_NAME": os.getenv("S3_BUCKET_NAME", ""),
    }

