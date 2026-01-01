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
    logger.error("\033[91m[AUTH-VERIFY] Starting token verification\033[0m")
    
    token = credentials.credentials
    
    if not token:
        logger.error("\033[91m[AUTH-VERIFY] ERROR: No token provided\033[0m")
        raise HTTPException(
            status_code=401,
            detail="Authorization token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.error(f"\033[91m[AUTH-VERIFY] Token received (length: {len(token)})\033[0m")
    logger.error(f"\033[91m[AUTH-VERIFY] Token preview: {token[:50]}...\033[0m")
    
    auth0_config = get_auth0_config()
    domain = auth0_config.get("AUTH0_DOMAIN")
    audience = auth0_config.get("AUTH0_AUDIENCE")
    
    logger.error(f"\033[91m[AUTH-VERIFY] Domain: {domain or 'NOT SET'}\033[0m")
    logger.error(f"\033[91m[AUTH-VERIFY] Audience: {audience or 'NOT SET'}\033[0m")
    
    if not domain:
        logger.error("\033[91m[AUTH-VERIFY] ERROR: AUTH0_DOMAIN not configured\033[0m")
        raise HTTPException(
            status_code=500,
            detail="AUTH0_DOMAIN not configured"
        )
    
    if not audience:
        logger.error("\033[91m[AUTH-VERIFY] ERROR: AUTH0_AUDIENCE not configured\033[0m")
        raise HTTPException(
            status_code=500,
            detail="AUTH0_AUDIENCE not configured"
        )
    
    try:
        # Get JWKS
        logger.error("\033[91m[AUTH-VERIFY] Fetching JWKS...\033[0m")
        jwks = get_jwks(domain)
        logger.error(f"\033[91m[AUTH-VERIFY] JWKS fetched, keys count: {len(jwks.get('keys', []))}\033[0m")
        
        # Get unverified header to find the key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        logger.error(f"\033[91m[AUTH-VERIFY] Token kid: {kid}\033[0m")
        
        if not kid:
            logger.error("\033[91m[AUTH-VERIFY] ERROR: Token missing 'kid' in header\033[0m")
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
            logger.error(f"\033[91m[AUTH-VERIFY] ERROR: Unable to find key with kid: {kid}\033[0m")
            raise HTTPException(
                status_code=401,
                detail=f"Unable to find key with kid: {kid}"
            )
        
        logger.error("\033[91m[AUTH-VERIFY] RSA key found, constructing public key...\033[0m")
        # Convert JWK to RSA key
        public_key = jwk.construct(rsa_key)
        
        logger.error("\033[91m[AUTH-VERIFY] Verifying and decoding token...\033[0m")
        # Verify and decode token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=f"https://{domain}/"
        )
        
        logger.error(f"\033[91m[AUTH-VERIFY] Token verified successfully!\033[0m")
        logger.error(f"\033[91m[AUTH-VERIFY] Payload keys: {list(payload.keys())}\033[0m")
        logger.error(f"\033[91m[AUTH-VERIFY] Payload sub: {payload.get('sub')}\033[0m")
        logger.error(f"\033[91m[AUTH-VERIFY] Payload email: {payload.get('email')}\033[0m")
        logger.error(f"\033[91m[AUTH-VERIFY] Payload name: {payload.get('name')}\033[0m")
        
        return payload
        
    except JWTError as e:
        logger.error(f"\033[91m[AUTH-VERIFY] JWTError: {str(e)}\033[0m")
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"\033[91m[AUTH-VERIFY] Exception during verification: {str(e)}\033[0m")
        logger.error(f"\033[91m[AUTH-VERIFY] Exception type: {type(e).__name__}\033[0m")
        import traceback
        logger.error(f"\033[91m[AUTH-VERIFY] Traceback: {traceback.format_exc()}\033[0m")
        raise HTTPException(
            status_code=401,
            detail=f"Token verification failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

