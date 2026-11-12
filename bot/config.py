from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

MODEL_NAME = "gemini-3.1-flash-lite"


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    gemini_api_key: str
    model_name: str = MODEL_NAME
    port: int = 7860
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10 MB


def load_settings() -> Settings:
    load_dotenv()

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    port_raw = os.getenv("PORT", "7860").strip()

    if not telegram_token:
        raise RuntimeError(
            "Environment variable TELEGRAM_BOT_TOKEN is not set. "
            "Add it to .env locally or to Space Secrets on Hugging Face."
        )

    if not gemini_key:
        raise RuntimeError(
            "Environment variable GEMINI_API_KEY is not set. "
            "Add it to .env locally or to Space Secrets on Hugging Face."
        )

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid PORT value: {port_raw!r}") from exc

    return Settings(
        telegram_bot_token=telegram_token,
        gemini_api_key=gemini_key,
        model_name=MODEL_NAME,
        port=port,
    )
