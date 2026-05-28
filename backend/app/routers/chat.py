"""Chat endpoint — AI conversation about user's chart (premium only)."""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from app.models.chart import ChatRequest, ChatResponse, ChartData
from app.services.interpretation import chat_answer
from app.services.chat_crypto import encrypt_message, decrypt_message
from app.services.auth import get_user_id
from app.services.supabase_client import get_supabase
from app.services.subscription import is_premium
from app.services.shared_limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/{chart_id}", response_model=list[dict])
async def get_chat_history(chart_id: str, user_id: str = Depends(get_user_id)):
    """Return last 20 messages for a chart session."""
    sb = get_supabase()
    try:
        result = (
            sb.table("chat_sessions")
            .select("messages")
            .eq("chart_id", chart_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception:
        return []
    if not result or not result.data:
        return []
    raw = result.data[0].get("messages") or []
    # Decrypt messages on read (handles both encrypted and legacy plaintext)
    messages = [
        {**m, "content": decrypt_message(m["content"])} if m.get("content") else m
        for m in raw
    ]
    return messages[-20:]


@router.post("", response_model=ChatResponse)
@limiter.limit("30/day")
async def send_message(
    request: Request,
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
):
    sb = get_supabase()

    premium = is_premium(user_id)
    today_str = datetime.now(timezone.utc).date().isoformat()

    # Count messages: free users — total ever; premium users — today only
    try:
        sessions_result = (
            sb.table("chat_sessions")
            .select("messages")
            .eq("user_id", user_id)
            .execute()
        )
        total_user_msgs = 0
        today_user_msgs = 0
        for session in (sessions_result.data or []):
            for m in (session.get("messages") or []):
                if m.get("role") == "user":
                    total_user_msgs += 1
                    if str(m.get("created_at", "")).startswith(today_str):
                        today_user_msgs += 1
    except Exception as e:
        logger.warning("Failed to count chat messages user=%s: %s", user_id, e)
        total_user_msgs = 0
        today_user_msgs = 0

    if not premium:
        if total_user_msgs >= 1:
            raise HTTPException(status_code=402, detail="paywall")
    else:
        if today_user_msgs >= 10:
            raise HTTPException(status_code=429, detail="Лимит 10 вопросов в день исчерпан. Возвращайтесь завтра.")

    try:
        result = (
            sb.table("natal_charts")
            .select("chart_data, name, interpretation, astrocartography, forecast_cache, leadership_cache")
            .eq("id", body.chart_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
    except Exception as e:
        logger.error("DB fetch chart %s for chat: %s", body.chart_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось загрузить карту.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Карта не найдена")

    row = result.data
    chart = ChartData(**row["chart_data"])
    name = row["name"]

    # Build extra context from cached premium data
    extra_context: dict = {}
    if row.get("interpretation"):
        interp = row["interpretation"]
        extra_context["interpretation_summary"] = interp.get("summary", "")
    if row.get("astrocartography"):
        extra_context["astrocartography"] = row["astrocartography"]
    if row.get("forecast_cache"):
        extra_context["forecast"] = row["forecast_cache"]
    if row.get("leadership_cache"):
        extra_context["leadership"] = row["leadership_cache"]

    try:
        answer = await chat_answer(
            chart=chart,
            name=name,
            message=body.message,
            history=[{"role": m.role, "content": m.content} for m in body.history],
            extra_context=extra_context,
        )
    except Exception as e:
        logger.error("Claude chat failed chart %s: %s", body.chart_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось получить ответ. Попробуйте ещё раз.")

    # Persist asynchronously — user gets response immediately
    background_tasks.add_task(
        _save_messages, sb, body.chart_id, user_id, body.message, answer
    )

    return ChatResponse(answer=answer)


def _save_messages(sb, chart_id: str, user_id: str, user_msg: str, assistant_msg: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    new_msgs = [
        {"role": "user", "content": encrypt_message(user_msg), "created_at": now},
        {"role": "assistant", "content": encrypt_message(assistant_msg), "created_at": now},
    ]
    try:
        existing = (
            sb.table("chat_sessions")
            .select("id, messages")
            .eq("chart_id", chart_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            row = existing.data[0]
            msgs = list(row["messages"] or []) + new_msgs
            (
                sb.table("chat_sessions")
                .update({"messages": msgs, "updated_at": now})
                .eq("id", row["id"])
                .execute()
            )
        else:
            (
                sb.table("chat_sessions")
                .insert({"chart_id": chart_id, "user_id": user_id, "messages": new_msgs})
                .execute()
            )
    except Exception as e:
        logger.warning("Failed to persist chat messages chart=%s: %s", chart_id, e)
