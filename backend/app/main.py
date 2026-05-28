import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.services.shared_limiter import limiter as shared_limiter
from app.config import settings
from app.routers import charts, chat, webhooks, legal, account
from app.services.firebase_admin_client import init_firebase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_for_production()
    init_firebase()
    yield


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="Astro Self Map API",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    limit_str = str(exc.detail) if hasattr(exc, "detail") else str(exc)
    if "day" in limit_str:
        msg = "Лимит вопросов на сегодня исчерпан (10 в день). Возвращайтесь завтра."
    else:
        msg = "Слишком много запросов. Подождите немного и попробуйте снова."
    return JSONResponse(status_code=429, content={"detail": msg})

app.state.limiter = shared_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=False,  # Mobile API uses Bearer token, not cookies
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Versioned API (mobile client routes)
app.include_router(charts.router, prefix="/v1")
app.include_router(chat.router, prefix="/v1")
app.include_router(account.router, prefix="/v1")

# Unversioned (webhooks use fixed URLs in RevenueCat; legal pages are public)
app.include_router(webhooks.router)
app.include_router(legal.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
