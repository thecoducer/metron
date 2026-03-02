"""
Centralized error handling for the Metron application.

This module provides:
- Custom exception classes
- Error handling decorators
- Retry logic with exponential backoff
- Consistent error logging and reporting
"""

import functools
import time
from enum import Enum
from typing import Any, Callable, Optional, Tuple, Type

from requests.exceptions import (ConnectionError, HTTPError, RequestException,
                                 Timeout)

from .logging_config import logger


class ErrorCategory(Enum):
    """Categories of errors for consistent handling."""
    NETWORK = "network"
    API = "api"
    AUTHENTICATION = "authentication"
    DATA = "data"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class PortfolioTrackerError(Exception):
    """Base exception for all Metron errors."""
    
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.UNKNOWN, 
                 original_error: Optional[Exception] = None):
        self.message = message
        self.category = category
        self.original_error = original_error
        super().__init__(self.message)


class NetworkError(PortfolioTrackerError):
    """Network-related errors (timeouts, connection failures)."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.NETWORK, original_error)


class APIError(PortfolioTrackerError):
    """API-related errors (HTTP errors, invalid responses)."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, 
                 original_error: Optional[Exception] = None):
        self.status_code = status_code
        super().__init__(message, ErrorCategory.API, original_error)


class AuthenticationError(PortfolioTrackerError):
    """Authentication and authorization errors."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.AUTHENTICATION, original_error)


class DataError(PortfolioTrackerError):
    """Data parsing and validation errors."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.DATA, original_error)


class ConfigurationError(PortfolioTrackerError):
    """Configuration and setup errors."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.CONFIGURATION, original_error)


class ErrorHandler:
    """Central error handling utilities."""
    
    @staticmethod
    def wrap_external_api_error(error: Exception, service_name: str) -> PortfolioTrackerError:
        """Convert external API exceptions to our custom exceptions.
        
        Args:
            error: The original exception
            service_name: Name of the service (for logging)
        
        Returns:
            Custom PortfolioTrackerError subclass
        """
        if isinstance(error, Timeout):
            return NetworkError(
                f"{service_name} request timeout - server slow to respond",
                original_error=error
            )
        elif isinstance(error, ConnectionError):
            return NetworkError(
                f"Cannot connect to {service_name} - network unavailable",
                original_error=error
            )
        elif isinstance(error, HTTPError):
            status_code = error.response.status_code if hasattr(error, 'response') else None
            return APIError(
                f"{service_name} returned HTTP error: {error}",
                status_code=status_code,
                original_error=error
            )
        elif isinstance(error, RequestException):
            return NetworkError(
                f"{service_name} request failed: {error}",
                original_error=error
            )
        else:
            return PortfolioTrackerError(
                f"Unexpected error from {service_name}: {error}",
                original_error=error
            )
    
    @staticmethod
    def log_error(error: Exception, context: str = "") -> None:
        """Log error with appropriate level and context.
        
        Args:
            error: The exception to log
            context: Additional context about where error occurred
        """
        prefix = f"[{context}] " if context else ""
        
        if isinstance(error, NetworkError):
            logger.warning("%s%s", prefix, error.message)
        elif isinstance(error, APIError):
            if error.status_code and error.status_code >= 500:
                logger.error("%s%s (HTTP %d)", prefix, error.message, error.status_code)
            else:
                logger.warning("%s%s", prefix, error.message)
        elif isinstance(error, (AuthenticationError, ConfigurationError)):
            logger.error("%s%s", prefix, error.message)
        else:
            logger.exception("%s%s", prefix, str(error))


def retry_on_transient_error(
    max_retries: int = 2,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (NetworkError, APIError, OSError)
):
    """Decorator to retry function on transient errors.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to retry on
    
    Example:
        @retry_on_transient_error(max_retries=3, delay=1.0)
        def fetch_data():
            # ... API call ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    
                    # Don't retry on permanent errors (4xx HTTP errors)
                    if isinstance(e, APIError) and e.status_code and 400 <= e.status_code < 500:
                        logger.warning("%s failed with permanent error (HTTP %d)", func.__name__, e.status_code)
                        raise
                    
                    if attempt < max_retries:
                        logger.warning(
                            "%s failed (attempt %d/%d): %s - retrying in %ss...",
                            func.__name__, attempt + 1, max_retries + 1, e, current_delay
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error("%s failed after %d attempts", func.__name__, max_retries + 1)
                        raise
            
            # Should not reach here, but just in case
            if last_error:
                raise last_error
            
        return wrapper
    return decorator


def handle_errors(
    default_return: Any = None,
    log_context: str = "",
    preserve_cache: bool = False,
    cache_attr: Optional[str] = None
):
    """Decorator for consistent error handling across API methods.
    
    Args:
        default_return: Value to return on error (None, [], {}, etc.)
        log_context: Context string for logging
        preserve_cache: If True, return cached value on error
        cache_attr: Name of instance attribute containing cached value
    
    Example:
        @handle_errors(default_return=[], log_context="fetch_holdings")
        def fetch_holdings(self):
            # ... API call ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Wrap and log error
                if not isinstance(e, PortfolioTrackerError):
                    wrapped_error = ErrorHandler.wrap_external_api_error(e, func.__name__)
                else:
                    wrapped_error = e
                
                ErrorHandler.log_error(wrapped_error, context=log_context or func.__name__)
                
                # Try to preserve cache if requested
                if preserve_cache and cache_attr and args:
                    instance = args[0]  # Assume first arg is self
                    cached_value = getattr(instance, cache_attr, None)
                    if cached_value is not None:
                        logger.info("Returning cached value for %s", func.__name__)
                        return cached_value
                
                return default_return
        
        return wrapper
    return decorator


def safe_api_call(func: Callable, *args, **kwargs) -> Tuple[Optional[Any], Optional[Exception]]:
    """Execute API call safely and return result or error.
    
    Args:
        func: Function to call
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
    
    Returns:
        Tuple of (result, error) - one will be None
    
    Example:
        result, error = safe_api_call(api.fetch_data, param1, param2)
        if error:
            handle_error(error)
        else:
            process_result(result)
    """
    try:
        result = func(*args, **kwargs)
        return result, None
    except Exception as e:
        return None, e


class ErrorAggregator:
    """Aggregate multiple errors from parallel operations."""
    
    def __init__(self):
        self.errors = []
    
    def add(self, error: Exception, context: str = ""):
        """Add an error to the aggregator.
        
        Args:
            error: The exception
            context: Context about where it occurred
        """
        self.errors.append({
            'error': error,
            'context': context,
            'message': str(error)
        })
    
    def has_errors(self) -> bool:
        """Check if any errors were collected."""
        return len(self.errors) > 0
    
    def get_summary(self) -> str:
        """Get a summary of all errors.
        
        Returns:
            Human-readable error summary
        """
        if not self.errors:
            return "No errors"
        
        if len(self.errors) == 1:
            error_info = self.errors[0]
            return f"{error_info['context']}: {error_info['message']}" if error_info['context'] else error_info['message']
        
        # Multiple errors
        summary_lines = [f"Multiple errors occurred ({len(self.errors)}):"]
        for error_info in self.errors:
            context = error_info['context']
            msg = error_info['message']
            summary_lines.append(f"  - {context}: {msg}" if context else f"  - {msg}")
        
        return "\n".join(summary_lines)
    
    def log_all(self):
        """Log all collected errors."""
        for error_info in self.errors:
            ErrorHandler.log_error(error_info['error'], context=error_info['context'])
