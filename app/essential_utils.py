"""
Essential utilities module for the Insurance RAG API.
Consolidated from multiple utility files to provide only essential functionality.
"""

import asyncio
import functools
import logging
import time
import re
import html
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urlparse
import hashlib
import json
from datetime import datetime

logger = logging.getLogger(__name__)


# =============================================================================
# ASYNC RETRY DECORATOR
# =============================================================================

def async_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Async retry decorator for API calls with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each failed attempt
        exceptions: Tuple of exceptions to catch and retry on
    
    Returns:
        Decorated async function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts - 1:
                        # Last attempt failed, raise the exception
                        logger.error(
                            f"Function {func.__name__} failed after {max_attempts} attempts: {str(e)}"
                        )
                        raise e
                    
                    # Log retry attempt
                    logger.warning(
                        f"Function {func.__name__} failed on attempt {attempt + 1}/{max_attempts}: {str(e)}. "
                        f"Retrying in {current_delay:.2f}s..."
                    )
                    
                    # Wait before retry
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff_factor
            
            # This should never be reached, but just in case
            raise last_exception
        
        return wrapper
    return decorator


# =============================================================================
# INPUT SANITIZATION AND VALIDATION
# =============================================================================

class InputSanitizer:
    """Essential input sanitization utilities."""
    
    # Regex patterns for validation
    URL_PATTERN = re.compile(r'^https?://[^\s/$.?#].[^\s]*$', re.IGNORECASE)
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    
    @staticmethod
    def sanitize_string(
        text: str, 
        max_length: int = 1000,
        remove_html: bool = True,
        normalize_whitespace: bool = True
    ) -> str:
        """
        Sanitize string input to prevent XSS and injection attacks.
        
        Args:
            text: Input text to sanitize
            max_length: Maximum allowed length
            remove_html: Whether to remove/escape HTML
            normalize_whitespace: Whether to normalize whitespace
            
        Returns:
            Sanitized string
        """
        if not text or not isinstance(text, str):
            return ""
        
        # Initial cleanup
        sanitized = text.strip()
        
        # Remove null bytes and control characters
        sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', sanitized)
        
        # Handle HTML
        if remove_html:
            # Remove script tags and their content
            sanitized = re.sub(r'<script[^>]*>.*?</script>', '', sanitized, flags=re.IGNORECASE | re.DOTALL)
            # Remove other HTML tags
            sanitized = re.sub(r'<[^>]*>', '', sanitized)
            # Escape remaining HTML entities
            sanitized = html.escape(sanitized)
        
        # Remove dangerous patterns
        dangerous_patterns = [
            r'javascript:',
            r'vbscript:',
            r'on\w+\s*=',  # Event handlers
            r'union\s+select',  # SQL injection
            r'drop\s+table',
            r'insert\s+into',
            r'delete\s+from',
        ]
        
        for pattern in dangerous_patterns:
            sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
        
        # Normalize whitespace
        if normalize_whitespace:
            sanitized = re.sub(r'\s+', ' ', sanitized)
        
        # Truncate to max length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rstrip()
        
        return sanitized
    
    @staticmethod
    def sanitize_url(url: str) -> str:
        """
        Sanitize and validate URL.
        
        Args:
            url: URL to sanitize
            
        Returns:
            Sanitized URL
            
        Raises:
            ValueError: If URL is invalid or unsafe
        """
        if not url or not isinstance(url, str):
            raise ValueError("URL is required and must be a string")
        
        # Basic sanitization
        sanitized_url = url.strip()
        
        # Remove dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '`', '\x00', '\r', '\n']
        for char in dangerous_chars:
            if char in sanitized_url:
                raise ValueError(f"URL contains dangerous character: {char}")
        
        # Validate URL format
        if not InputSanitizer.URL_PATTERN.match(sanitized_url):
            raise ValueError("Invalid URL format")
        
        # Parse and validate components
        parsed = urlparse(sanitized_url)
        
        if parsed.scheme.lower() not in ['http', 'https']:
            raise ValueError("Only HTTP and HTTPS schemes are allowed")
        
        if not parsed.netloc:
            raise ValueError("URL must include a valid domain")
        
        # Check for internal/private addresses
        hostname = parsed.hostname
        if hostname:
            hostname_lower = hostname.lower()
            blocked_patterns = [
                'localhost', '127.0.0.1', '0.0.0.0',
                '192.168.', '10.', '172.16.', '172.17.', '172.18.',
                '172.19.', '172.20.', '172.21.', '172.22.', '172.23.',
                '172.24.', '172.25.', '172.26.', '172.27.', '172.28.',
                '172.29.', '172.30.', '172.31.'
            ]
            
            for pattern in blocked_patterns:
                if hostname_lower.startswith(pattern):
                    raise ValueError(f"URL points to internal/private address: {hostname}")
        
        return sanitized_url
    
    @staticmethod
    def sanitize_questions(questions: List[str]) -> List[str]:
        """
        Sanitize a list of questions.
        
        Args:
            questions: List of questions to sanitize
            
        Returns:
            List of sanitized questions
        """
        if not questions or not isinstance(questions, list):
            return []
        
        sanitized_questions = []
        
        for question in questions:
            if not isinstance(question, str):
                continue
            
            # Sanitize the question
            sanitized = InputSanitizer.sanitize_string(
                question,
                max_length=1000,
                remove_html=True,
                normalize_whitespace=True
            )
            
            # Only add non-empty questions with minimum length
            if sanitized and len(sanitized.strip()) >= 3:
                # Ensure question ends with appropriate punctuation
                sanitized = sanitized.rstrip()
                if sanitized and not sanitized[-1] in '.?!':
                    sanitized += '?'
                
                sanitized_questions.append(sanitized)
        
        return sanitized_questions


