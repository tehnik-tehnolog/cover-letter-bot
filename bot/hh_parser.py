from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

VACANCY_URL_RE = re.compile(
    r"https?://(?:[\w-]+\.)?hh\.(?:ru|kz|by|uz)/vacancy/(\d+)[^\s]*",
    re.IGNORECASE,
)
RESUME_URL_RE = re.compile(
    r"https?://(?:[\w-]+\.)?hh\.(?:ru|kz|by|uz)/resume/([a-zA-Z0-9]+)[^\s]*",
    re.IGNORECASE,
)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

API_HEADERS = {
    "User-Agent": "HH-CoverLetter-Bot/1.0 (telegram-bot)",
    "Accept": "application/json",
}


class HHParseError(Exception):
    """Raised when an hh.ru page cannot be fetched or parsed."""


@dataclass(frozen=True)
class VacancyData:
    vacancy_id: str
    url: str
    title: str
    company: str
    salary: str
    area: str
    experience: str
    employment: str
    skills: tuple[str, ...]
    description: str

    def to_prompt_text(self) -> str:
        parts = [f"Вакансия: {self.title}"]
        if self.company:
            parts.append(f"Компания: {self.company}")
        if self.area:
            parts.append(f"Локация: {self.area}")
        if self.salary:
            parts.append(f"Зарплата: {self.salary}")
        if self.experience:
            parts.append(f"Требуемый опыт: {self.experience}")
        if self.employment:
            parts.append(f"Занятость и формат: {self.employment}")
        if self.skills:
            parts.append(f"Ключевые навыки: {', '.join(self.skills)}")
        parts.append(f"Ссылка: {self.url}")
        if self.description:
            parts.append(f"\nОписание вакансии:\n{self.description}")
        return "\n".join(parts)


def extract_hh_vacancy_url(text: str) -> tuple[str, str] | None:
    match = VACANCY_URL_RE.search(text)
    if not match:
        return None
    return match.group(0), match.group(1)


def extract_hh_resume_url(text: str) -> tuple[str, str] | None:
    match = RESUME_URL_RE.search(text)
    if not match:
        return None
    return match.group(0), match.group(1)


