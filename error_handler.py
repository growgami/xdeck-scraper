import logging
import asyncio
from functools import wraps
import traceback
from typing import Callable, TypeVar, ParamSpec

# Type variables for generic function signatures
T = TypeVar('T')  # Return type
P = ParamSpec('P')  # Parameters

logger = logging.getLogger(__name__)

class RetryConfig:
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

def with_retry(retry_config: RetryConfig = RetryConfig()):
    """
    Decorator that adds retry logic with exponential backoff to async functions.
    
    Args:
        retry_config: Configuration for retry behavior
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception = None
            
            for attempt in range(retry_config.max_retries):
                try:
                    return await func(*args, **kwargs)
                    
                except Exception as e:
                    last_exception = e
                    delay = min(
                        retry_config.base_delay * (2 ** attempt),
                        retry_config.max_delay
                    )
                    
                    logger.warning(
                        f"Attempt {attempt + 1}/{retry_config.max_retries} failed for {func.__name__}. "
                        f"Error: {str(e)}. Retrying in {delay:.1f}s..."
                    )
                    
                    # Log detailed error info for debugging
                    logger.debug(f"Detailed error:\n{traceback.format_exc()}")
                    
                    if attempt < retry_config.max_retries - 1:
                        await asyncio.sleep(delay)
                    
            # If we get here, all retries failed
            logger.error(
                f"All {retry_config.max_retries} attempts failed for {func.__name__}. "
                f"Last error: {str(last_exception)}"
            )
            raise last_exception
            
        return wrapper
    return decorator

class APIError(Exception):
    """Base exception for API-related errors"""
    pass

class NetworkError(Exception):
    """Exception for network-related errors"""
    pass

class BrowserError(Exception):
    """Exception for browser automation errors"""
    pass

class DataProcessingError(Exception):
    """Exception for data processing errors"""
    pass

class TelegramError(Exception):
    """Exception for Telegram-related errors"""
    pass

def log_error(logger: logging.Logger, error: Exception, context: str = None):
    """
    Centralized error logging function
    
    Args:
        logger: Logger instance to use
        error: Exception that occurred
        context: Additional context about where/when the error occurred
    """
    error_type = type(error).__name__
    error_msg = str(error)
    stack_trace = traceback.format_exc()
    
    log_message = f"Error Type: {error_type}\n"
    if context:
        log_message += f"Context: {context}\n"
    log_message += f"Message: {error_msg}\n"
    log_message += f"Stack Trace:\n{stack_trace}"
    
    logger.error(log_message) 