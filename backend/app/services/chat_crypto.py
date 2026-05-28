"""Encrypt/decrypt chat messages at rest using Fernet symmetric encryption."""
import logging
from app.config import settings

logger = logging.getLogger(__name__)

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    key = settings.chat_encryption_key
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode())
        return _fernet
    except Exception as e:
        logger.error("Failed to initialise chat encryption: %s", e)
        return None


def encrypt_message(text: str) -> str:
    """Encrypt a message. Returns encrypted string prefixed with 'enc:'.
    Falls back to plaintext if encryption not configured."""
    f = _get_fernet()
    if f is None:
        return text
    try:
        return "enc:" + f.encrypt(text.encode()).decode()
    except Exception as e:
        logger.error("Message encryption failed: %s", e)
        return text


def decrypt_message(text: str) -> str:
    """Decrypt a message. Handles both encrypted ('enc:' prefix) and legacy plaintext."""
    if not text.startswith("enc:"):
        return text  # Legacy plaintext — return as-is
    f = _get_fernet()
    if f is None:
        logger.warning("Encrypted message found but CHAT_ENCRYPTION_KEY not set")
        return text
    try:
        return f.decrypt(text[4:].encode()).decode()
    except Exception as e:
        logger.error("Message decryption failed: %s", e)
        return text  # Return raw rather than crash
