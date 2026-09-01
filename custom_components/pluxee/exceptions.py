"""Exceptions for the Pluxee API."""


class PluxeeAPIError(Exception):
    """Raised when the Pluxee API returns an unexpected error."""


class AuthenticationError(PluxeeAPIError):
    """Raised when authentication fails (invalid credentials)."""
