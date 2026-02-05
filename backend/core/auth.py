from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient, PyJWTError
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError
import requests
import logging
from typing import Dict, Any
from core.env_config import get_auth0_config

logger = logging.getLogger(__name__)
security = HTTPBearer()

# Cache for JWKS client
_jwks_client: PyJWKClient = None
_jwks_url: str = ""


def get_jwks_url(domain: str) -> str:
    """Get the JWKS URL for Auth0 domain."""
    return f"https://{domain}/.well-known/jwks.json"


def get_jwks_client(domain: str) -> PyJWKClient:
    """Get or create cached JWKS client for Auth0."""
    global _jwks_client, _jwks_url
    
    jwks_url = get_jwks_url(domain)
    
    # Return cached client if available and URL matches
    if _jwks_url == jwks_url and _jwks_client:
        return _jwks_client
    
    try:
        _jwks_client = PyJWKClient(jwks_url)
        _jwks_url = jwks_url
        return _jwks_client
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to initialize JWKS client: {str(e)}"
        )


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Verify JWT token from Auth0 OR Local Auth.
    
    Returns the decoded token payload if valid.
    Raises HTTPException if token is invalid.
    """
    token = credentials.credentials
    
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authorization token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    auth0_config = get_auth0_config()
    domain = auth0_config.get("AUTH0_DOMAIN")
    audience = auth0_config.get("AUTH0_AUDIENCE")
    
    if not domain:
        raise HTTPException(
            status_code=500,
            detail="AUTH0_DOMAIN not configured"
        )
    
    if not audience:
        raise HTTPException(
            status_code=500,
            detail="AUTH0_AUDIENCE not configured"
        )
    
    try:
        # Get JWKS client
        jwks_client = get_jwks_client(domain)
        
        # Get signing key from JWKS
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Verify and decode token with explicit algorithm restriction (security best practice)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],  # Explicitly allow only RS256 to prevent algorithm confusion attacks
            audience=audience,
            issuer=f"https://{domain}/"
        )
        
        return payload
        
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token verification failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

