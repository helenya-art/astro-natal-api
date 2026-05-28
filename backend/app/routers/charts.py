"""Chart creation and retrieval endpoints."""
import logging
import uuid
from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Request

# Validated UUID path parameter — FastAPI returns 422 automatically on invalid input
_UUID_RE = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
ChartId = Annotated[str, Path(pattern=_UUID_RE)]
from slowapi import Limiter
from app.config import settings
from app.models.chart import (
    CreateChartRequest, ChartResponse, ChartData, Interpretation, InterpretationPublic, PremiumInterpretation
)
from app.services.natal_chart import geocode, calculate_chart
from app.services.interpretation import (
    interpret_chart, interpret_chart_premium, interpret_astrocartography,
    interpret_forecast, interpret_leadership, interpret_solar_return, interpret_blogging,
    interpret_forecast_month, interpret_forecast_week, interpret_forecast_day,
)
from app.services.astrology_api import get_astrocartography_lines, get_natal_transits, get_solar_return_transits
from app.services.image_gen import generate_character_image, determine_character_type
from app.services.auth import get_user_id
from app.services.supabase_client import get_supabase
from app.services.rate_limit import user_id_or_ip
from app.services.shared_limiter import limiter
from app.services.subscription import is_premium

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/charts", tags=["charts"])


def _public_interpretation(interp: Interpretation, premium: bool) -> InterpretationPublic:
    """Strip paid sections for non-premium users."""
    return InterpretationPublic(
        personality=interp.personality,
        realization=interp.realization,
        money=interp.money if premium else None,
        professions=interp.professions if premium else None,
        practical=interp.practical if premium else None,
        summary=interp.summary,
    )


def _build_response(row: dict, premium: bool) -> ChartResponse:
    interp = Interpretation(**row["interpretation"])
    premium_report = None
    if premium and row.get("premium_interpretation"):
        try:
            premium_report = PremiumInterpretation(**row["premium_interpretation"])
        except Exception as e:
            logger.warning("Failed to parse premium_interpretation: %s", e)

    return ChartResponse(
        chart_id=row["id"],
        name=row.get("name") or "",
        birth_date=row.get("birth_date") or "",
        birth_place=row.get("birth_place") or "",
        chart_data=ChartData(**row["chart_data"]),
        interpretation=_public_interpretation(interp, premium),
        character_type=row.get("character_type") or "",
        character_image_url=row.get("character_image_url") or "",
        is_premium=premium,
        premium_report=premium_report,
    )


