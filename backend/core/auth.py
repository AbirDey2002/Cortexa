from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, jwk
from jose.utils import base64url_decode
import requests
import logging
from typing import Dict, Any
from core.env_config import get_auth0_config

logger = logging.getLogger(__name__)
security = HTTPBearer()

# Cache for JWKS
_jwks_cache: Dict[str, Any] = {}
_jwks_url: str = ""


def get_jwks_url(domain: str) -> str:
    """Get the JWKS URL for Auth0 domain."""
    return f"https://{domain}/.well-known/jwks.json"


def get_jwks(domain: str) -> Dict[str, Any]:
    """Fetch and cache JWKS from Auth0."""
    global _jwks_cache, _jwks_url
    
    jwks_url = get_jwks_url(domain)
    
    # Return cached JWKS if available and URL matches
    if _jwks_url == jwks_url and _jwks_cache:
        return _jwks_cache
    
    try:
        response = requests.get(jwks_url, timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_url = jwks_url
        return _jwks_cache
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch JWKS: {str(e)}"
        )


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Verify JWT token from Auth0.
    
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
        # Get JWKS
        jwks = get_jwks(domain)
        
        # Get unverified header to find the key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid:
            raise HTTPException(
                status_code=401,
                detail="Token missing 'kid' in header"
            )
        
        # Find the key with matching kid
        rsa_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = key
                break
        
        if not rsa_key:
            raise HTTPException(
                status_code=401,
                detail=f"Unable to find key with kid: {kid}"
            )
        
        # Convert JWK to RSA key
        public_key = jwk.construct(rsa_key)
        
        # Verify and decode token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=f"https://{domain}/"
        )
        
        return payload
        
    except JWTError as e:
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

