from __future__ import annotations

import io
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import Settings
from bot.document_parser import DocumentParseError, parse_resume_document
from bot.gemini_service import CoverLetterGenerator, GeminiGenerationError
from bot.hh_parser import (
    HHParseError,
    extract_hh_resume_url,
    extract_hh_vacancy_url,
    fetch_hh_resume,
    fetch_hh_vacancy,
)
from bot.storage import InMemoryResumeStorage

logger = logging.getLogger(__name__)

router = Router()

NEW_USER_WELCOME = (
    "Привет. Я - помощник для составления сопроводительного письма.\n\n"
    "Для начала отправьте мне ваше резюме одним файлом (PDF, DOCX или TXT), текстом или ссылкой на резюме hh.ru.\n"
    "После этого просто присылайте ссылки на интересующие вакансии с hh.ru.\n"
    "Чтобы позже обновить резюме, используйте команду /reset."
)

MIN_PLAIN_RESUME_CHARS = 30
TELEGRAM_MAX_MESSAGE_LEN = 4000


def _split_long_message(text: str, max_len: int = TELEGRAM_MAX_MESSAGE_LEN) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        split_at = remaining.rfind("\n", 0, max_len)
        if split_at <= 0:
            split_at = max_len
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


@router.message(CommandStart())
async def cmd_start(message: Message, storage: InMemoryResumeStorage) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    existing = await storage.get(user_id)

    if existing is None:
        await message.answer(NEW_USER_WELCOME)
        return

    await message.answer(
        f"У вас уже сохранено резюме в памяти ({existing.source_label}, "
        f"{len(existing.text)} симв.).\n\n"
        "Отправьте ссылку на вакансию с hh.ru — я подготовлю сопроводительное письмо.\n"
        "Если нужно заменить резюме, отправьте команду /reset."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Как пользоваться ботом:\n"
        "1. Отправьте резюме файлом (PDF, DOCX, TXT), текстом или ссылкой на hh.ru.\n"
        "2. Отправьте ссылку на вакансию с hh.ru (например, https://hh.ru/vacancy/123456).\n"
        "3. Получите готовое сопроводительное письмо.\n\n"
        "Команды:\n"
        "/start — начать работу / проверить статус\n"
        "/status — проверить сохранённое резюме\n"
        "/reset — удалить текущее резюме и загрузить новое"
    )


@router.message(Command("status"))
async def cmd_status(message: Message, storage: InMemoryResumeStorage) -> None:
    if not message.from_user:
        return

    record = await storage.get(message.from_user.id)
    if record is None:
        await message.answer(
            "Резюме сейчас не сохранено. Отправьте файл (PDF, DOCX, TXT), "
            "текст или ссылку на резюме hh.ru."
        )
        return

    preview = record.text[:250].replace("\n", " ")
    if len(record.text) > 250:
        preview += "..."
    await message.answer(
        f"Резюме в памяти: {record.source_label} ({len(record.text)} симв.)\n"
        f"Фрагмент: {preview}\n\n"
        "Отправьте ссылку на вакансию hh.ru для генерации письма или /reset для сброса."
    )


@router.message(Command("reset", "update", "clear", "new"))
async def cmd_reset(message: Message, storage: InMemoryResumeStorage) -> None:
    if not message.from_user:
        return

    removed = await storage.delete(message.from_user.id)
    if removed:
        await message.answer(
            "Текущее резюме удалено из памяти.\n"
            "Отправьте новое резюме файлом (PDF, DOCX, TXT), текстом или ссылкой на hh.ru."
        )
    else:
        await message.answer(
            "У вас ещё нет сохранённого резюме.\n"
            "Отправьте резюме файлом (PDF, DOCX, TXT), текстом или ссылкой на hh.ru."
        )


@router.message(F.document)
async def handle_document(
    message: Message,
    bot: Bot,
    storage: InMemoryResumeStorage,
    settings: Settings,
) -> None:
    if not message.from_user or not message.document:
        return

    user_id = message.from_user.id
    if await storage.has_resume(user_id):
        await message.answer(
            "У вас уже есть сохранённое резюме. Чтобы загрузить новое, сначала сбросьте текущее командой /reset."
        )
        return

    doc = message.document
    filename = doc.file_name or "resume.txt"

    if doc.file_size and doc.file_size > settings.max_file_size_bytes:
        await message.answer("Файл слишком большой. Максимальный размер — 10 МБ.")
        return

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    buffer = io.BytesIO()
    try:
        await bot.download(doc, destination=buffer)
        extracted_text = parse_resume_document(filename, buffer.getvalue())
    except DocumentParseError as exc:
        await message.answer(str(exc))
        return
    except Exception:
        logger.exception("Unexpected error while downloading/parsing document for user %s", user_id)
        await message.answer("Не удалось обработать файл. Попробуйте другой формат или вставьте текст резюме.")
        return

    await storage.save(
        user_id=user_id,
        text=extracted_text,
        source_type="file",
        source_label=f"файл {filename}",
    )

    await message.answer(
        f"Резюме из файла «{filename}» сохранено в память ({len(extracted_text)} симв.).\n\n"
        "Теперь отправьте ссылку на вакансию с hh.ru, и я напишу сопроводительное письмо."
    )