@router.post("", response_model=ChartResponse)
@limiter.limit(f"{settings.chart_rate_limit}/hour")
async def create_chart(
    request: Request,
    body: CreateChartRequest,
    user_id: str = Depends(get_user_id),
):
    sb = get_supabase()
    premium = is_premium(user_id)

    # 0. Enforce chart limit: free=1, premium=2
    try:
        existing = sb.table("natal_charts").select("id").eq("user_id", user_id).execute()
        chart_count = len(existing.data or [])
    except Exception:
        chart_count = 0

    max_charts = 2 if premium else 1
    if chart_count >= max_charts:
        if not premium:
            raise HTTPException(status_code=403, detail="chart_limit_free")
        else:
            raise HTTPException(status_code=403, detail="chart_limit_premium")

    # 1. Geocode birth place
    try:
        lat, lon = await geocode(body.birth_place)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 2. Calculate natal chart
    try:
        chart_data = calculate_chart(
            birth_date=body.birth_date,
            birth_time=body.birth_time,
            latitude=lat,
            longitude=lon,
        )
    except Exception as e:
        logger.error("Chart calculation failed user=%s: %s", user_id, e, exc_info=True)
        raise HTTPException(status_code=422, detail="Не удалось рассчитать карту. Проверьте дату и место рождения.")

    # 3. AI interpretation
    try:
        interpretation = await interpret_chart(
            chart=chart_data,
            name=body.name,
            birth_time_exact=body.birth_time_exact,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("Interpretation failed user=%s: %s", user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось создать интерпретацию. Попробуйте ещё раз.")

    # 4. Character image
    character_type = determine_character_type(interpretation.character_prompt, body.gender)
    image_url = ""
    try:
        img_bytes = await generate_character_image(interpretation.character_prompt, body.gender)
        img_path = f"characters/{uuid.uuid4()}.png"
        sb.storage.from_("astro-images").upload(
            path=img_path,
            file=img_bytes,
            file_options={"content-type": "image/png"},
        )
        image_url = sb.storage.from_("astro-images").get_public_url(img_path)
    except Exception as e:
        logger.warning("Image generation failed user=%s: %s", user_id, e)

    # 5. Persist
    chart_id = str(uuid.uuid4())
    try:
        sb.table("natal_charts").insert({
            "id": chart_id,
            "user_id": user_id,
            "name": body.name,
            "birth_date": body.birth_date,
            "birth_time": body.birth_time,
            "birth_time_exact": body.birth_time_exact,
            "birth_place": body.birth_place,
            "latitude": lat,
            "longitude": lon,
            "chart_data": chart_data.model_dump(),
            "interpretation": interpretation.model_dump(),
            "character_type": character_type,
            "character_image_url": image_url,
        }).execute()
    except Exception as e:
        logger.error("DB insert failed user=%s: %s", user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось сохранить карту. Попробуйте ещё раз.")

    return ChartResponse(
        chart_id=chart_id,
        name=body.name,
        birth_date=body.birth_date,
        birth_place=body.birth_place,
        chart_data=chart_data,
        interpretation=_public_interpretation(interpretation, premium),
        character_type=character_type,
        character_image_url=image_url,
        is_premium=premium,
    )


def _generate_premium_bg(chart_id: str, row: dict) -> None:
    """Background task: generate and save premium interpretation without blocking response."""
    import asyncio
    async def _run():
        try:
            chart_data = ChartData(**row["chart_data"])
            premium_interp = await interpret_chart_premium(
                chart=chart_data,
                name=row.get("name", ""),
                birth_date=row.get("birth_date", ""),
                birth_time_exact=row.get("birth_time_exact", True),
            )
            sb = get_supabase()
            sb.table("natal_charts").update({
                "premium_interpretation": premium_interp.model_dump()
            }).eq("id", chart_id).execute()
            logger.info("Premium interpretation saved for chart=%s", chart_id)
        except Exception as e:
            logger.error("Premium bg generation failed chart=%s: %s", chart_id, e)
            # Mark failure in DB so GET /charts/{id} can trigger retry next time
            try:
                sb = get_supabase()
                sb.table("natal_charts").update(
                    {"premium_generation_failed": True}
                ).eq("id", chart_id).execute()
            except Exception:
                pass
    asyncio.run(_run())


@router.get("/{chart_id}", response_model=ChartResponse)
async def get_chart(
    chart_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
):
    sb = get_supabase()
    try:
        result = (
            sb.table("natal_charts")
            .select("*")
            .eq("id", chart_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
    except Exception as e:
        logger.error("DB fetch chart=%s user=%s: %s", chart_id, user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось загрузить карту.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Карта не найдена")

    premium = is_premium(user_id)
    row = result.data

    # Trigger premium generation in background — don't block the response
    if premium and not row.get("premium_interpretation"):
        background_tasks.add_task(_generate_premium_bg, chart_id, row)

    return _build_response(row, premium)


@router.get("/{chart_id}/leadership")
@limiter.limit("10/day")
async def get_leadership(request: Request,
    chart_id: ChartId, user_id: str = Depends(get_user_id)):
    """Work/leadership style analysis based on natal chart. Cached in DB."""
    if not is_premium(user_id):
        raise HTTPException(status_code=403, detail="Анализ стиля доступен в премиум-подписке")

    sb = get_supabase()
    try:
        result = sb.table("natal_charts").select(
            "name, chart_data, leadership_cache"
        ).eq("id", chart_id).eq("user_id", user_id).single().execute()
    except Exception:
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные карты.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Карта не найдена")

    row = result.data
    if row.get("leadership_cache"):
        return row["leadership_cache"]

    try:
        chart_data = ChartData(**row["chart_data"])
        leadership = await interpret_leadership(chart_data, row["name"])
        try:
            sb.table("natal_charts").update({"leadership_cache": leadership}).eq("id", chart_id).execute()
        except Exception as e:
            logger.warning("Failed to cache leadership: %s", e)
        return leadership
    except Exception as e:
        logger.error("Leadership generation failed chart=%s: %s", chart_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось создать анализ стиля. Попробуйте позже.")


@router.get("/{chart_id}/astrocartography")
@limiter.limit("10/day")
async def get_astrocartography(request: Request,
    chart_id: ChartId, user_id: str = Depends(get_user_id)):
    """Return astrocartography interpretation (cached in DB after first generation)."""
    if not is_premium(user_id):
        raise HTTPException(status_code=403, detail="Астрокартография доступна в премиум-подписке")

    sb = get_supabase()
    try:
        result = (
            sb.table("natal_charts")
            .select("name, birth_date, birth_time, latitude, longitude, astrocartography")
            .eq("id", chart_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
    except Exception as e:
        logger.error("DB fetch for astrocartography chart=%s: %s", chart_id, e)
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные карты.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Карта не найдена")

    row = result.data

    # Return cached if available
    if row.get("astrocartography"):
        return row["astrocartography"]

    # Generate
    try:
        lines_data = await get_astrocartography_lines(
            name=row["name"],
            birth_date=row["birth_date"],
            birth_time=row.get("birth_time"),
            latitude=row["latitude"],
            longitude=row["longitude"],
        )
        interpretation = await interpret_astrocartography(lines_data, row["name"])
        result_data = {
            "interpretation": interpretation,
            "raw_lines": lines_data.get("lines", []),
        }
        # Cache in DB
        try:
            sb.table("natal_charts").update(
                {"astrocartography": result_data}
            ).eq("id", chart_id).execute()
        except Exception as e:
            logger.warning("Failed to cache astrocartography: %s", e)
        return result_data
    except Exception as e:
        logger.error("Astrocartography generation failed chart=%s: %s", chart_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось рассчитать астрокартографию. Попробуйте позже.")


@router.get("/{chart_id}/forecast")
@limiter.limit("10/day")
async def get_forecast(request: Request,
    chart_id: ChartId, user_id: str = Depends(get_user_id)):
    """Yearly transit forecast + favorable dates. Cached in DB."""
    if not is_premium(user_id):
        raise HTTPException(status_code=403, detail="Прогноз доступен в премиум-подписке")

    sb = get_supabase()
    try:
        result = sb.table("natal_charts").select(
            "name, birth_date, birth_time, latitude, longitude, forecast_cache, forecast_cached_at"
        ).eq("id", chart_id).eq("user_id", user_id).single().execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные карты.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Карта не найдена")

    row = result.data

    # Return cache if fresh (< 7 days)
    from datetime import datetime, timezone, timedelta
    cached_at = row.get("forecast_cached_at")
    if row.get("forecast_cache") and cached_at:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
        if age < timedelta(days=7):
            return row["forecast_cache"]

    try:
        from datetime import date
        today = date.today()
        end = date(today.year + 1, today.month, today.day)
        period_label = f"{today.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}"

        events_data = await get_natal_transits(
            name=row["name"], birth_date=row["birth_date"],
            birth_time=row.get("birth_time"),
            latitude=row["latitude"], longitude=row["longitude"],
        )
        forecast = await interpret_forecast(events_data.get("events", []), row["name"], period_label)

        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            sb.table("natal_charts").update({
                "forecast_cache": forecast,
                "forecast_cached_at": now_iso,
            }).eq("id", chart_id).execute()
        except Exception as e:
            logger.warning("Failed to cache forecast: %s", e)

        return forecast
    except Exception as e:
        logger.error("Forecast generation failed chart=%s: %s", chart_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось рассчитать прогноз. Попробуйте позже.")


@router.get("/{chart_id}/solar-return")
@limiter.limit("10/day")
async def get_solar_return(request: Request,
    chart_id: ChartId, user_id: str = Depends(get_user_id)):
    """Solar return (yearly chart) — cached for current birthday year."""
    if not is_premium(user_id):
        raise HTTPException(status_code=403, detail="Карта года доступна в премиум-подписке")

    from datetime import date
    sb = get_supabase()
    try:
        result = sb.table("natal_charts").select(
            "name, birth_date, birth_time, latitude, longitude, solar_return_cache, solar_return_year"
        ).eq("id", chart_id).eq("user_id", user_id).single().execute()
    except Exception:
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные карты.")
    if not result.data:
        raise HTTPException(status_code=404, detail="Карта не найдена")

    row = result.data
    today = date.today()
    # Cache key: current birthday year (year when last birthday occurred)
    birth_month = int(row["birth_date"].split(".")[1])
    current_year = today.year if today.month >= birth_month else today.year - 1
    cache_year = str(current_year)

    if row.get("solar_return_cache") and str(row.get("solar_return_year", "")) == cache_year:
        return row["solar_return_cache"]

    try:
        events_data = await get_solar_return_transits(
            name=row["name"],
            birth_date=row["birth_date"],
            birth_time=row.get("birth_time"),
            latitude=row["latitude"],
            longitude=row["longitude"],
        )
        interpretation = await interpret_solar_return(events_data, row["name"], row["birth_date"])
        try:
            sb.table("natal_charts").update({
                "solar_return_cache": interpretation,
                "solar_return_year": current_year,
            }).eq("id", chart_id).execute()
        except Exception as e:
            logger.warning("Failed to cache solar return: %s", e)
        return interpretation
    except Exception as e:
        logger.error("Solar return failed chart=%s: %s", chart_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось рассчитать карту года. Попробуйте позже.")


@router.get("/{chart_id}/forecast/month")
@limiter.limit("10/day")
async def get_forecast_month(request: Request,
    chart_id: ChartId, user_id: str = Depends(get_user_id)):
    """Monthly forecast cached for the current calendar month."""
    if not is_premium(user_id):
        raise HTTPException(status_code=403, detail="Прогноз доступен в премиум-подписке")

    from datetime import date
    sb = get_supabase()
    try:
        result = sb.table("natal_charts").select(
            "name, chart_data, forecast_short_cache"
        ).eq("id", chart_id).eq("user_id", user_id).single().execute()
    except Exception:
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные карты.")
    if not result.data:
        raise HTTPException(status_code=404, detail="Карта не найдена")

    row = result.data
    today = date.today()
    month_key = today.strftime("%Y-%m")
    cache = row.get("forecast_short_cache") or {}
    if cache.get("month") and cache.get("month_key") == month_key:
        return cache["month"]

    try:
        month_label = today.strftime("%B %Y")
        chart_data = ChartData(**row["chart_data"])
        forecast = await interpret_forecast_month(chart_data, row["name"], month_label)
        cache["month"] = forecast
        cache["month_key"] = month_key
        try:
            sb.table("natal_charts").update({"forecast_short_cache": cache}).eq("id", chart_id).execute()
        except Exception as e:
            logger.warning("Failed to cache month forecast: %s", e)
        return forecast
    except Exception as e:
        logger.error("Month forecast failed chart=%s: %s", chart_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось создать прогноз на месяц.")


@router.get("/{chart_id}/forecast/week")
@limiter.limit("10/day")
async def get_forecast_week(request: Request,
    chart_id: ChartId, user_id: str = Depends(get_user_id)):
    """Weekly forecast cached for the current ISO week."""
    if not is_premium(user_id):
        raise HTTPException(status_code=403, detail="Прогноз доступен в премиум-подписке")

    from datetime import date
    sb = get_supabase()
    try:
        result = sb.table("natal_charts").select(
            "name, chart_data, forecast_short_cache"
        ).eq("id", chart_id).eq("user_id", user_id).single().execute()
    except Exception:
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные карты.")
    if not result.data:
        raise HTTPException(status_code=404, detail="Карта не найдена")

    row = result.data
    today = date.today()
    iso = today.isocalendar()
    week_key = f"{iso[0]}-W{iso[1]:02d}"
    cache = row.get("forecast_short_cache") or {}
    if cache.get("week") and cache.get("week_key") == week_key:
        return cache["week"]

    try:
        from datetime import timedelta
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        week_label = f"{week_start.strftime('%d %B')} – {week_end.strftime('%d %B %Y')}"
        chart_data = ChartData(**row["chart_data"])
        forecast = await interpret_forecast_week(chart_data, row["name"], week_label)
        cache["week"] = forecast
        cache["week_key"] = week_key
        try:
            sb.table("natal_charts").update({"forecast_short_cache": cache}).eq("id", chart_id).execute()
        except Exception as e:
            logger.warning("Failed to cache week forecast: %s", e)
        return forecast
    except Exception as e:
        logger.error("Week forecast failed chart=%s: %s", chart_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось создать прогноз на неделю.")


@router.get("/{chart_id}/forecast/day")
@limiter.limit("10/day")
async def get_forecast_day(request: Request,
    chart_id: ChartId, user_id: str = Depends(get_user_id)):
    """Daily forecast cached for today's date."""
    if not is_premium(user_id):
        raise HTTPException(status_code=403, detail="Прогноз доступен в премиум-подписке")

    from datetime import date
    sb = get_supabase()
    try:
        result = sb.table("natal_charts").select(
            "name, chart_data, forecast_short_cache"
        ).eq("id", chart_id).eq("user_id", user_id).single().execute()
    except Exception:
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные карты.")
    if not result.data:
        raise HTTPException(status_code=404, detail="Карта не найдена")

    row = result.data
    today = date.today()
    day_key = today.isoformat()
    cache = row.get("forecast_short_cache") or {}
    if cache.get("day") and cache.get("day_key") == day_key:
        return cache["day"]

    try:
        day_label = today.strftime("%A, %d %B %Y")
        chart_data = ChartData(**row["chart_data"])
        forecast = await interpret_forecast_day(chart_data, row["name"], day_label)
        cache["day"] = forecast
        cache["day_key"] = day_key
        try:
            sb.table("natal_charts").update({"forecast_short_cache": cache}).eq("id", chart_id).execute()
        except Exception as e:
            logger.warning("Failed to cache day forecast: %s", e)
        return forecast
    except Exception as e:
        logger.error("Day forecast failed chart=%s: %s", chart_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось создать прогноз на день.")


@router.delete("/{chart_id}", status_code=204)
async def delete_chart(chart_id: ChartId, user_id: str = Depends(get_user_id)):
    """Permanently delete a user's chart and all associated cached data."""
    sb = get_supabase()
    try:
        result = sb.table("natal_charts").select("id").eq("id", chart_id).eq("user_id", user_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Карта не найдена")
    if not result.data:
        raise HTTPException(status_code=404, detail="Карта не найдена")

    try:
        # Delete chat sessions for this chart
        sb.table("chat_sessions").delete().eq("chart_id", chart_id).eq("user_id", user_id).execute()
        # Delete the chart itself
        sb.table("natal_charts").delete().eq("id", chart_id).eq("user_id", user_id).execute()
    except Exception as e:
        logger.error("Failed to delete chart=%s user=%s: %s", chart_id, user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось удалить карту. Попробуйте позже.")


@router.get("/{chart_id}/blogging")
@limiter.limit("10/day")
async def get_blogging(request: Request,
    chart_id: ChartId, user_id: str = Depends(get_user_id)):
    """Detailed blogging potential analysis. Cached in DB."""
    if not is_premium(user_id):
        raise HTTPException(status_code=403, detail="Анализ блогинга доступен в премиум-подписке")

    sb = get_supabase()
    try:
        result = sb.table("natal_charts").select(
            "name, chart_data, blogging_cache"
        ).eq("id", chart_id).eq("user_id", user_id).single().execute()
    except Exception:
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные карты.")
    if not result.data:
        raise HTTPException(status_code=404, detail="Карта не найдена")

    row = result.data
    if row.get("blogging_cache"):
        return row["blogging_cache"]

    try:
        chart_data = ChartData(**row["chart_data"])
        analysis = await interpret_blogging(chart_data, row["name"])
        try:
            sb.table("natal_charts").update({"blogging_cache": analysis}).eq("id", chart_id).execute()
        except Exception as e:
            logger.warning("Failed to cache blogging: %s", e)
        return analysis
    except Exception as e:
        logger.error("Blogging analysis failed chart=%s: %s", chart_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось создать анализ. Попробуйте позже.")


@router.get("", response_model=list[ChartResponse])
async def list_charts(user_id: str = Depends(get_user_id)):
    sb = get_supabase()
    try:
        result = (
            sb.table("natal_charts")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        logger.error("DB list failed user=%s: %s", user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Не удалось загрузить список карт.")

    premium = is_premium(user_id)
    return [_build_response(row, premium) for row in (result.data or [])]