def validate_bearer_token(authorization_header: Optional[str]) -> bool:
    """
    Validate Bearer token against configured API key.
    
    Args:
        authorization_header: Authorization header value
        
    Returns:
        True if token is valid, False otherwise
    """
    from app.config import Config
    
    if not authorization_header or not isinstance(authorization_header, str):
        return False
    
    # Check Bearer token format
    if not authorization_header.startswith('Bearer '):
        return False
    
    # Extract token
    token = authorization_header[7:].strip()  # Remove 'Bearer ' prefix
    
    # Validate against configured API key
    return token == Config.API_KEY and bool(Config.API_KEY)


# =============================================================================
# PERFORMANCE LOGGING UTILITIES
# =============================================================================

class PerformanceLogger:
    """Essential performance logging utilities."""
    
    def __init__(self):
        self.logger = logging.getLogger("performance")
        self.operation_times = {}
    
    def start_operation(self, operation_id: str, operation_name: str) -> None:
        """
        Start tracking an operation.
        
        Args:
            operation_id: Unique identifier for the operation
            operation_name: Name of the operation being tracked
        """
        self.operation_times[operation_id] = {
            'name': operation_name,
            'start_time': time.time(),
            'start_timestamp': datetime.now().isoformat()
        }
    
    def end_operation(
        self, 
        operation_id: str, 
        success: bool = True, 
        error_message: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        End tracking an operation and log performance metrics.
        
        Args:
            operation_id: Unique identifier for the operation
            success: Whether the operation was successful
            error_message: Error message if operation failed
            additional_data: Additional data to include in log
            
        Returns:
            Duration of the operation in seconds
        """
        if operation_id not in self.operation_times:
            self.logger.warning(f"Operation {operation_id} not found in tracking")
            return 0.0
        
        operation_info = self.operation_times.pop(operation_id)
        end_time = time.time()
        duration = end_time - operation_info['start_time']
        
        # Prepare log data
        log_data = {
            'operation_id': operation_id,
            'operation_name': operation_info['name'],
            'duration_seconds': round(duration, 3),
            'success': success,
            'start_time': operation_info['start_timestamp'],
            'end_time': datetime.now().isoformat()
        }
        
        if error_message:
            log_data['error_message'] = error_message
        
        if additional_data:
            log_data.update(additional_data)
        
        # Log the performance data
        if success:
            self.logger.info(f"Operation completed: {json.dumps(log_data)}")
        else:
            self.logger.error(f"Operation failed: {json.dumps(log_data)}")
        
        # Log warning for slow operations
        if duration > 5.0:
            self.logger.warning(
                f"Slow operation detected: {operation_info['name']} took {duration:.2f}s"
            )
        
        return duration
    
    def log_api_request(
        self,
        request_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        processing_time: float,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> None:
        """
        Log API request performance metrics.
        
        Args:
            request_id: Unique request identifier
            endpoint: API endpoint path
            method: HTTP method
            status_code: HTTP status code
            processing_time: Request processing time in seconds
            client_ip: Client IP address
            user_agent: Client user agent
        """
        log_data = {
            'request_id': request_id,
            'endpoint': endpoint,
            'method': method,
            'status_code': status_code,
            'processing_time_seconds': round(processing_time, 3),
            'timestamp': datetime.now().isoformat()
        }
        
        if client_ip:
            log_data['client_ip'] = client_ip
        
        if user_agent:
            log_data['user_agent'] = user_agent
        
        # Determine log level based on status code and processing time
        if status_code >= 500:
            self.logger.error(f"API request error: {json.dumps(log_data)}")
        elif status_code >= 400:
            self.logger.warning(f"API request client error: {json.dumps(log_data)}")
        elif processing_time > 10.0:
            self.logger.warning(f"Slow API request: {json.dumps(log_data)}")
        else:
            self.logger.info(f"API request: {json.dumps(log_data)}")


def track_performance(operation_name: str):
    """
    Decorator for tracking function performance.
    
    Args:
        operation_name: Name of the operation being tracked
    
    Returns:
        Decorated function with performance tracking
    """
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                operation_id = f"{operation_name}_{int(time.time() * 1000000)}"
                performance_logger.start_operation(operation_id, operation_name)
                
                try:
                    result = await func(*args, **kwargs)
                    performance_logger.end_operation(operation_id, success=True)
                    return result
                except Exception as e:
                    performance_logger.end_operation(
                        operation_id, 
                        success=False, 
                        error_message=str(e)
                    )
                    raise
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                operation_id = f"{operation_name}_{int(time.time() * 1000000)}"
                performance_logger.start_operation(operation_id, operation_name)
                
                try:
                    result = func(*args, **kwargs)
                    performance_logger.end_operation(operation_id, success=True)
                    return result
                except Exception as e:
                    performance_logger.end_operation(
                        operation_id, 
                        success=False, 
                        error_message=str(e)
                    )
                    raise
            
            return sync_wrapper
    
    return decorator


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def generate_hash(content: Union[str, bytes]) -> str:
    """
    Generate SHA-256 hash for content.
    
    Args:
        content: Content to hash (string or bytes)
        
    Returns:
        First 16 characters of SHA-256 hash
    """
    if isinstance(content, str):
        content = content.encode('utf-8')
    
    return hashlib.sha256(content).hexdigest()[:16]


def generate_request_id() -> str:
    """
    Generate unique request ID.
    
    Returns:
        Unique request identifier
    """
    timestamp = int(time.time() * 1000000)
    return f"req_{timestamp}"


def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """
    Safely parse JSON string with fallback.
    
    Args:
        json_str: JSON string to parse
        default: Default value if parsing fails
        
    Returns:
        Parsed JSON data or default value
    """
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to specified length with suffix.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
        
    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


# =============================================================================
# GLOBAL INSTANCES
# =============================================================================

# Global performance logger instance
performance_logger = PerformanceLogger()


# =============================================================================
# CONVENIENCE FUNCTIONS FOR MAIN.PY
# =============================================================================

def sanitize_input(text: str) -> str:
    """
    Convenience function for sanitizing input text.
    
    Args:
        text: Input text to sanitize
        
    Returns:
        Sanitized text
    """
    return InputSanitizer.sanitize_string(text)


async def log_performance_metrics(
    request_id: str,
    endpoint: str,
    processing_time: float,
    questions_count: int = 0,
    success: bool = True
) -> None:
    """
    Convenience function for logging performance metrics.
    
    Args:
        request_id: Unique request identifier
        endpoint: API endpoint
        processing_time: Processing time in seconds
        questions_count: Number of questions processed
        success: Whether the request was successful
    """
    additional_data = {
        'questions_count': questions_count,
        'avg_time_per_question': processing_time / max(questions_count, 1)
    }
    
    performance_logger.log_api_request(
        request_id=request_id,
        endpoint=endpoint,
        method="POST",
        status_code=200 if success else 500,
        processing_time=processing_time
    )