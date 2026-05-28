"""Natal chart calculation via immanuel + OpenStreetMap geocoding."""
from datetime import datetime
import aiohttp
from app.models.chart import ChartData, Planet, House, Aspect

# immanuel is imported lazily inside calculate_chart because pyswisseph
# (its C-extension dependency) is only available in Docker/Linux.

ASPECT_NAMES = {"conjunction", "opposition", "trine", "square", "sextile"}

PLANET_NAMES_RU = {
    "Sun":     "Солнце",
    "Moon":    "Луна",
    "Mercury": "Меркурий",
    "Venus":   "Венера",
    "Mars":    "Марс",
    "Jupiter": "Юпитер",
    "Saturn":  "Сатурн",
    "Uranus":  "Уран",
    "Neptune": "Нептун",
    "Pluto":   "Плутон",
}


async def geocode(place: str) -> tuple[float, float]:
    """Resolve city name to (latitude, longitude) via Nominatim."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": place, "format": "json", "limit": 1}
    headers = {"User-Agent": "AstroNatalApi/1.0 (your-contact@example.com)"}
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, params=params, headers=headers) as resp:
                results = await resp.json()
        except aiohttp.ClientError:
            raise ValueError("Сервис геокодирования недоступен. Попробуйте ещё раз.")
        if not results:
            raise ValueError("Место рождения не найдено. Уточните название города.")
        return float(results[0]["lat"]), float(results[0]["lon"])


def _angle_to_float(angle_obj) -> float:
    """Convert immanuel Angle object (or plain float/int) to float degrees."""
    if angle_obj is None:
        return 0.0
    if hasattr(angle_obj, "raw"):
        return float(angle_obj.raw)
    try:
        return float(angle_obj)
    except (TypeError, ValueError):
        return 0.0


def _sign_name(sign_obj) -> str:
    if sign_obj is None:
        return "Unknown"
    s = str(sign_obj)
    # Handle "Gemini", "Sign.Gemini", or enum repr
    return s.split(".")[-1].title()


def _house_number(house_obj) -> int:
    if house_obj is None:
        return 0
    # immanuel House object has direct .number attribute
    if hasattr(house_obj, "number"):
        try:
            return int(house_obj.number)
        except (TypeError, ValueError):
            pass
    try:
        s = str(house_obj).replace("House", "").replace("HOUSE", "").replace(".", "").strip()
        return int(s)
    except Exception:
        return 0


def calculate_chart(
    birth_date: str,
    birth_time: str | None,
    latitude: float,
    longitude: float,
) -> ChartData:
    """
    Build natal chart data from birth parameters.
    birth_date: "15.06.1990"
    birth_time: "14:30" or None (defaults to noon)
    Requires immanuel + pyswisseph — available in Docker, not on bare Windows.
    """
    from immanuel import charts as imm_charts
    from immanuel.const import chart as chart_const

    day, month, year = map(int, birth_date.strip().split("."))
    if birth_time:
        hour, minute = map(int, birth_time.strip().split(":"))
    else:
        hour, minute = 12, 0

    dt = datetime(year, month, day, hour, minute)

    try:
        native = imm_charts.Subject(
            date_time=dt.isoformat(),
            latitude=latitude,
            longitude=longitude,
        )
        natal = imm_charts.Natal(native)
    except Exception as e:
        err = str(e)
        if "time zone" in err.lower() or "zoneinfo" in err.lower() or "timezone" in err.lower():
            raise ValueError(
                "Не удалось определить часовой пояс для указанного места рождения. "
                "Попробуйте уточнить город или страну."
            )
        raise

    # ── Planets ────────────────────────────────────────────────────────────
    # natal.objects has int keys, values are Object instances.
    # Match by .name attribute (string like "Sun", "Moon" etc.)
    planets: list[Planet] = []
    for planet_obj in natal.objects.values():
        name_str = str(getattr(planet_obj, "name", ""))
        if name_str not in PLANET_NAMES_RU:
            continue
        ru_name = PLANET_NAMES_RU[name_str]
        planets.append(Planet(
            name=ru_name,
            sign=_sign_name(getattr(planet_obj, "sign", None)),
            house=_house_number(getattr(planet_obj, "house", 0)),
            degree=round(_angle_to_float(getattr(planet_obj, "longitude", None)), 2),
            retrograde=bool(getattr(planet_obj, "retrograde", False)),
        ))

    # ── Houses ─────────────────────────────────────────────────────────────
    houses: list[House] = []
    for i in range(1, 13):
        house_obj = natal.houses.get(i)
        if house_obj:
            houses.append(House(
                number=i,
                sign=_sign_name(getattr(house_obj, "sign", None)),
                degree=round(_angle_to_float(getattr(house_obj, "longitude", None)), 2),
            ))

    # ── Aspects ────────────────────────────────────────────────────────────
    # natal.aspects is a nested dict: {planet_id: {planet_id: Aspect}}
    aspects: list[Aspect] = []
    for planet_aspects in natal.aspects.values():
        if not isinstance(planet_aspects, dict):
            continue
        for asp in planet_aspects.values():
            asp_name = str(getattr(asp, "type", "")).split(".")[-1].lower()
            if asp_name not in ASPECT_NAMES:
                continue
            # asp.active and asp.passive are int keys into natal.objects
            active_obj = natal.objects.get(getattr(asp, "active", None))
            passive_obj = natal.objects.get(getattr(asp, "passive", None))
            if not active_obj or not passive_obj:
                continue
            p1_str = str(getattr(active_obj, "name", ""))
            p2_str = str(getattr(passive_obj, "name", ""))
            p1 = PLANET_NAMES_RU.get(p1_str, p1_str)
            p2 = PLANET_NAMES_RU.get(p2_str, p2_str)
            applying = "applying" in str(getattr(asp, "movement", "")).lower()
            aspects.append(Aspect(
                planet1=p1,
                planet2=p2,
                aspect_type=asp_name,
                orb=round(_angle_to_float(getattr(asp, "orb", None)), 2),
                applying=applying,
            ))

    # ── Angles ─────────────────────────────────────────────────────────────
    asc  = natal.objects.get(chart_const.ASC)
    mc   = natal.objects.get(chart_const.MC)
    sun  = natal.objects.get(chart_const.SUN)
    moon = natal.objects.get(chart_const.MOON)

    return ChartData(
        planets=planets,
        houses=houses,
        aspects=aspects,
        ascendant=_sign_name(getattr(asc,  "sign", None)),
        mc=        _sign_name(getattr(mc,   "sign", None)),
        sun_sign=  _sign_name(getattr(sun,  "sign", None)),
        moon_sign= _sign_name(getattr(moon, "sign", None)),
    )
