"""Retry utilities for handling transient errors."""

import time
from collections.abc import Callable
from typing import Any


def retry(
    timeout: float = 15.0,
    interval: float = 0.5,
    log_interval: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
    """Retry decorator that catches specified exceptions and retries until timeout.

    Args:
        timeout: Maximum time to retry in seconds
        interval: Time between retries in seconds
        log_interval: Time between log messages in seconds
        exceptions: Tuple of exception types to catch and retry on

    Returns:
        Decorator function
    """

    def decorator(func: Callable[[], Any]) -> Callable[[], Any]:
        def wrapper() -> Any:
            start_time = time.time()
            last_log = 0.0
            last_error = None
            attempt = 0

            while time.time() - start_time < timeout:
                attempt += 1
                try:
                    result = func()
                    if attempt > 1:
                        print(f"Retry succeeded on attempt {attempt}")
                    return result  # Success, return the result
                except exceptions as e:
                    last_error = e

                elapsed = time.time() - start_time
                if elapsed - last_log >= log_interval:
                    print(f"Retrying... (attempt {attempt}, {elapsed:.1f}s elapsed)")
                    last_log = elapsed

                time.sleep(interval)

            # Timeout reached, re-raise the last error
            if last_error:
                raise last_error
            else:
                raise TimeoutError("Retry timeout reached with no errors captured")

        return wrapper

    return decorator
