---
title: Job Co-Driver Telegram Bot
emoji: 📝
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Job Co-Driver Telegram Bot

Telegram-бот на базе **google-genai** (`gemini-3.1-flash-lite-preview`), который хранит резюме пользователя и генерирует персонализированные сопроводительные письма по ссылкам на вакансии с `hh.ru`.

## Возможности

- **Новый пользователь (`/start`)**: инструкция по загрузке резюме в формате файла (`PDF`, `DOCX`, `TXT`), обычного текста или ссылки на резюме `hh.ru`.
- **Генерация письма**: парсинг страницы вакансии `hh.ru` (с резервным обращением к публичному API `api.hh.ru`) и генерация сопроводительного письма через `gemini-3.1-flash-lite-preview`.
- **Сброс и обновление (`/reset`)**: удаление текущего резюме из памяти и загрузка нового.
- **Проверка статуса (`/status`)**: просмотр статуса загруженного резюме.

## Структура проекта

```text
.
├── bot/
│   ├── __init__.py
│   ├── config.py           # Конфигурация, MODEL_NAME и переменные окружения
│   ├── document_parser.py  # Извлечение текста из PDF, DOCX и TXT в памяти
│   ├── gemini_service.py   # Генерация писем через google-genai
│   ├── handlers.py         # Хендлеры aiogram (/start, /reset, документы, ссылки)
│   ├── hh_parser.py        # Парсер вакансий и резюме с hh.ru
│   └── storage.py          # Хранилище резюме в памяти
├── tests/
│   └── test_bot_modules.py
├── main.py                 # Точка входа (aiogram polling + JSON healthcheck :7860)
├── requirements.txt
├── Dockerfile
├── .dockerignore
└── .env.example
```

## Локальный запуск в PyCharm

1. Откройте папку проекта в **PyCharm** и создайте виртуальное окружение (Python 3.11+).
2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
3. Скопируйте `.env.example` в `.env` и заполните ключи:
   ```env
   TELEGRAM_BOT_TOKEN="ваш_токен_от_BotFather"
   GEMINI_API_KEY="ваш_ключ_Gemini_API"
   PORT=7860
   ```
4. Запустите `main.py` в PyCharm (Run Configuration -> `main.py`).