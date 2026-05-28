"""Request authentication — verifies Firebase ID tokens."""
import logging
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.services.firebase_admin_client import verify_firebase_token

logger = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False)


def get_user_id(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    try:
        return verify_firebase_token(credentials.credentials)
    except Exception as e:
        logger.debug("Firebase token verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Токен недействителен или истёк")
