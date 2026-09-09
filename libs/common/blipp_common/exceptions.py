from typing import Optional, Dict, Any

try:
    from fastapi import HTTPException
except ImportError:
    class HTTPException(Exception):  # type: ignore
        def __init__(
            self,
            status_code: int = 500,
            detail: Any = None,
            headers: Optional[Dict[str, str]] = None,
        ):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
            self.headers = headers


class AppException(HTTPException):
    """
    Standard application exception carrying explicit machine-readable code
    and human-readable message to be formatted in the API error envelope.
    """
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.message = message


# Standardized error codes
CODE_INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
CODE_UNAUTHORIZED = "UNAUTHORIZED"
CODE_TOKEN_EXPIRED = "TOKEN_EXPIRED"
CODE_INVALID_TOKEN = "INVALID_TOKEN"
CODE_USER_ALREADY_EXISTS = "USER_ALREADY_EXISTS"
CODE_SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
CODE_REGISTRATION_FAILED = "REGISTRATION_FAILED"
CODE_VALIDATION_ERROR = "VALIDATION_ERROR"
CODE_INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
CODE_FORBIDDEN = "FORBIDDEN"
CODE_NOT_FOUND = "NOT_FOUND"

__all__ = [
    "AppException",
    "CODE_INVALID_CREDENTIALS",
    "CODE_UNAUTHORIZED",
    "CODE_TOKEN_EXPIRED",
    "CODE_INVALID_TOKEN",
    "CODE_USER_ALREADY_EXISTS",
    "CODE_SERVICE_UNAVAILABLE",
    "CODE_REGISTRATION_FAILED",
    "CODE_VALIDATION_ERROR",
    "CODE_INTERNAL_SERVER_ERROR",
    "CODE_FORBIDDEN",
    "CODE_NOT_FOUND",
]
