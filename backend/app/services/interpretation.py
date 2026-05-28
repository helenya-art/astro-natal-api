import os
"""AI interpretation — natal chart analysis and chat via OpenAI."""
import json
import logging
from datetime import date
from openai import AsyncOpenAI
from app.config import settings
from app.models.chart import ChartData, Interpretation, InterpretationPublic, PremiumInterpretation, Section, Block

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=settings.openai_key)

INTERPRETATION_MODEL = "gpt-4.1"
CHAT_MODEL = "gpt-4.1"

ALLOWED_HISTORY_ROLES = {"user", "assistant"}

ASTROCARTOGRAPHY_PROMPT = os.getenv("ASTROCARTOGRAPHY_PROMPT", "")

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "")

PREMIUM_SYSTEM_PROMPT = os.getenv("PREMIUM_SYSTEM_PROMPT", "")

CHAT_SYSTEM = os.getenv("CHAT_SYSTEM", "")


def _chart_to_text(chart: ChartData) -> str:
    lines = [
        f"Асцендент: {chart.ascendant}",
        f"MC (Середина неба): {chart.mc}",
        "",
        "## Планеты:",
    ]
    for p in chart.planets:
        retro = " (ретро)" if p.retrograde else ""
        lines.append(f"- {p.name}: {p.sign}, {p.house} дом{retro}")

    lines += ["", "## Дома (куспиды):"]
    for h in chart.houses:
        lines.append(f"- Дом {h.number}: {h.sign}")

    lines += ["", "## Мажорные аспекты:"]
    for a in chart.aspects:
        applying = " (нарастающий)" if a.applying else ""
        lines.append(f"- {a.planet1} {a.aspect_type} {a.planet2} (орб {a.orb}{applying})")

    return "\n".join(lines)


def _parse_interpretation(raw: str) -> Interpretation:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("OpenAI returned invalid JSON: %s | raw=%.200s", e, text)
        raise ValueError("Модель вернула некорректный формат. Попробуйте ещё раз.")

    try:
        def parse_section(key: str) -> Section:
            s = data[key]
            return Section(
                title=s["title"],
                blocks=[Block(sub=b["sub"], text=b["text"]) for b in s["blocks"]],
            )

        return Interpretation(
            personality=parse_section("personality"),
            realization=parse_section("realization"),
            money=parse_section("money"),
            professions=parse_section("professions"),
            practical=parse_section("practical"),
            summary=data["summary"],
            character_prompt=data["character_prompt"],
        )
    except (KeyError, TypeError) as e:
        logger.error("OpenAI response missing field: %s | raw=%.200s", e, text)
        raise ValueError("Модель вернула неполный ответ. Попробуйте ещё раз.")


LEADERSHIP_PROMPT = os.getenv("LEADERSHIP_PROMPT", "")


FORECAST_PROMPT = os.getenv("FORECAST_PROMPT", "")


FORECAST_MONTH_PROMPT = os.getenv("FORECAST_MONTH_PROMPT", "")

FORECAST_WEEK_PROMPT = os.getenv("FORECAST_WEEK_PROMPT", "")

FORECAST_DAY_PROMPT = os.getenv("FORECAST_DAY_PROMPT", "")


