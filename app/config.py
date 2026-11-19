"""All settings come from environment variables, so the same code runs on your laptop and in production.

Set them in a .env file (see .env.example) or in your hosting provider's dashboard.
"""
import os
import warnings
from pathlib import Path
from zoneinfo import ZoneInfo


class Settings:
    def __init__(self) -> None:
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./boutique.db")
        self.environment: str = os.getenv("ENVIRONMENT", "development")
        self.secret_key: str = os.getenv("SECRET_KEY", "")
        self.access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "720"))  # 12 h = one work day
        # bcrypt cost: 12 is a good production default (~0.25 s per hash). Tests lower it to run fast.
        self.bcrypt_rounds: int = int(os.getenv("BCRYPT_ROUNDS", "12"))
        self.store_name: str = os.getenv("STORE_NAME", "MM Store")
        # Where product photos are saved. In Docker this is a volume, so photos survive restarts.
        self.media_dir: Path = Path(os.getenv("MEDIA_DIR", "media")).resolve()
        # Never hard-code "+01:00": Morocco was UTC+1 (UTC+0 during Ramadan) until 20 Sept 2026, then
        # switched permanently back to UTC+0. ZoneInfo applies the official rules for every date.
        self.store_timezone = ZoneInfo(os.getenv("STORE_TIMEZONE", "Africa/Casablanca"))

        if not self.secret_key:
            if self.environment == "production":
                raise RuntimeError("SECRET_KEY must be set in production")
            warnings.warn("SECRET_KEY not set: using an insecure development key")
            self.secret_key = "dev-only-insecure-key-change-me-0123456789"


settings = Settings()