def _clean_html_text(html_fragment: str) -> str:
    soup = BeautifulSoup(html_fragment, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _parse_vacancy_html(html: str, url: str, vacancy_id: str) -> VacancyData | None:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one('[data-qa="vacancy-title"]') or soup.select_one("h1")
    title = title_el.get_text(" ", strip=True) if title_el else ""

    company_el = soup.select_one('[data-qa="vacancy-company-name"]')
    company = company_el.get_text(" ", strip=True) if company_el else ""

    salary_el = soup.select_one('[data-qa="vacancy-salary"]') or soup.select_one(
        '[data-qa="vacancy-salary-compensation-type-net"]'
    )
    salary = salary_el.get_text(" ", strip=True) if salary_el else ""

    area_el = soup.select_one('[data-qa="vacancy-view-location"]') or soup.select_one(
        '[data-qa="vacancy-view-raw-address"]'
    )
    area = area_el.get_text(" ", strip=True) if area_el else ""

    exp_el = soup.select_one('[data-qa="vacancy-experience"]')
    experience = exp_el.get_text(" ", strip=True) if exp_el else ""

    employment_parts: list[str] = []
    for selector in (
        '[data-qa="vacancy-view-employment-mode"]',
        '[data-qa="work-schedule-by-days-text"]',
        '[data-qa="working-hours-text"]',
    ):
        el = soup.select_one(selector)
        if el:
            val = el.get_text(" ", strip=True)
            if val:
                employment_parts.append(val)
    employment = ", ".join(employment_parts)

    skills = tuple(
        el.get_text(" ", strip=True)
        for el in soup.select('[data-qa="skills-element"]')
        if el.get_text(strip=True)
    )

    desc_el = soup.select_one('[data-qa="vacancy-description"]')
    description = _clean_html_text(str(desc_el)) if desc_el else ""

    # Fallback to JSON-LD JobPosting if data-qa tags were absent
    if not title or not description:
        for script in soup.select('script[type="application/ld+json"]'):
            raw_json = script.string
            if not raw_json:
                continue
            try:
                payload = json.loads(raw_json)
            except json.JSONDecodeError:
                continue

            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    title = title or str(item.get("title", "")).strip()
                    hiring = item.get("hiringOrganization") or {}
                    if isinstance(hiring, dict) and not company:
                        company = str(hiring.get("name", "")).strip()
                    if not description and item.get("description"):
                        description = _clean_html_text(str(item["description"]))
                    break

    if not title or not description:
        return None

    return VacancyData(
        vacancy_id=vacancy_id,
        url=url,
        title=title,
        company=company,
        salary=salary,
        area=area,
        experience=experience,
        employment=employment,
        skills=skills,
        description=description[:15_000],
    )


def _format_api_salary(salary: dict | None) -> str:
    if not salary:
        return ""
    s_from = salary.get("from")
    s_to = salary.get("to")
    currency = salary.get("currency", "")
    gross = salary.get("gross")
    suffix = " (до вычета налогов)" if gross is True else " (на руки)" if gross is False else ""

    if s_from and s_to:
        return f"от {s_from} до {s_to} {currency}{suffix}".strip()
    if s_from:
        return f"от {s_from} {currency}{suffix}".strip()
    if s_to:
        return f"до {s_to} {currency}{suffix}".strip()
    return ""


def _parse_vacancy_api_json(data: dict, url: str, vacancy_id: str) -> VacancyData | None:
    title = str(data.get("name") or "").strip()
    raw_desc = str(data.get("description") or "").strip()
    if not title or not raw_desc:
        return None

    employer = data.get("employer") or {}
    company = str(employer.get("name") or "").strip()
    area = str((data.get("area") or {}).get("name") or "").strip()
    experience = str((data.get("experience") or {}).get("name") or "").strip()

    employment_items = [
        str((data.get("employment") or {}).get("name") or "").strip(),
        str((data.get("schedule") or {}).get("name") or "").strip(),
    ]
    employment = ", ".join(item for item in employment_items if item)

    skills = tuple(
        str(skill.get("name")).strip()
        for skill in (data.get("key_skills") or [])
        if isinstance(skill, dict) and skill.get("name")
    )

    return VacancyData(
        vacancy_id=vacancy_id,
        url=url,
        title=title,
        company=company,
        salary=_format_api_salary(data.get("salary")),
        area=area,
        experience=experience,
        employment=employment,
        skills=skills,
        description=_clean_html_text(raw_desc)[:15_000],
    )


async def fetch_hh_vacancy(url: str, vacancy_id: str) -> VacancyData:
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        # 1. Try direct web page HTML scraping
        try:
            html_resp = await client.get(url, headers=BROWSER_HEADERS)
            if html_resp.status_code == 200:
                parsed = _parse_vacancy_html(html_resp.text, url, vacancy_id)
                if parsed is not None:
                    return parsed
        except httpx.HTTPError:
            pass

        # 2. Fallback to official public hh.ru API (resilient against HTML captcha/JS walls)
        api_url = f"https://api.hh.ru/vacancies/{vacancy_id}"
        try:
            api_resp = await client.get(api_url, headers=API_HEADERS)
        except httpx.HTTPError as exc:
            raise HHParseError(
                f"Не удалось подключиться к hh.ru для загрузки вакансии: {exc}"
            ) from exc

        if api_resp.status_code == 404:
            raise HHParseError("Вакансия не найдена на hh.ru (возможно, она удалена или перенесена в архив).")
        if api_resp.status_code != 200:
            raise HHParseError(
                f"hh.ru вернул статус {api_resp.status_code} при попытке загрузить вакансию."
            )

        parsed_api = _parse_vacancy_api_json(api_resp.json(), url, vacancy_id)
        if parsed_api is None:
            raise HHParseError("Не удалось извлечь описание вакансии со страницы hh.ru.")
        return parsed_api


def _parse_resume_html(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")

    # Detect login/captcha wall
    if soup.select_one('[data-qa="account-login-form"]') or "captcha" in html.lower()[:4000]:
        return None

    blocks: list[str] = []
    selectors = [
        '[data-qa="resume-block-title-position"]',
        '[data-qa="resume-personal-age"]',
        '[data-qa="resume-personal-address"]',
        '[data-qa="resume-block-salary"]',
        '[data-qa="resume-block-experience"]',
        '[data-qa="resume-block-skills"]',
        '[data-qa="resume-block-about"]',
        '[data-qa="resume-block-education"]',
        '[data-qa="resume-block-languages"]',
    ]

    for selector in selectors:
        for el in soup.select(selector):
            text = _clean_html_text(str(el))
            if text:
                blocks.append(text)

    combined = "\n\n".join(blocks).strip()
    if len(combined) < 80:
        return None
    return combined[:25_000]


async def fetch_hh_resume(url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        try:
            resp = await client.get(url, headers=BROWSER_HEADERS)
        except httpx.HTTPError as exc:
            raise HHParseError(f"Ошибка сети при загрузке резюме с hh.ru: {exc}") from exc

        if resp.status_code == 404:
            raise HHParseError("Резюме не найдено по указанной ссылке на hh.ru.")
        if resp.status_code in (401, 403):
            raise HHParseError(
                "Доступ к резюме на hh.ru закрыт настройками приватности. "
                "Скачайте резюме в PDF/DOCX на hh.ru и отправьте файл, либо вставьте текст резюме."
            )
        if resp.status_code != 200:
            raise HHParseError(
                f"Не удалось загрузить резюме с hh.ru (HTTP {resp.status_code}). "
                "Попробуйте отправить PDF, DOCX, TXT или текст резюме."
            )

        parsed = _parse_resume_html(resp.text)
        if not parsed:
            raise HHParseError(
                "hh.ru скрыл содержимое резюме или запросил авторизацию. "
                "Отправьте резюме файлом (PDF, DOCX, TXT) или просто скопируйте его текст в сообщение."
            )
        return parsed
