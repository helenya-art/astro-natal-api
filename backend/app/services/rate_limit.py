"""Rate-limit key functions for slowapi."""
import logging
from fastapi import Request
from slowapi.util import get_remote_address
from app.services.firebase_admin_client import verify_firebase_token

logger = logging.getLogger(__name__)


def user_id_or_ip(request: Request) -> str:
    """
    Extract Firebase UID for per-user rate limiting.
    Falls back to IP if token is missing or invalid.
    Runs BEFORE the route handler — can't use Depends() here.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            uid = verify_firebase_token(auth[7:])
            return f"user:{uid}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}"
