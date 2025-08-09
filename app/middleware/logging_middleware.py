"""
Enhanced Logging Middleware with comprehensive request/response tracking.
"""

import time
import logging
import uuid
import json
from typing import Callable, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.logging_service import logging_service


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Enhanced middleware for comprehensive request/response logging.
    
    Features:
    - Automatic request ID generation
    - Comprehensive request/response logging with LoggingService
    - Performance metrics tracking
    - Error logging with security masking
    - System health monitoring
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.logger = logging.getLogger("request")
        self.performance_logger = logging.getLogger("performance")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with comprehensive logging and performance tracking."""
        
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        
        # Add request ID to request state for access in endpoints
        request.state.request_id = request_id
        
        # Get client information
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        
        # Capture request data for logging
        request_body = await self._get_request_body(request)
        request_data = {
            'endpoint': str(request.url.path),
            'method': request.method,
            'headers': dict(request.headers),
            'body': request_body,
            'client_ip': client_ip,
            'user_agent': user_agent,
            'query_params': dict(request.query_params)
        }
        
        # Log request start
        start_time = time.time()
        
        self.logger.info(
            f"Request started - {request.method} {request.url.path} - ID: {request_id}"
        )
        
        # Log request to LoggingService
        try:
            await logging_service.log_request(request_id, request_data)
        except Exception as e:
            self.logger.warning(f"Failed to log request to LoggingService: {e}")
        
        # Process request
        response = None
        error_occurred = False
        error_details = None
        llm_service_used = None
        api_key_used = None
        
        try:
            response = await call_next(request)
            
            # Extract LLM service info from request state if available
            llm_service_used = getattr(request.state, 'llm_service_used', None)
            api_key_used = getattr(request.state, 'api_key_used', None)
            
        except Exception as e:
            error_occurred = True
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
            
            self.logger.error(
                f"Request error - {request.method} {request.url.path}: {e} - ID: {request_id}"
            )
            
            # Log error to system events
            try:
                await logging_service.log_system_event('request_error', {
                    'request_id': request_id,
                    'endpoint': str(request.url.path),
                    'method': request.method,
                    'error': error_details,
                    'client_ip': client_ip
                })
            except Exception as log_error:
                self.logger.warning(f"Failed to log error event: {log_error}")
            
            # Re-raise the exception
            raise
        
        finally:
            # Calculate processing time
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Log request completion
            if not error_occurred and response:
                self.logger.info(
                    f"Request completed - {request.method} {request.url.path} - "
                    f"Status: {response.status_code}, Time: {processing_time:.3f}s - ID: {request_id}"
                )
                
                # Add request ID to response headers for debugging
                response.headers["X-Request-ID"] = request_id
                
                # Capture response data for logging
                response_body = await self._get_response_body(response)
                response_data = {
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'body': response_body,
                    'processing_time': processing_time,
                    'llm_service_used': llm_service_used,
                    'api_key_used': api_key_used
                }
                
                # Log response to LoggingService
                try:
                    await logging_service.log_response(request_id, response_data)
                except Exception as e:
                    self.logger.warning(f"Failed to log response to LoggingService: {e}")
            
            # Log long-running requests for monitoring (no limits enforced)
            if processing_time > 60:  # Log requests over 1 minute for monitoring
                self.performance_logger.info(
                    f"Long-running request - {request.method} {request.url.path} - "
                    f"Time: {processing_time:.3f}s - ID: {request_id}"
                )
                
                # Log long request as system event for monitoring
                try:
                    await logging_service.log_system_event('long_request', {
                        'request_id': request_id,
                        'endpoint': str(request.url.path),
                        'method': request.method,
                        'processing_time': processing_time,
                        'client_ip': client_ip
                    })
                except Exception as e:
                    self.logger.warning(f"Failed to log long request event: {e}")
        
        return response
    
    async def _get_request_body(self, request: Request) -> Dict[str, Any]:
        """
        Safely extract request body for logging.
        
        Args:
            request: FastAPI request object
            
        Returns:
            Request body as dictionary or empty dict if not available
        """
        try:
            # Only capture body for POST requests to avoid issues
            if request.method in ['POST', 'PUT', 'PATCH']:
                content_type = request.headers.get('content-type', '').lower()
                
                if 'application/json' in content_type:
                    # For JSON requests, we need to read the body carefully
                    # Note: This is tricky because the body can only be read once
                    # We'll try to get it from the request state if available
                    if hasattr(request.state, 'body'):
                        return request.state.body
                    else:
                        # For now, return empty dict to avoid breaking the request
                        return {}
                else:
                    return {'content_type': content_type, 'body_captured': False}
            
            return {}
            
        except Exception as e:
            self.logger.debug(f"Failed to capture request body: {e}")
            return {'error': 'Failed to capture body'}
    
    async def _get_response_body(self, response: Response) -> Dict[str, Any]:
        """
        Safely extract response body for logging.
        
        Args:
            response: FastAPI response object
            
        Returns:
            Response body information
        """
        try:
            content_type = response.headers.get('content-type', '').lower()
            
            # Only log basic response info to avoid memory issues
            return {
                'content_type': content_type,
                'content_length': response.headers.get('content-length'),
                'body_captured': False  # We don't capture actual body to avoid memory issues
            }
            
        except Exception as e:
            self.logger.debug(f"Failed to capture response body info: {e}")
            return {'error': 'Failed to capture response info'}
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address with proxy support."""
        # Check for forwarded headers (common in production deployments)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        if request.client:
            return request.client.host
        
        return "unknown"
    
