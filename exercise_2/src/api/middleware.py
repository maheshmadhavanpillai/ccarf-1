"""API middleware — authentication and rate limiting."""

from typing import Callable, Any


def authorize_request(handler: Callable) -> Callable:
    """Middleware that validates Bearer token authentication.

    Extracts the token from the Authorization header, validates it,
    and attaches the authenticated user context to the request.

    Usage:
        @authorize_request
        def my_endpoint(request):
            user = request.user  # Available after auth
    """
    def wrapper(request: dict[str, Any]) -> dict[str, Any]:
        auth_header = request.get("headers", {}).get("authorization", "")

        if not auth_header.startswith("Bearer "):
            return {
                "status": 401,
                "body": {
                    "success": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Missing or invalid Authorization header"
                    }
                }
            }

        token = auth_header[7:]  # Strip "Bearer "
        # In production: validate token against auth service
        if not _validate_token(token):
            return {
                "status": 403,
                "body": {
                    "success": False,
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Token is expired or invalid"
                    }
                }
            }

        request["user"] = {"token": token, "validated": True}
        return handler(request)

    return wrapper


def rate_limit(max_requests: int = 100, window_seconds: int = 60) -> Callable:
    """Rate limiting decorator for API endpoints.

    Args:
        max_requests: Maximum requests allowed per window.
        window_seconds: Time window in seconds.
    """
    def decorator(handler: Callable) -> Callable:
        def wrapper(request: dict[str, Any]) -> dict[str, Any]:
            client_id = request.get("client_id", "anonymous")
            # In production: check Redis counter for client_id
            if _is_rate_limited(client_id, max_requests, window_seconds):
                return {
                    "status": 429,
                    "body": {
                        "success": False,
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": f"Exceeded {max_requests} requests per {window_seconds}s"
                        }
                    }
                }
            return handler(request)
        return wrapper
    return decorator


def _validate_token(token: str) -> bool:
    """Validate an authentication token. Stub for demonstration."""
    return len(token) > 10


def _is_rate_limited(client_id: str, max_req: int, window: int) -> bool:
    """Check if client has exceeded rate limit. Stub for demonstration."""
    return False
