"""
Security middleware for adding security headers to responses.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import os
import logging

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all HTTP responses.
    
    Headers added:
    - X-Content-Type-Options: Prevents MIME sniffing
    - X-Frame-Options: Prevents clickjacking
    - X-XSS-Protection: XSS protection for older browsers
    - Strict-Transport-Security: Enforces HTTPS (production only)
    - Content-Security-Policy: Mitigates XSS attacks
    """
    
    def __init__(self, app, environment: str = "local"):
        super().__init__(app)
        self.environment = environment
        self.is_production = environment in ["prod", "production"]
    
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        
        # Basic security headers (all environments)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # HSTS - only in production with HTTPS
        if self.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy
        # Adjust this based on your needs
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Adjust as needed
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions Policy (formerly Feature Policy)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        return response


def get_security_headers_middleware(environment: str = None):
    """
    Factory function to create SecurityHeadersMiddleware with environment config.
    
    Args:
        environment: Environment name (local/dev/qa/prod). If None, reads from env var.
    
    Returns:
        SecurityHeadersMiddleware instance
    """
    if environment is None:
        environment = os.getenv("ENVIRONMENT", "local")
    
    logger.info(f"Initializing SecurityHeadersMiddleware for environment: {environment}")
    
    return lambda app: SecurityHeadersMiddleware(app, environment=environment)
