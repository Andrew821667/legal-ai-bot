"""
Конфигурация бота - загрузка переменных окружения
"""
import os
from dotenv import load_dotenv

# Загрузка переменных из .env
load_dotenv()

# Обязательные переменные
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ADMIN_TELEGRAM_ID = int(os.getenv('ADMIN_TELEGRAM_ID', 0))

# OpenAI настройки
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
MAX_TOKENS = int(os.getenv('MAX_TOKENS', 800))
TEMPERATURE = float(os.getenv('TEMPERATURE', 0.7))

# База данных
DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/bot.db')

# Логирование
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'logs/bot.log')

# Поведение бота
MAX_HISTORY_MESSAGES = int(os.getenv('MAX_HISTORY_MESSAGES', 15))
RESPONSE_DELAY = int(os.getenv('RESPONSE_DELAY', 1))

# Email настройки (SMTP)
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
FROM_EMAIL = os.getenv('FROM_EMAIL', 'a.popov.gv@gmail.com')
FROM_NAME = os.getenv('FROM_NAME', 'Андрей Попов - Legal AI')

# Проверка обязательных переменных
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в .env файле")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не установлен в .env файле")

if not ADMIN_TELEGRAM_ID:
    raise ValueError("ADMIN_TELEGRAM_ID не установлен в .env файле")
