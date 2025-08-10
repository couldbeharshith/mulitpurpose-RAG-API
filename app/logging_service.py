"""
Console-only logging service for the Insurance RAG API.
Provides structured JSON logging to console for Hugging Face Spaces compatibility.
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LogResponse:
    """Response structure for log queries."""
    logs: List[Dict[str, Any]]
    total_count: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class LoggingService:
    """Lightweight logging service with console-only JSON structured logs."""
    
    def __init__(self, log_directory: str = "./logs"):
        # Disable file logging entirely for Hugging Face Spaces compatibility
        self.file_logging_enabled = False
        self._setup_console_logging()
        
    def _setup_console_logging(self):
        """Configure console-only logging."""
        # Note: logging.basicConfig() is already called in main.py
        # This method is kept for compatibility but doesn't reconfigure logging
        pass
    
    async def log_request(self, request_id: str, request_data: Dict[str, Any]):
        """Log incoming request data."""
        log_entry = {
            "type": "request",
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat(),
            "method": request_data.get("method", ""),
            "endpoint": request_data.get("endpoint", ""),
            "client_ip": request_data.get("client_ip", ""),
            "headers": self._sanitize_headers(request_data.get("headers", {})),
            "body_size": len(str(request_data.get("body", "")))
        }
        
        await self._write_log(log_entry)
    
    async def log_response(self, request_id: str, response_data: Dict[str, Any]):
        """Log outgoing response data."""
        log_entry = {
            "type": "response", 
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat(),
            "status_code": response_data.get("status_code", 0),
            "processing_time": response_data.get("processing_time", 0),
            "llm_service": response_data.get("llm_service_used", ""),
            "api_key_used": response_data.get("api_key_used", ""),
            "response_size": len(str(response_data.get("body", "")))
        }
        
        await self._write_log(log_entry)
    
    async def log_system_event(self, event_type: str, event_data: Dict[str, Any]):
        """Log system events like errors and slow requests."""
        log_entry = {
            "type": "system_event",
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            **event_data
        }
        
        await self._write_log(log_entry)
    
    async def _write_log(self, log_entry: Dict[str, Any]):
        """Output log entry to console instead of file."""
        try:
            # Output to console using logger.info() as specified in requirements
            logger.info(json.dumps(log_entry))
        except Exception as e:
            logger.error(f"Failed to output log to console: {e}")
    
    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Return headers without masking as requested."""
        return dict(headers)
    
    async def get_logs(self, limit: int = 100, offset: int = 0, 
                      date_filter: Optional[str] = None, log_type: str = 'all',
                      start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
                      request_id: Optional[str] = None) -> 'LogResponse':
        """Return empty results since file-based log retrieval is disabled."""
        # Return empty results as file-based functionality is disabled
        return LogResponse(
            logs=[], 
            total_count=0, 
            page=1, 
            per_page=limit, 
            has_next=False, 
            has_prev=False
        )
    
    def _read_log_file(self, log_file) -> List[Dict[str, Any]]:
        """Return empty list since file-based log reading is disabled."""
        # Return empty list as file-based functionality is disabled
        return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get logging service status - console-only mode."""
        return {
            "logging_mode": "console_only",
            "file_logging_enabled": False,
            "total_files": 0,
            "total_size_mb": 0,
            "latest_file": None
        }
    
    def _apply_filters(self, logs: List[Dict[str, Any]], log_type: str, 
                      start_time: Optional[datetime], end_time: Optional[datetime],
                      request_id: Optional[str]) -> List[Dict[str, Any]]:
        """Apply filters to log entries."""
        filtered_logs = logs
        
        # Filter by log type
        if log_type != 'all':
            if log_type == 'requests':
                filtered_logs = [log for log in filtered_logs if log.get('type') == 'request']
            elif log_type == 'responses':
                filtered_logs = [log for log in filtered_logs if log.get('type') == 'response']
            elif log_type == 'system':
                filtered_logs = [log for log in filtered_logs if log.get('type') == 'system_event']
        
        # Filter by time range
        if start_time or end_time:
            time_filtered = []
            for log in filtered_logs:
                try:
                    log_time = datetime.fromisoformat(log.get('timestamp', ''))
                    if start_time and log_time < start_time:
                        continue
                    if end_time and log_time > end_time:
                        continue
                    time_filtered.append(log)
                except (ValueError, TypeError):
                    continue
            filtered_logs = time_filtered
        
        # Filter by request ID
        if request_id:
            filtered_logs = [log for log in filtered_logs if log.get('request_id') == request_id]
        
        return filtered_logs
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive logging system health information - console-only mode."""
        status = self.get_status()
        
        # Health info for console-only logging
        health_info = {
            **status,
            "status": "healthy",  # Always healthy in console-only mode
            "disk_usage_ok": True,  # No disk usage in console-only mode
            "write_test": True  # Console writing always available
        }
        
        return health_info


# Global logging service instance
logging_service = LoggingService()