@router.message(F.text)
async def handle_text(
    message: Message,
    bot: Bot,
    storage: InMemoryResumeStorage,
    generator: CoverLetterGenerator,
) -> None:
    if not message.from_user or not message.text:
        return

    user_id = message.from_user.id
    text = message.text.strip()

    if text.startswith("/"):
        await message.answer("Неизвестная команда. Используйте /start, /status, /reset или /help.")
        return

    has_resume = await storage.has_resume(user_id)

    # Scenario 1: New user (no resume stored yet)
    if not has_resume:
        vacancy_match = extract_hh_vacancy_url(text)
        if vacancy_match:
            await message.answer(
                "Сначала нужно сохранить ваше резюме, а потом отправлять ссылку на вакансию.\n"
                "Отправьте резюме файлом (PDF, DOCX, TXT), текстом или ссылкой на резюме hh.ru."
            )
            return

        resume_match = extract_hh_resume_url(text)
        if resume_match:
            resume_url, _ = resume_match
            status_msg = await message.answer("Загружаю резюме по ссылке hh.ru...")
            await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
            try:
                parsed_resume = await fetch_hh_resume(resume_url)
            except HHParseError as exc:
                await status_msg.edit_text(str(exc))
                return

            await storage.save(
                user_id=user_id,
                text=parsed_resume,
                source_type="hh_url",
                source_label="ссылка hh.ru",
            )
            await status_msg.edit_text(
                f"Резюме с hh.ru распознано и сохранено в память ({len(parsed_resume)} симв.).\n\n"
                "Теперь отправьте ссылку на вакансию с hh.ru, чтобы получить сопроводительное письмо."
            )
            return

        if len(text) < MIN_PLAIN_RESUME_CHARS:
            await message.answer(
                "Сообщение слишком короткое для резюме. Пожалуйста, отправьте полный текст резюме, "
                "прикрепите файл (PDF, DOCX, TXT) или пришлите ссылку на резюме на hh.ru."
            )
            return

        await storage.save(
            user_id=user_id,
            text=text,
            source_type="text",
            source_label="текстовое резюме",
        )
        await message.answer(
            f"Резюме сохранено в память ({len(text)} симв.).\n\n"
            "Теперь отправьте ссылку на вакансию с hh.ru, и я сгенерирую сопроводительное письмо."
        )
        return

    # Scenario 2: Existing user (resume already in memory -> expects hh.ru vacancy link)
    vacancy_match = extract_hh_vacancy_url(text)
    if not vacancy_match:
        await message.answer(
            "Резюме уже сохранено. Пришлите ссылку на вакансию с hh.ru "
            "(например, https://hh.ru/vacancy/123456), чтобы сгенерировать сопроводительное письмо.\n\n"
            "Чтобы заменить резюме, используйте команду /reset."
        )
        return

    vacancy_url, vacancy_id = vacancy_match
    resume_record = await storage.get(user_id)
    if resume_record is None:
        await message.answer(NEW_USER_WELCOME)
        return

    status_msg = await message.answer("Изучаю вакансию и готовлю сопроводительное письмо...")
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    try:
        vacancy = await fetch_hh_vacancy(vacancy_url, vacancy_id)
        letter = await generator.generate_cover_letter(
            resume_text=resume_record.text,
            vacancy=vacancy,
        )
    except HHParseError as exc:
        await status_msg.edit_text(str(exc))
        return
    except GeminiGenerationError as exc:
        logger.exception("Gemini generation failed for user %s", user_id)
        await status_msg.edit_text(str(exc))
        return
    except Exception:
        logger.exception("Unexpected error processing vacancy %s for user %s", vacancy_id, user_id)
        await status_msg.edit_text("Произошла непредвиденная ошибка. Попробуйте позже.")
        return

    parts = _split_long_message(letter)
    await status_msg.edit_text(parts[0])
    for extra_part in parts[1:]:
        await message.answer(extra_part)


@router.message()
async def handle_unsupported_message(message: Message, storage: InMemoryResumeStorage) -> None:
    if not message.from_user:
        return

    if await storage.has_resume(message.from_user.id):
        await message.answer(
            "Отправьте текстовую ссылку на вакансию с hh.ru или используйте /reset для обновления резюме."
        )
    else:
        await message.answer(
            "Пожалуйста, отправьте резюме файлом (PDF, DOCX, TXT), текстовым сообщением или ссылкой на hh.ru."
        )
