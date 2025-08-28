"""Unit test specific configuration and fixtures."""

from typing import Any
from unittest.mock import Mock

import httpx


def create_mock_response(json_data: dict[str, Any] | None = None) -> Mock:
    """Create a standard mock HTTP response.

    Args:
        json_data: Optional JSON data to return from response.json()

    Returns:
        Mock response object ready for use with httpx mocks
    """
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    if json_data is not None:
        mock_response.json.return_value = json_data
    return mock_response


def create_http_error_mock(error_message: str = "API error") -> httpx.HTTPError:
    """Create a standard HTTP error for testing.

    Args:
        error_message: Error message for the exception

    Returns:
        HTTPError instance ready to be used as side_effect
    """
    return httpx.HTTPError(error_message)


def create_rate_limit_error_mock(
    error_message: str = "Too Many Requests",
) -> httpx.HTTPStatusError:
    """Create a rate limit error (HTTP 429) for testing.

    Args:
        error_message: Error message for the exception

    Returns:
        HTTPStatusError instance with 429 status code
    """
    return create_http_status_error_mock(429, error_message)


def create_http_status_error_mock(
    status_code: int, error_message: str = "Server Error"
) -> httpx.HTTPStatusError:
    """Create an HTTP status error for testing.

    Args:
        status_code: HTTP status code (e.g., 500, 404)
        error_message: Error message for the exception

    Returns:
        HTTPStatusError instance with specified status code
    """
    error_response = Mock()
    error_response.status_code = status_code
    return httpx.HTTPStatusError(error_message, request=Mock(), response=error_response)