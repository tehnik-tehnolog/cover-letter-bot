from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv

MODEL_NAME = "gemini-3.1-flash-lite-preview"
BotMode = Literal["auto", "webhook", "polling"]


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    gemini_api_key: str
    database_url: str
    model_name: str = MODEL_NAME
    port: int = 7860
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    webhook_base_url: str = ""
    webhook_path: str = "/webhook"
    webhook_secret: str = ""
    bot_mode: BotMode = "auto"

    @property
    def use_webhook(self) -> bool:
        if self.bot_mode == "webhook":
            return True
        if self.bot_mode == "polling":
            return False
        return bool(self.webhook_base_url)

    @property
    def webhook_url(self) -> str:
        if not self.webhook_base_url:
            return ""
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"


def _derive_webhook_secret(token: str) -> str:
    return hashlib.sha256(f"render-webhook:{token}".encode("utf-8")).hexdigest()[:32]


def load_settings() -> Settings:
    load_dotenv()

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    port_raw = os.getenv("PORT", "7860").strip()

    webhook_base_url = (
        os.getenv("WEBHOOK_BASE_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    ).rstrip("/")

    webhook_path = os.getenv("WEBHOOK_PATH", "/webhook").strip() or "/webhook"
    if not webhook_path.startswith("/"):
        webhook_path = f"/{webhook_path}"

    bot_mode_raw = os.getenv("BOT_MODE", "auto").strip().lower() or "auto"
    if bot_mode_raw not in ("auto", "webhook", "polling"):
        raise RuntimeError(
            f"Invalid BOT_MODE={bot_mode_raw!r}. Expected 'auto', 'webhook', or 'polling'."
        )
    bot_mode: BotMode = bot_mode_raw  # type: ignore[assignment]

    if not telegram_token:
        raise RuntimeError(
            "Environment variable TELEGRAM_BOT_TOKEN is not set. "
            "Add it to .env locally or to Render Environment Variables."
        )

    if not gemini_key:
        raise RuntimeError(
            "Environment variable GEMINI_API_KEY is not set. "
            "Add it to .env locally or to Render Environment Variables."
        )

    if not database_url:
        raise RuntimeError(
            "Environment variable DATABASE_URL is not set. "
            "Add your Supabase PostgreSQL connection string to .env or Render Environment Variables."
        )

    if "[YOUR-PASSWORD]" in database_url:
        raise RuntimeError(
            "DATABASE_URL still contains the [YOUR-PASSWORD] placeholder. "
            "Replace it with your actual Supabase database password."
        )

    if bot_mode == "webhook" and not webhook_base_url:
        raise RuntimeError(
            "BOT_MODE is 'webhook', but neither WEBHOOK_BASE_URL nor RENDER_EXTERNAL_URL is set."
        )

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid PORT value: {port_raw!r}") from exc

    webhook_secret = (
        os.getenv("WEBHOOK_SECRET", "").strip()
        or _derive_webhook_secret(telegram_token)
    )

    return Settings(
        telegram_bot_token=telegram_token,
        gemini_api_key=gemini_key,
        database_url=database_url,
        model_name=MODEL_NAME,
        port=port,
        webhook_base_url=webhook_base_url,
        webhook_path=webhook_path,
        webhook_secret=webhook_secret,
        bot_mode=bot_mode,
    )
