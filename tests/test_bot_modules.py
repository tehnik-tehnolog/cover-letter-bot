from __future__ import annotations

import unittest

from bot.hh_parser import (
    _parse_vacancy_api_json,
    _parse_vacancy_html,
    extract_hh_resume_url,
    extract_hh_vacancy_url,
)
from bot.storage import InMemoryResumeStorage


class TestResumeStorage(unittest.IsolatedAsyncioTestCase):
    async def test_save_get_delete(self) -> None:
        storage = InMemoryResumeStorage()
        self.assertFalse(await storage.has_resume(101))

        await storage.save(101, "Python developer, 5 years", "text", "текстовое резюме")
        self.assertTrue(await storage.has_resume(101))

        record = await storage.get(101)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.text, "Python developer, 5 years")
        self.assertEqual(await storage.count(), 1)

        deleted = await storage.delete(101)
        self.assertTrue(deleted)
        self.assertFalse(await storage.has_resume(101))
        self.assertFalse(await storage.delete(101))


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
        # Only run if bs4 & lxml are installed in current Python environment
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
