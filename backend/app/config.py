from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # OpenAI — interpretation + image generation
    openai_api_key: SecretStr = SecretStr("")

    # Firebase Admin — service account JSON as a single env var string
    # Get from Firebase Console → Project settings → Service accounts → Generate new private key
    firebase_credentials_json: str = ""

    # Supabase — database + image storage (auth handled by Firebase)
    supabase_url: str = ""
    supabase_service_key: SecretStr = SecretStr("")

    # RevenueCat webhook signature
    revenuecat_webhook_secret: SecretStr = SecretStr("")

    # Fernet key for encrypting chat messages at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    chat_encryption_key: str = ""

    redis_url: str = "redis://redis:6379/0"

    environment: str = "development"
    allowed_origins: str = ""
    style_reference_url_female: str = ""
    style_reference_url_male: str = ""
    chart_rate_limit: int = 5
    astrology_api_key: str = ""

    # ── Accessors ──────────────────────────────────────────────────────────
    @property
    def openai_key(self) -> str:
        return self.openai_api_key.get_secret_value()

    @property
    def supabase_key(self) -> str:
        return self.supabase_service_key.get_secret_value()

    @property
    def rc_webhook_secret(self) -> str:
        return self.revenuecat_webhook_secret.get_secret_value()

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def origins_list(self) -> list[str]:
        if not self.allowed_origins:
            return ["*"]
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def validate_for_production(self) -> None:
        # Always required
        required = {
            "OPENAI_API_KEY": self.openai_key,
            "FIREBASE_CREDENTIALS_JSON": self.firebase_credentials_json,
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_SERVICE_KEY": self.supabase_key,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        # Only required in production
        if self.is_production:
            if not self.rc_webhook_secret:
                raise RuntimeError("REVENUECAT_WEBHOOK_SECRET must be set in production")
            if self.allowed_origins == "":
                raise RuntimeError("ALLOWED_ORIGINS must be set in production (cannot use wildcard)")


settings = Settings()
