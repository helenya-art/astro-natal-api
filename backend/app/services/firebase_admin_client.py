"""Firebase Admin SDK singleton — initialised once at app startup."""
import json
import logging
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from app.config import settings

logger = logging.getLogger(__name__)

_initialised = False


def init_firebase() -> None:
    global _initialised
    if _initialised:
        return

    cred_json = settings.firebase_credentials_json
    if cred_json:
        try:
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialised with service account")
        except Exception as e:
            raise RuntimeError(f"Invalid FIREBASE_CREDENTIALS_JSON: {e}")
    else:
        # Falls back to Application Default Credentials (works on GCP/Cloud Run)
        firebase_admin.initialize_app()
        logger.info("Firebase Admin initialised with Application Default Credentials")

    _initialised = True


def verify_firebase_token(token: str) -> str:
    """Verify a Firebase ID token and return the user UID."""
    decoded = firebase_auth.verify_id_token(token, check_revoked=True)
    uid: str = decoded.get("uid", "")
    if not uid:
        raise ValueError("Token has no UID")
    return uid
