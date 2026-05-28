"""Subscription status check — reads from Supabase, written by RevenueCat webhook."""
import logging
import os
from app.services.supabase_client import get_supabase
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Comma-separated Firebase UIDs of testers who get premium access.
# Example in .env: TEST_PREMIUM_USERS=abc123,def456
# Leave empty (or omit) in production.
_raw = os.getenv("TEST_PREMIUM_USERS", "")
_TEST_PREMIUM_USERS: frozenset[str] = frozenset(
    uid.strip() for uid in _raw.split(",") if uid.strip()
)
if _TEST_PREMIUM_USERS:
    logger.warning("TEST_PREMIUM_USERS is set — %d tester(s) have free premium", len(_TEST_PREMIUM_USERS))


def is_premium(user_id: str) -> bool:
    """
    Returns True if user has an active premium subscription.
    Called on every paid-content request — Supabase query is fast (~1ms).
    """
    if user_id in _TEST_PREMIUM_USERS:
        return True

    try:
        sb = get_supabase()
        result = (
            sb.table("user_subscriptions")
            .select("is_premium, expires_at")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return False
        row = result.data[0]
        if not row["is_premium"]:
            return False
        # Also check expiry if present
        if row["expires_at"]:
            expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if expires < datetime.now(timezone.utc):
                return False
        return True
    except Exception as e:
        logger.error("Subscription check failed user=%s: %s", user_id, e)
        return False  # Fail closed — no free access on error
