"""Shared rate limiter using Redis — counts are shared across all workers."""
from slowapi import Limiter
from app.services.rate_limit import user_id_or_ip
from app.config import settings

limiter = Limiter(
    key_func=user_id_or_ip,
    storage_uri=settings.redis_url,
)
