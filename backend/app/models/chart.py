import re
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, field_validator, Field


DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


class CreateChartRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    birth_date: str = Field(
        min_length=10, max_length=10,
        description="Format: DD.MM.YYYY",
    )
    birth_time: Optional[str] = Field(
        default=None, max_length=5,
        description="Format: HH:MM",
    )
    birth_time_exact: bool = True
    birth_place: str = Field(min_length=2, max_length=200)
    gender: Literal["female", "male"] = "female"

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, v: str) -> str:
        if not DATE_RE.match(v):
            raise ValueError("Дата рождения должна быть в формате ДД.ММ.ГГГГ")
        try:
            dt = datetime.strptime(v, "%d.%m.%Y")
        except ValueError:
            raise ValueError("Некорректная дата рождения (например, 31 февраля не существует)")
        if not (1900 <= dt.year <= 2025):
            raise ValueError("Год рождения должен быть между 1900 и 2025")
        return v

    @field_validator("birth_time")
    @classmethod
    def validate_birth_time(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not TIME_RE.match(v):
            raise ValueError("Время рождения должно быть в формате ЧЧ:ММ")
        hour, minute = map(int, v.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Некорректное время рождения")
        return v

    @field_validator("name", "birth_place")
    @classmethod
    def strip_and_no_control_chars(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Поле не может быть пустым")
        return v

    def model_post_init(self, __context: object) -> None:
        # If time is not provided, it cannot be marked as exact
        if self.birth_time is None and self.birth_time_exact:
            raise ValueError("birth_time_exact cannot be True when birth_time is not provided")


class Planet(BaseModel):
    name: str
    sign: str
    house: int
    degree: float
    retrograde: bool = False


class House(BaseModel):
    number: int
    sign: str
    degree: float


class Aspect(BaseModel):
    planet1: str
    planet2: str
    aspect_type: str
    orb: float
    applying: bool = False


class ChartData(BaseModel):
    planets: list[Planet]
    houses: list[House]
    aspects: list[Aspect]
    ascendant: str
    mc: str
    sun_sign: str
    moon_sign: str


class Block(BaseModel):
    sub: str
    text: str


class Section(BaseModel):
    title: str
    blocks: list[Block]


class Interpretation(BaseModel):
    """Full interpretation — stored in DB and used internally."""
    personality: Section
    realization: Section
    money: Section
    professions: Section
    practical: Section
    summary: str
    character_prompt: str  # internal only — never sent to client


class InterpretationPublic(BaseModel):
    """Subset of interpretation returned to client. Paid sections are None for free users."""
    personality: Section
    realization: Section
    money: Section | None = None
    professions: Section | None = None
    practical: Section | None = None
    summary: str


class PremiumInterpretation(BaseModel):
    """Full premium report — generated lazily on first premium view, cached in DB."""
    money_cards: Section
    roles_matrix: Section
    top_work: Section
    periods: Section
    education: Section
    wow_insights: Section
    chat_questions: list[str]


class ChartResponse(BaseModel):
    chart_id: str
    name: str
    birth_date: str
    birth_place: str
    chart_data: ChartData
    interpretation: InterpretationPublic
    character_type: str
    character_image_url: str
    is_premium: bool = False
    premium_report: PremiumInterpretation | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    chart_id: str = Field(min_length=36, max_length=36)
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatMessage] = Field(default=[], max_length=20)


class ChatResponse(BaseModel):
    answer: str
