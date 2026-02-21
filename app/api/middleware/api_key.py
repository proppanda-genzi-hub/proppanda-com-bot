from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import os
import logging

logger = logging.getLogger(__name__)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate API key from X-API-KEY header.
    Only applies to /api/v1/* endpoints.
    """
    
    def __init__(self, app, api_key: str = None):
        super().__init__(app)
        self.api_key = api_key or os.getenv("API_KEY")
        
        if not self.api_key:
            logger.warning("⚠️ API_KEY not set in environment! All requests will be rejected.")
    
    async def dispatch(self, request: Request, call_next):
        # Skip API key validation for health check, docs, and OPTIONS (CORS preflight)
        if request.url.path in ["/", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # Skip API key validation for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Only validate API key for /api/v1/* endpoints
        if request.url.path.startswith("/api/v1"):
            api_key_header = request.headers.get("X-API-KEY")
            
            if not api_key_header:
                logger.warning(f"❌ Missing API key for {request.url.path}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "error": "Unauthorized",
                        "detail": "Missing API KEY "
                    }
                )
            
            if api_key_header != self.api_key:
                logger.warning(f"❌ Invalid API key attempted for {request.url.path}")
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "error": "Forbidden",
                        "detail": "Invalid API key"
                    }
                )
            
            logger.debug(f"✅ Valid API key for {request.url.path}")
        
        response = await call_next(request)
        return response
