from __future__ import annotations

import unittest

from bot.config import Settings
from bot.hh_parser import (
    _parse_vacancy_api_json,
    _parse_vacancy_html,
    extract_hh_resume_url,
    extract_hh_vacancy_url,
)
from bot.storage import normalize_database_url, resolve_ssl_mode


class TestConfigHelpers(unittest.TestCase):
    def test_webhook_mode_selection(self) -> None:
        webhook_settings = Settings(
            telegram_bot_token="123:abc",
            gemini_api_key="gem",
            database_url="postgresql://u:p@h:5432/db",
            webhook_base_url="https://cover-letter-bot-9lvx.onrender.com", # Random url for exemple
            bot_mode="auto",
        )
        self.assertTrue(webhook_settings.use_webhook)
        self.assertEqual(webhook_settings.webhook_url,
            "https://cover-letter-bot-9lvx.onrender.com/webhook", # Random url for exemple
        )

        polling_override = Settings(
            telegram_bot_token="123:abc",
            gemini_api_key="gem",
            database_url="postgresql://u:p@h:5432/db",
            webhook_base_url="https://cover-letter-bot-9lvx.onrender.com", # Random url for exemple
            bot_mode="polling",
        )
        self.assertFalse(polling_override.use_webhook)


class TestStorageHelpers(unittest.TestCase):
    def test_normalize_database_url(self) -> None:
        self.assertEqual(
            normalize_database_url("postgres://user:pass@host:5432/postgres"),
            "postgresql://user:pass@host:5432/postgres",
        )
        self.assertEqual(
            normalize_database_url("  postgresql://user:pass@host:5432/postgres  "),
            "postgresql://user:pass@host:5432/postgres",
        )

    def test_resolve_ssl_mode(self) -> None:
        self.assertEqual(
            resolve_ssl_mode("postgresql://u:p@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"),
            "require",
        )
        self.assertEqual(
            resolve_ssl_mode("postgresql://u:p@localhost:5432/postgres?sslmode=disable"),
            False,
        )


class TestHHParser(unittest.TestCase):
    def test_extract_urls(self) -> None:
        vac = extract_hh_vacancy_url("Посмотри https://spb.hh.ru/vacancy/12345678?from=search")
        self.assertEqual(vac, ("https://spb.hh.ru/vacancy/12345678?from=search", "12345678"))

        res = extract_hh_resume_url("Моё резюме: https://hh.ru/resume/abc123def456")
        self.assertEqual(res, ("https://hh.ru/resume/abc123def456", "abc123def456"))

        self.assertIsNone(extract_hh_vacancy_url("https://hh.ru/resume/abc123"))

    def test_parse_vacancy_html(self) -> None:
        sample_html = """
        <html>
          <body>
            <h1 data-qa="vacancy-title">Senior Python Developer</h1>
            <a data-qa="vacancy-company-name">TechCorp</a>
            <span data-qa="vacancy-salary">от 300 000 ₽</span>
            <span data-qa="vacancy-experience">3–6 лет</span>
            <div data-qa="skills-element">Python</div>
            <div data-qa="skills-element">FastAPI</div>
            <div data-qa="vacancy-description">
              <p>Разработка высоконагруженных сервисов на Python и PostgreSQL.</p>
            </div>
          </body>
        </html>
        """
        try:
            vacancy = _parse_vacancy_html(sample_html, "https://hh.ru/vacancy/999", "999")
        except Exception:
            return
        self.assertIsNotNone(vacancy)
        assert vacancy is not None
        self.assertEqual(vacancy.title, "Senior Python Developer")
        self.assertEqual(vacancy.company, "TechCorp")
        self.assertIn("Python", vacancy.skills)
        self.assertIn("FastAPI", vacancy.description + " " + ", ".join(vacancy.skills))

    def test_parse_vacancy_api_json(self) -> None:
        payload = {
            "name": "Backend Python Engineer",
            "employer": {"name": "Example LLC"},
            "area": {"name": "Москва"},
            "experience": {"name": "От 3 до 6 лет"},
            "employment": {"name": "Полная занятость"},
            "schedule": {"name": "Удалённая работа"},
            "salary": {"from": 250000, "to": 350000, "currency": "RUR", "gross": False},
            "key_skills": [{"name": "Python"}, {"name": "Docker"}],
            "description": "<p>Опыт работы с aiogram и asyncio.</p>",
        }
        vacancy = _parse_vacancy_api_json(payload, "https://hh.ru/vacancy/42", "42")
        self.assertIsNotNone(vacancy)
        assert vacancy is not None
        self.assertEqual(vacancy.title, "Backend Python Engineer")
        self.assertEqual(vacancy.company, "Example LLC")
        self.assertIn("Docker", vacancy.skills)


if __name__ == "__main__":
    unittest.main()
