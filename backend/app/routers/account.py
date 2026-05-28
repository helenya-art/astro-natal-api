"""Account management — GDPR / Google Play data deletion requirement."""
import logging
from datetime import date, datetime, timezone
import firebase_admin.auth
from fastapi import APIRouter, Depends, HTTPException
from app.services.auth import get_user_id
from app.services.supabase_client import get_supabase
from app.services.subscription import is_premium

logger = logging.getLogger(__name__)
router = APIRouter(tags=["account"])


@router.get("/account/status")
async def account_status(user_id: str = Depends(get_user_id)):
    """Return subscription status, daily chat usage, and latest chart info."""
    sb = get_supabase()

    # Subscription info
    premium = is_premium(user_id)
    expires_at: str | None = None
    try:
        sub = sb.table("user_subscriptions").select("is_premium, expires_at").eq("user_id", user_id).limit(1).execute()
        if sub.data:
            expires_at = sub.data[0].get("expires_at")
    except Exception as e:
        logger.warning("Failed to fetch subscription for user=%s: %s", user_id, e)

    # Count today's chat messages
    today_str = date.today().isoformat()
    daily_used = 0
    try:
        sessions = sb.table("chat_sessions").select("messages").eq("user_id", user_id).execute()
        for session in (sessions.data or []):
            for msg in (session.get("messages") or []):
                if msg.get("role") == "user" and str(msg.get("created_at", "")).startswith(today_str):
                    daily_used += 1
    except Exception as e:
        logger.warning("Failed to count chat messages for user=%s: %s", user_id, e)

    # Latest chart
    chart_id: str | None = None
    try:
        charts = (
            sb.table("natal_charts")
            .select("id")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if charts.data:
            chart_id = charts.data[0]["id"]
    except Exception as e:
        logger.warning("Failed to fetch chart_id for user=%s: %s", user_id, e)

    daily_limit = 10 if premium else 1
    return {
        "is_premium": premium,
        "expires_at": expires_at,
        "daily_questions_used": daily_used,
        "daily_questions_remaining": max(0, daily_limit - daily_used),
        "daily_questions_limit": daily_limit,
        "extra_questions": 0,
        "chart_id": chart_id,
    }


@router.delete("/account", status_code=204)
async def delete_account(user_id: str = Depends(get_user_id)):
    """
    Permanently delete the authenticated user's data and Firebase account.
    Order: chat_sessions → natal_charts → user_subscriptions → Firebase user.
    """
    sb = get_supabase()
    try:
        sb.table("chat_sessions").delete().eq("user_id", user_id).execute()
        sb.table("natal_charts").delete().eq("user_id", user_id).execute()
        sb.table("user_subscriptions").delete().eq("user_id", user_id).execute()
    except Exception as e:
        logger.error("Failed to delete Supabase data for %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Не удалось удалить данные. Попробуйте позже.")

    try:
        firebase_admin.auth.delete_user(user_id)
    except firebase_admin.auth.UserNotFoundError:
        pass  # Already deleted — treat as success
    except Exception as e:
        logger.error("Failed to delete Firebase user %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Не удалось удалить аккаунт. Попробуйте позже.")
