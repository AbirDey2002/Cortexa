from dotenv import load_dotenv
load_dotenv()  # Load environment variables before importing config classes

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from models.base import Base
from db.session import engine
from api.v1.api_router import api_router
import logging
from typing import Dict
from core.logging_config import setup_logging
import os

# Initialize database
Base.metadata.create_all(bind=engine)

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="cortexa backend")

# Import security configurations
from core.config import CORSConfigs, SecurityConfigs
from core.security_middleware import SecurityHeadersMiddleware
from core.rate_limit import setup_rate_limiting

# CORS - Must be added early before routes
# Use environment-configured allowed origins instead of wildcard
allowed_origins = CORSConfigs.get_allowed_origins()
logger.info(f"CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware, environment=SecurityConfigs.ENVIRONMENT)

# Setup rate limiting
setup_rate_limiting(app)

# Global exception handler to prevent information disclosure
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler to prevent leaking internal server details.
    Logs the full error server-side but returns a generic message to the client.
    """
    # Log the full error with traceback
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    
    # Return generic error to client (avoid information disclosure)
    if SecurityConfigs.IS_PRODUCTION:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred. Please try again later."}
        )
    else:
        # In development, show more details
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": str(exc)}
        )

# Include API router
app.include_router(api_router)

# Mount static files directory for serving uploaded files
# Security Note: Static files are served without BOLA checks.
# Production recommendation: Serve sensitive files via a protected API route.
uploads_dir = "uploads"
if not os.path.exists(uploads_dir):
    os.makedirs(uploads_dir)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

if __name__ == "__main__":
    import uvicorn
    from core.config import HostingConfigs

    # Avoid infinite reload loops by excluding changing files like logs
    reload_enabled = os.getenv("RELOAD", "false").lower() == "true"
    reload_excludes = [
        "logs/*",
        "**/*.log",
        "**/__pycache__/**",
    ]

    uvicorn.run(
        "main:app",
        host=HostingConfigs.HOST,
        port=HostingConfigs.PORT,
        reload=reload_enabled,
        reload_excludes=reload_excludes,
    )