async def interpret_forecast_month(chart: ChartData, name: str, month_label: str) -> dict:
    """Generate detailed monthly forecast from natal chart using gpt-4.1. No external API needed."""
    from datetime import date
    chart_text = _chart_to_text(chart)
    today = date.today()
    user_content = (
        f"Имя: {name}\n"
        f"Сегодня: {today.strftime('%d.%m.%Y')}\n"
        f"Запрошен прогноз на: {month_label}\n\n"
        f"{chart_text}"
    )
    response = await client.chat.completions.create(
        model=INTERPRETATION_MODEL,
        messages=[
            {"role": "system", "content": FORECAST_MONTH_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=2000,
        temperature=0.7,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except Exception:
        logger.error("Failed to parse month forecast JSON: %s", raw[:200])
        raise ValueError("Не удалось разобрать прогноз на месяц")


async def interpret_forecast_week(chart: ChartData, name: str, week_label: str) -> dict:
    """Generate detailed weekly forecast from natal chart using gpt-4.1."""
    from datetime import date
    chart_text = _chart_to_text(chart)
    today = date.today()
    user_content = (
        f"Имя: {name}\n"
        f"Сегодня: {today.strftime('%d.%m.%Y')} ({today.strftime('%A')})\n"
        f"Запрошен прогноз на: {week_label}\n\n"
        f"{chart_text}"
    )
    response = await client.chat.completions.create(
        model=INTERPRETATION_MODEL,
        messages=[
            {"role": "system", "content": FORECAST_WEEK_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=2500,
        temperature=0.7,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except Exception:
        logger.error("Failed to parse week forecast JSON: %s", raw[:200])
        raise ValueError("Не удалось разобрать прогноз на неделю")


async def interpret_forecast_day(chart: ChartData, name: str, day_label: str) -> dict:
    """Generate detailed daily forecast from natal chart using gpt-4.1."""
    from datetime import date
    chart_text = _chart_to_text(chart)
    today = date.today()
    user_content = (
        f"Имя: {name}\n"
        f"Дата: {today.strftime('%d.%m.%Y')} ({today.strftime('%A')})\n"
        f"Запрошен прогноз на: {day_label}\n\n"
        f"{chart_text}"
    )
    response = await client.chat.completions.create(
        model=INTERPRETATION_MODEL,
        messages=[
            {"role": "system", "content": FORECAST_DAY_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=1200,
        temperature=0.7,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except Exception:
        logger.error("Failed to parse day forecast JSON: %s", raw[:200])
        raise ValueError("Не удалось разобрать прогноз на день")


SOLAR_RETURN_PROMPT = os.getenv("SOLAR_RETURN_PROMPT", "")


async def interpret_solar_return(events_data: dict, name: str, birth_date: str) -> dict:
    """Generate solar return (yearly chart) interpretation from transit data using gpt-4.1."""
    from datetime import date
    today = date.today()
    events = events_data.get("events", [])
    events_text = "\n".join(
        f"- {e.get('date', '')} {e.get('transit_planet', '')} {e.get('aspect', '')} {e.get('natal_planet', '')}: {e.get('description', '')}"
        for e in events[:60]
    ) if events else "Данные транзитов не предоставлены."

    user_content = (
        f"Имя: {name}\n"
        f"Дата рождения: {birth_date}\n"
        f"Сегодня: {today.strftime('%d.%m.%Y')}\n"
        f"Астрологический год: от дня рождения до следующего дня рождения\n\n"
        f"Транзиты солнечного возврата:\n{events_text}"
    )

    response = await client.chat.completions.create(
        model=INTERPRETATION_MODEL,
        messages=[
            {"role": "system", "content": SOLAR_RETURN_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=2000,
        temperature=0.7,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except Exception:
        logger.error("Failed to parse solar return JSON: %s", raw[:200])
        raise ValueError("Не удалось разобрать карту года")


BLOGGING_PROMPT = os.getenv("BLOGGING_PROMPT", "")


async def interpret_blogging(chart: ChartData, name: str) -> dict:
    """Generate detailed blogging/content creation analysis from natal chart using gpt-4.1."""
    chart_text = _chart_to_text(chart)
    user_content = f"Имя: {name}\n\n{chart_text}"

    response = await client.chat.completions.create(
        model=INTERPRETATION_MODEL,
        messages=[
            {"role": "system", "content": BLOGGING_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=3000,
        temperature=0.7,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except Exception:
        logger.error("Failed to parse blogging JSON: %s", raw[:200])
        raise ValueError("Не удалось разобрать анализ блогинга")


async def interpret_leadership(chart: ChartData, name: str) -> dict:
    """Generate leadership/work style analysis from natal chart using gpt-4.1."""
    chart_text = _chart_to_text(chart)
    user_content = f"Имя: {name}\n\n{chart_text}"

    response = await client.chat.completions.create(
        model=INTERPRETATION_MODEL,
        messages=[
            {"role": "system", "content": LEADERSHIP_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=1500,
        temperature=0.7,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Leadership JSON parse failed: %s", raw[:200])
        raise ValueError("Не удалось создать анализ стиля.")


async def interpret_forecast(events: list, name: str, period_label: str) -> dict:
    """Interpret transit events into a structured forecast."""
    # Build a concise event list for the prompt
    aspect_ru = {
        "conjunction": "соединение", "trine": "трин", "sextile": "секстиль",
        "square": "квадрат", "opposition": "оппозиция",
    }
    planet_ru = {
        "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
        "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн",
        "Uranus": "Уран", "Neptune": "Нептун", "Pluto": "Плутон",
    }

    lines = []
    for e in events[:60]:  # limit context size
        planet = planet_ru.get(e.get("transiting_planet", ""), e.get("transiting_planet", ""))
        aspect = aspect_ru.get(e.get("aspect_type", ""), e.get("aspect_type", ""))
        target = planet_ru.get(e.get("stationed_planet", ""), e.get("stationed_planet", ""))
        date_str = e.get("date", "")
        direction = "нарастающий" if e.get("aspect_direction") == "applying" else "спадающий"
        lines.append(f"{date_str}: {planet} {aspect} {target} ({direction})")

    events_text = "\n".join(lines)
    user_content = f"Имя: {name}\nПериод: {period_label}\n\nСобытия:\n{events_text}"

    response = await client.chat.completions.create(
        model=INTERPRETATION_MODEL,
        messages=[
            {"role": "system", "content": FORECAST_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=3000,
        temperature=0.7,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Forecast JSON parse failed: %s", raw[:200])
        raise ValueError("Не удалось создать прогноз.")


async def interpret_astrocartography(lines_data: dict, name: str) -> dict:
    """Interpret astrocartography line data with gpt-4.1."""
    # Build concise summary of strongest lines for the prompt
    lines = lines_data.get("lines", [])
    strong = [l for l in lines if l.get("strength") in ("very_strong", "strong")]
    lines_text = "\n".join(
        f"- {l['planet']} {l['line_type']}: {l.get('meaning', '')} | keywords: {', '.join(l.get('keywords', []))}"
        for l in strong[:10]
    )
    user_content = f"Имя: {name}\n\nПланетарные линии:\n{lines_text}"

    response = await client.chat.completions.create(
        model=INTERPRETATION_MODEL,
        messages=[
            {"role": "system", "content": ASTROCARTOGRAPHY_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=2000,
        temperature=0.7,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Astrocartography JSON parse failed: %s", raw[:200])
        raise ValueError("Не удалось создать интерпретацию астрокартографии.")


async def interpret_chart(chart: ChartData, name: str, birth_time_exact: bool) -> Interpretation:
    chart_text = _chart_to_text(chart)
    time_note = (
        "Время рождения точное."
        if birth_time_exact
        else "Время рождения приблизительное — интерпретация домов менее точна."
    )
    user_content = f"Имя: {name}\n{time_note}\n\n{chart_text}"

    response = await client.chat.completions.create(
        model=INTERPRETATION_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=5000,
        temperature=0.75,
    )

    return _parse_interpretation(response.choices[0].message.content or "")


def _parse_premium_interpretation(raw: str) -> PremiumInterpretation:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("OpenAI premium returned invalid JSON: %s | raw=%.200s", e, text)
        raise ValueError("Модель вернула некорректный формат. Попробуйте ещё раз.")

    try:
        def parse_section(key: str) -> Section:
            s = data[key]
            return Section(
                title=s["title"],
                blocks=[Block(sub=b["sub"], text=b["text"]) for b in s["blocks"]],
            )

        return PremiumInterpretation(
            money_cards=parse_section("money_cards"),
            roles_matrix=parse_section("roles_matrix"),
            top_work=parse_section("top_work"),
            periods=parse_section("periods"),
            education=parse_section("education"),
            wow_insights=parse_section("wow_insights"),
            chat_questions=data.get("chat_questions", []),
        )
    except (KeyError, TypeError) as e:
        logger.error("Premium response missing field: %s | raw=%.200s", e, text)
        raise ValueError("Модель вернула неполный ответ. Попробуйте ещё раз.")


async def interpret_chart_premium(
    chart: ChartData,
    name: str,
    birth_date: str,
    birth_time_exact: bool,
) -> PremiumInterpretation:
    chart_text = _chart_to_text(chart)
    time_note = (
        "Время рождения точное."
        if birth_time_exact
        else "Время рождения приблизительное — интерпретация домов менее точна."
    )
    today = date.today().strftime("%d.%m.%Y")
    user_content = (
        f"Имя: {name}\nДата рождения: {birth_date}\nСегодня: {today}\n{time_note}\n\n{chart_text}"
    )

    response = await client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": PREMIUM_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=6000,
        temperature=0.75,
    )

    return _parse_premium_interpretation(response.choices[0].message.content or "")


async def chat_answer(
    chart: ChartData,
    name: str,
    message: str,
    history: list[dict],
    extra_context: dict | None = None,
) -> str:
    chart_text = _chart_to_text(chart)

    # Build rich context block from all available cached data
    context_parts = [f"## Натальная карта {name}:\n{chart_text}"]

    if extra_context:
        if extra_context.get("interpretation_summary"):
            context_parts.append(f"## Краткое описание личности (из разбора):\n{extra_context['interpretation_summary']}")

        if extra_context.get("leadership"):
            ldr = extra_context["leadership"]
            style = ldr.get("style_name", "")
            tagline = ldr.get("tagline", "")
            advice = ldr.get("key_advice", "")
            if style:
                context_parts.append(f"## Стиль в деле:\nСтиль: {style}\n{tagline}\nГлавный совет: {advice}")

        if extra_context.get("astrocartography"):
            astro = extra_context["astrocartography"]
            interp = astro.get("interpretation", {})
            summary = interp.get("summary", "")
            reloc = interp.get("relocation_insight", "")
            cities = interp.get("top_cities", [])
            zones = interp.get("zones_to_avoid", [])
            raw_lines = astro.get("raw_lines", [])
            astro_text = "## Астрокартография (релокация):\n"
            if summary:
                astro_text += f"Итог: {summary}\n"
            if reloc:
                astro_text += f"Стратегия: {reloc}\n"
            if cities:
                astro_text += "Лучшие города:\n" + "\n".join(
                    f"- {c.get('city')}, {c.get('country')}: {c.get('why', '')}" for c in cities[:5]
                )
            if zones:
                astro_text += "\nЗоны избегать:\n" + "\n".join(
                    f"- {z.get('region')}: {z.get('reason', '')}" for z in zones
                )
            if raw_lines:
                astro_text += f"\nВсего планетарных линий в данных: {len(raw_lines)}"
            context_parts.append(astro_text)

        if extra_context.get("forecast"):
            fc = extra_context["forecast"]
            fc_text = "## Прогноз на год:\n"
            fc_text += f"Главные темы: {fc.get('overview', '')}\n"
            fc_text += f"Ключевое действие: {fc.get('key_action', '')}"
            context_parts.append(fc_text)

    full_context = "\n\n".join(context_parts)
    system_with_chart = (
        f"{CHAT_SYSTEM}\n\n"
        "Ты имеешь доступ ко всем данным пользователя ниже. "
        "Если пользователь спрашивает о прогнозе — используй данные прогноза. "
        "Если спрашивает о городе или релокации — используй астрокартографию и рассуждай по планетарным линиям. "
        "Если спрашивает о стиле работы — используй данные стиля в деле.\n\n"
        f"{full_context}"
    )

    messages = [{"role": "system", "content": system_with_chart}]

    for h in history[-8:]:
        if h.get("role") in ALLOWED_HISTORY_ROLES and h.get("content"):
            messages.append({
                "role": h["role"],
                "content": str(h["content"])[:2000],
            })

    messages.append({"role": "user", "content": message})

    response = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        max_tokens=1200,
        temperature=0.8,
    )
    return response.choices[0].message.content or ""
