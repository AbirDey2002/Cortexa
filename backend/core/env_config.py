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


# PF configuration removed from codebase


def get_smtp_config() -> dict:
    return {
        "SMTP_SERVER": os.getenv("SMTP_SERVER", ""),
        "SMTP_PORT": os.getenv("SMTP_PORT", "25"),
        "SMTP_USERNAME": os.getenv("SMTP_USERNAME", ""),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD", ""),
    }


def get_auth0_config() -> dict:
    import logging
    logger = logging.getLogger(__name__)
    
    config = {
        "AUTH0_DOMAIN": os.getenv("AUTH0_DOMAIN", ""),
        "AUTH0_CLIENT_ID": os.getenv("AUTH0_CLIENT_ID", ""),
        "AUTH0_CLIENT_SECRET": os.getenv("AUTH0_CLIENT_SECRET", ""),
        "AUTH0_AUDIENCE": os.getenv("AUTH0_AUDIENCE", ""),
        # M2M credentials for Management API (optional, falls back to regular credentials)
        "AUTH0_M2M_CLIENT_ID": os.getenv("AUTH0_M2M_CLIENT_ID", ""),
        "AUTH0_M2M_CLIENT_SECRET": os.getenv("AUTH0_M2M_CLIENT_SECRET", ""),
    }
    
    # Log config values (mask secret)
    logger.error("\033[91m[ENV-CONFIG] Auth0 Configuration:\033[0m")
    logger.error(f"\033[91m[ENV-CONFIG] AUTH0_DOMAIN: {config['AUTH0_DOMAIN'] or 'NOT SET'}\033[0m")
    logger.error(f"\033[91m[ENV-CONFIG] AUTH0_CLIENT_ID: {config['AUTH0_CLIENT_ID'] or 'NOT SET'}\033[0m")
    logger.error(f"\033[91m[ENV-CONFIG] AUTH0_CLIENT_SECRET: {'SET' if config['AUTH0_CLIENT_SECRET'] else 'NOT SET'} (length: {len(config['AUTH0_CLIENT_SECRET']) if config['AUTH0_CLIENT_SECRET'] else 0})\033[0m")
    logger.error(f"\033[91m[ENV-CONFIG] AUTH0_AUDIENCE: {config['AUTH0_AUDIENCE'] or 'NOT SET'}\033[0m")
    logger.error(f"\033[91m[ENV-CONFIG] AUTH0_M2M_CLIENT_ID: {config['AUTH0_M2M_CLIENT_ID'] or 'NOT SET (will use AUTH0_CLIENT_ID)'}\033[0m")
    logger.error(f"\033[91m[ENV-CONFIG] AUTH0_M2M_CLIENT_SECRET: {'SET' if config['AUTH0_M2M_CLIENT_SECRET'] else 'NOT SET (will use AUTH0_CLIENT_SECRET)'} (length: {len(config['AUTH0_M2M_CLIENT_SECRET']) if config['AUTH0_M2M_CLIENT_SECRET'] else 0})\033[0m")
    
    return config


def get_aws_config() -> dict:
    return {
        "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_SESSION_TOKEN": os.getenv("AWS_SESSION_TOKEN", ""),
        "AWS_REGION": os.getenv("AWS_REGION", "us-east-1"),
        "S3_BUCKET_NAME": os.getenv("S3_BUCKET_NAME", ""),
    }


def get_gemini_config() -> dict:
    return {
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
    }


def get_env_variable(key: str, default: str = "") -> str:
    """
    Get environment variable value.
    
    Args:
        key (str): Environment variable key
        default (str): Default value if key not found
        
    Returns:
        str: Environment variable value or default
    """
    return os.getenv(key, default)


def get_deepagents_config() -> dict:
    """
    Return DeepAgents-related configuration from environment.
    """
    return {
        "DEEPAGENTS_API_KEY": os.getenv("DEEPAGENTS_API_KEY", ""),
        "DEEPAGENTS_BASE_URL": os.getenv("DEEPAGENTS_BASE_URL", ""),
        # Default to disabling auth locally if not explicitly provided
        "DEEPAGENTS_DISABLE_AUTH": os.getenv("DEEPAGENTS_DISABLE_AUTH", "true"),
        # Some builds require explicitly omitting auth headers
        "DEEPAGENTS_OMIT_AUTH_HEADERS": os.getenv("DEEPAGENTS_OMIT_AUTH_HEADERS", "true"),
        # Optional hints for model/provider selection
        "DEEPAGENTS_MODEL_PROVIDER": os.getenv("DEEPAGENTS_MODEL_PROVIDER", "google-generativeai"),
        "DEEPAGENTS_MODEL_NAME": os.getenv("DEEPAGENTS_MODEL_NAME", "gemini-2.5-flash"),
    }

