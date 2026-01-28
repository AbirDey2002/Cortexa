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

logger = logging.getLogger(__name__)


def get_rate_limit_key(request):
    """
    Get the key for rate limiting.
    
    For authenticated requests, use user ID from token.
    For unauthenticated requests, use IP address.
    """
    # Try to get user from token if available
    if hasattr(request.state, "user_id"):
        return f"user:{request.state.user_id}"
    
    # Fall back to IP address
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
