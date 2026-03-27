"""
Конфигурация бота заявок.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ─────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# ─── Email (SMTP) ────────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.yandex.ru")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "")

# ─── Услуги ───────────────────────────────────────────────────
SERVICES = [
    "Распил",
    "Присадка и распил",
    "Проектирование + распил + присадка",
    "Подпил/переделка",
]

MAX_FILES = 10
