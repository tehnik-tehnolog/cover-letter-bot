from __future__ import annotations

from google import genai
from google.genai import types

from bot.config import MODEL_NAME
from bot.hh_parser import VacancyData

SYSTEM_INSTRUCTION = """Ты — карьерный ИИ-помощник. Твоя задача — написать персонализированное сопроводительное письмо для отклика на вакансию на hh.ru.

Примерный алгоритм генерации письма:

1. Начало и «Крючок»:
   - Сразу укажи целевую роль и главную ключевую компетенцию/достижение кандидата в первых двух предложениях.
   - Запрещены шаблонные вступления («Меня заинтересовала ваша вакансия...», «Прошу рассмотреть мою кандидатуру...»).

2. Основная часть — Доказательство ценности (Value Proposition):
   - Выдели 2–3 ключевых требования бизнеса и сопоставь их с  фактами из резюме.
   - Оформи это в виде короткого маркированного списка (2–3 буллита).

3. Мотивация и контекст (1–2 предложения)(Опционально):
   - Покажи, почему кандидату интересен именно этот продукт, команда или технологический стек из описания вакансии.

4. Короткое завершение (Call to Action)(Опционально):
   - Заверши письмо максимально кратко и уверенно (1 предложение): готовность обсудить задачи на интервью и контакт (если он есть в резюме, иначе оставь плейсхолдер или нейтральную фразу без воды и долгих прощаний).

Жесткие ограничения и стиль:
- Объем: 600–900 знаков (идеально для чтения в окне отклика hh.ru с экрана телефона).
- Запрещены штампы: «стрессоустойчивый», «коммуникабельный», «быстро обучаемый», «командный игрок».
- Не пересказывай всю биографию из резюме — бери только релевантный под конкретную вакансию опыт.
- Выведи ТОЛЬКО готовый текст сопроводительного письма без твоих комментариев, заголовков или пояснений.
"""


class GeminiGenerationError(Exception):
    """Raised when Gemini fails to generate a cover letter."""


class CoverLetterGenerator:
    def __init__(self, api_key: str, model_name: str = MODEL_NAME) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    async def generate_cover_letter(
        self,
        resume_text: str,
        vacancy: VacancyData,
    ) -> str:
        prompt = (
            "=== РЕЗЮМЕ КАНДИДАТА ===\n"
            f"{resume_text}\n\n"
            "=== ДАННЫЕ ВАКАНСИИ ===\n"
            f"{vacancy.to_prompt_text()}\n\n"
            "Напиши готовое сопроводительное письмо для отклика на эту вакансию."
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.4,
                ),
            )
        except Exception as exc:
            raise GeminiGenerationError(
                f"Ошибка при обращении к Gemini API ({self._model_name}): {exc}"
            ) from exc

        text = (response.text or "").strip()
        if not text:
            raise GeminiGenerationError(
                "Модель Gemini вернула пустой ответ. Попробуйте отправить ссылку ещё раз."
            )
        return text
