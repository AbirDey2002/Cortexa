"""
Rate limiting middleware using slowapi.
Protects API endpoints from abuse and DDoS attacks.
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import os
import logging
import jwt

logger = logging.getLogger(__name__)


def get_rate_limit_key(request):
    """
    Get the key for rate limiting.
    
    1. Try to get user ID from request state (set by dependencies).
    2. If not set, try to extract sub/email from JWT token without verification.
    3. Fall back to IP address.
    """
    # 1. Try request state (set by get_current_user dependency)
    if hasattr(request.state, "user_id"):
        return f"user:{request.state.user_id}"
    
    # 2. Try to extract from Authorization header proactively
    # This is for the middleware phase where dependencies haven't run yet.
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header[7:]
            # Safe decode without verification just to get identifier
            # Real verification happens in the endpoint dependencies
            payload = jwt.decode(token, options={"verify_signature": False})
            uid = payload.get("sub") or payload.get("email")
            if uid:
                return f"user:{uid}"
        except Exception:
            pass
    
    # 3. Fall back to IP address
    return get_remote_address(request)


def get_rate_limiter():
    """
    Create and configure the rate limiter.
    
    Configuration:
    - RATE_LIMIT_ENABLED: Enable/disable rate limiting (default: true)
    - RATE_LIMIT_PER_MINUTE: Requests per minute (default: 60)
    
    Returns:
        Limiter instance configured with environment settings
    """
    enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    
    if not enabled:
        logger.warning("Rate limiting is DISABLED. Enable in production!")
        # Return a limiter but we won't apply it
        return None
    
    # Get rate limit from environment
    rate_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    
    # Create limiter with custom key function
    limiter = Limiter(
        key_func=get_rate_limit_key,
        default_limits=[f"{rate_per_minute}/minute"],
        storage_uri="memory://",  # In-memory storage. Use Redis for production: "redis://localhost:6379"
        headers_enabled=True,  # Add rate limit headers to responses
    )
    
    logger.info(f"Rate limiting enabled: {rate_per_minute} requests per minute")
    
    return limiter


# Create global limiter instance
limiter = get_rate_limiter()


def setup_rate_limiting(app):
    """
    Setup rate limiting for the FastAPI application.
    
    Args:
        app: FastAPI application instance
    """
    if limiter is None:
        logger.warning("Skipping rate limiting setup (disabled)")
        return
    
    # Add exception handler for rate limit exceeded
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Add middleware
    app.add_middleware(SlowAPIMiddleware)
    
    logger.info("Rate limiting middleware configured")


# Decorator for custom rate limits on specific endpoints
def custom_rate_limit(limit: str):
    """
    Decorator to apply custom rate limit to specific endpoints.
    
    Usage:
        @app.get("/expensive-endpoint")
        @custom_rate_limit("10/minute")
        async def expensive_operation():
            ...
    
    Args:
        limit: Rate limit string (e.g., "10/minute", "100/hour")
    """
    if limiter is None:
        # If rate limiting is disabled, return a no-op decorator
        def decorator(func):
            return func
        return decorator
    
    return limiter.limit(limit)
