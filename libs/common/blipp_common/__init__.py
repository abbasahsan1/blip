"""
Blipp Common - Shared platform infrastructure library.
"""

from .config import BaseCommonSettings, settings
from .database import (
    Base,
    get_async_engine,
    get_session_factory,
    get_db_session,
    get_db,
    get_db_pool,
    init_db_pool,
    close_db_pool,
    init_db,
    close_db,
    CREATE_TABLES_SQL,
)
from .events import EventBus, event_bus
from .storage import (
    StorageService,
    StorageManager,
    storage_service,
    storage_manager,
    get_playback_url,
)
from .exceptions import (
    AppException,
    CODE_INVALID_CREDENTIALS,
    CODE_UNAUTHORIZED,
    CODE_TOKEN_EXPIRED,
    CODE_INVALID_TOKEN,
    CODE_USER_ALREADY_EXISTS,
    CODE_SERVICE_UNAVAILABLE,
    CODE_REGISTRATION_FAILED,
    CODE_VALIDATION_ERROR,
    CODE_INTERNAL_SERVER_ERROR,
    CODE_FORBIDDEN,
    CODE_NOT_FOUND,
)
from .security import (
    AuthenticatedUser,
    TokenData,
    UserResponse,
    security_scheme,
    get_jwks,
    verify_token,
    get_current_user,
    get_optional_current_user,
)

__all__ = [
    "BaseCommonSettings",
    "settings",
    "Base",
    "get_async_engine",
    "get_session_factory",
    "get_db_session",
    "get_db",
    "get_db_pool",
    "init_db_pool",
    "close_db_pool",
    "init_db",
    "close_db",
    "CREATE_TABLES_SQL",
    "EventBus",
    "event_bus",
    "StorageService",
    "StorageManager",
    "storage_service",
    "storage_manager",
    "get_playback_url",
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
    "AuthenticatedUser",
    "TokenData",
    "UserResponse",
    "security_scheme",
    "get_jwks",
    "verify_token",
    "get_current_user",
    "get_optional_current_user",
]

