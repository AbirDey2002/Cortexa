"""
Encryption service for securely storing user API keys.
Uses Fernet symmetric encryption (AES-128-CBC with HMAC).
"""
import os
import base64
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_fernet_instance = None


def get_fernet() -> Fernet:
    """
    Get or create a Fernet instance using the ENCRYPTION_KEY from environment.
    The key must be a valid 32-byte base64-encoded string.
    """
    global _fernet_instance
    
    if _fernet_instance is None:
        key = os.getenv("ENCRYPTION_KEY", "")
        environment = os.getenv("ENVIRONMENT", "local").lower()
        
        if not key:
            # In production, reject missing encryption key
            if environment in ["prod", "production"]:
                logger.error("ENCRYPTION_KEY not set in production environment!")
                raise ValueError(
                    "ENCRYPTION_KEY must be set in production. "
                    "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
            
            # Generate a temporary key for development only (NOT production)
            logger.warning(
                "ENCRYPTION_KEY not set! Generating temporary key FOR DEVELOPMENT ONLY. "
                "This is NOT secure for production. Set ENCRYPTION_KEY in .env"
            )
            key = Fernet.generate_key().decode()
            logger.info("Generated temporary ENCRYPTION_KEY for development.")
        
        try:
            _fernet_instance = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as e:
            logger.error(f"Invalid ENCRYPTION_KEY format: {e}")
            raise ValueError(
                "ENCRYPTION_KEY must be a valid Fernet key. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
    
    return _fernet_instance


def encrypt_api_key(plain_key: str) -> str:
    """
    Encrypt an API key and return base64-encoded ciphertext.
    
    Args:
        plain_key: The plaintext API key to encrypt
        
    Returns:
        Base64-encoded encrypted string
    """
    if not plain_key:
        raise ValueError("Cannot encrypt empty key")
    
    fernet = get_fernet()
    encrypted = fernet.encrypt(plain_key.encode())
    return encrypted.decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """
    Decrypt an API key from base64-encoded ciphertext.
    
    Args:
        encrypted_key: Base64-encoded encrypted string
        
    Returns:
        Decrypted plaintext API key
        
    Raises:
        InvalidToken: If decryption fails (wrong key or corrupted data)
    """
    if not encrypted_key:
        raise ValueError("Cannot decrypt empty key")
    
    fernet = get_fernet()
    try:
        decrypted = fernet.decrypt(encrypted_key.encode())
        return decrypted.decode()
    except InvalidToken:
        logger.error("Failed to decrypt API key - invalid token or wrong encryption key")
        raise


def get_key_display_suffix(plain_key: str, length: int = 4) -> str:
    """
    Get the last N characters of a key for display purposes.
    
    Args:
        plain_key: The plaintext API key
        length: Number of characters to show (default 4)
        
    Returns:
        String like "...a1b2" for display
    """
    if not plain_key or len(plain_key) < length:
        return "****"
    return f"...{plain_key[-length:]}"


def validate_encryption_setup() -> bool:
    """
    Validate that encryption is properly configured.
    Returns True if encryption round-trip works.
    """
    try:
        test_value = "test_api_key_12345"
        encrypted = encrypt_api_key(test_value)
        decrypted = decrypt_api_key(encrypted)
        return decrypted == test_value
    except Exception as e:
        logger.error(f"Encryption validation failed: {e}")
        return False
