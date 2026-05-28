"""RevenueCat webhook — updates subscription status in Supabase."""
import logging
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from app.config import settings
from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

GRANT_EVENTS = {
    "INITIAL_PURCHASE",
    "RENEWAL",
    "PRODUCT_CHANGE",
    "UNCANCELLATION",
    "SUBSCRIPTION_EXTENDED",
}

REVOKE_EVENTS = {
    "CANCELLATION",
    "EXPIRATION",
    "BILLING_ISSUE",
    "SUBSCRIBER_ALIAS",
}


def _verify_auth(authorization: str | None) -> bool:
    """Verify RevenueCat webhook via Authorization header bearer token."""
    expected: str = settings.rc_webhook_secret
    if not expected:
        logger.error("REVENUECAT_WEBHOOK_SECRET not configured — rejecting webhook")
        return False
    if not authorization:
        logger.warning("RevenueCat webhook received without Authorization header — rejected")
        return False
    # Use constant-time comparison to prevent timing attacks
    return secrets.compare_digest(authorization, f"Bearer {expected}")


@router.post("/revenuecat")
async def revenuecat_webhook(request: Request):
    authorization = request.headers.get("authorization") or request.headers.get("Authorization")
    if not _verify_auth(authorization):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = payload.get("event", {})
    event_type: str = event.get("type", "")
    app_user_id: str = event.get("app_user_id", "").strip()
    rc_customer_id: str = event.get("id", "")
    expiration_at_ms: int | None = event.get("expiration_at_ms")

    # Validate that app_user_id looks like a UUID before touching the DB
    if not app_user_id or len(app_user_id) != 36 or app_user_id.count("-") != 4:
        logger.info("Webhook ignored — app_user_id not a UUID: %r", app_user_id[:40])
        return {"received": True}

    expires_at = None
    if expiration_at_ms:
        expires_at = datetime.fromtimestamp(
            expiration_at_ms / 1000, tz=timezone.utc
        ).isoformat()

    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    if event_type in GRANT_EVENTS:
        try:
            sb.table("user_subscriptions").upsert({
                "user_id": app_user_id,
                "is_premium": True,
                "rc_customer_id": rc_customer_id,
                "expires_at": expires_at,
                "updated_at": now,
            }, on_conflict="user_id").execute()
            logger.info("Premium granted user=%s event=%s", app_user_id, event_type)
        except Exception as e:
            logger.error("Failed to grant premium user=%s: %s", app_user_id, e)
            raise HTTPException(status_code=500, detail="DB error")

    elif event_type in REVOKE_EVENTS:
        try:
            sb.table("user_subscriptions").upsert({
                "user_id": app_user_id,
                "is_premium": False,
                "rc_customer_id": rc_customer_id,
                "expires_at": expires_at,
                "updated_at": now,
            }, on_conflict="user_id").execute()
            logger.info("Premium revoked user=%s event=%s", app_user_id, event_type)
        except Exception as e:
            logger.error("Failed to revoke premium user=%s: %s", app_user_id, e)
            raise HTTPException(status_code=500, detail="DB error")

    return {"received": True}
