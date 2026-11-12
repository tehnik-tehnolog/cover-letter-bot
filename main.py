from __future__ import annotations

import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from bot.config import Settings, load_settings
from bot.gemini_service import CoverLetterGenerator
from bot.handlers import router
from bot.storage import InMemoryResumeStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def _start_healthcheck_server(port: int, storage: InMemoryResumeStorage) -> web.AppRunner:
    """Lightweight JSON-only HTTP endpoint so Hugging Face Spaces marks the Docker Space as healthy."""

    async def health_handler(_request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "active_resumes_in_memory": await storage.count(),
            }
        )

    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info("Healthcheck server listening on 0.0.0.0:%s", port)
    return runner


async def _set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запустить бота / статус"),
            BotCommand(command="status", description="Проверить сохранённое резюме"),
            BotCommand(command="reset", description="Удалить текущее резюме и загрузить новое"),
            BotCommand(command="help", description="Справка по использованию"),
        ]
    )


async def run_bot(settings: Settings) -> None:
    storage = InMemoryResumeStorage()
    generator = CoverLetterGenerator(
        api_key=settings.gemini_api_key,
        model_name=settings.model_name,
    )

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=None),
    )

    dp = Dispatcher()
    dp["storage"] = storage
    dp["generator"] = generator
    dp["settings"] = settings
    dp.include_router(router)

    health_runner = await _start_healthcheck_server(settings.port, storage)
    try:
        await _set_bot_commands(bot)
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting Telegram bot polling with model %s", settings.model_name)
        await dp.start_polling(bot)
    finally:
        await health_runner.cleanup()
        await bot.session.close()


def main() -> None:
    settings = load_settings()
    try:
        asyncio.run(run_bot(settings))
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
