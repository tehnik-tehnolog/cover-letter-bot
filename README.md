# Job Co-Driver Telegram Bot

Telegram-бот **[@job_co_driver_bot](https://t.me/job_co_driver_bot)** на базе **google-genai** (`gemini-3.1-flash-lite-preview`), который хранит резюме пользователя и генерирует персонализированные сопроводительные письма по ссылкам на вакансии с `hh.ru`.

## Возможности

- **Новый пользователь (`/start`)**: инструкция по загрузке резюме в формате файла (`PDF`, `DOCX`, `TXT`), обычного текста или ссылки на резюме `hh.ru`.
- **Хранение в Supabase PostgreSQL**: данные пользователя (`user_id`, `username`, `full_name`) и текст резюме сохраняются в таблице `user_resumes` (таблица создаётся автоматически при запуске).
- **Генерация письма**: парсинг страницы вакансии `hh.ru` (с резервным обращением к публичному API `api.hh.ru`) и генерация сопроводительного письма через `gemini-3.1-flash-lite-preview`.
- **Сброс и обновление (`/reset`)**: удаление текущего резюме из базы данных и загрузка нового.
- **Проверка статуса (`/status`)**: просмотр статуса сохранённого резюме.

## Переменные окружения

```env
TELEGRAM_BOT_TOKEN="ваш_тг_токен"
GEMINI_API_KEY="ваш_ключ_Gemini_API"
DATABASE_URL="postgresql://postgres.<PROJECT-REF>:ВАШ_ПАРОЛЬ@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
WEBHOOK_BASE_URL="https://<PROJECT-ID>onrender.com"
BOT_MODE="auto"
PORT=7860
```

## Локальный запуск в IDE

1. Откройте папку проекта в вашеи IDE и создайте виртуальное окружение (Python 3.11+).
2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
3. Заполните ключи и для локальной работы без webhook установите:
   ```env
   BOT_MODE="polling"
   ```
4. Запустите `main.py` в PyCharm.