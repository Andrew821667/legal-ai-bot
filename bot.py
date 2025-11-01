#!/usr/bin/env python3
"""
Legal AI Telegram Bot - главный файл запуска
Автор: Андрей Попов
"""
import logging
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import config
import handlers
import database

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Главная функция запуска бота"""
    try:
        logger.info("=" * 50)
        logger.info("Starting Legal AI Telegram Bot")
        logger.info(f"OpenAI Model: {config.OPENAI_MODEL}")
        logger.info(f"Admin ID: {config.ADMIN_TELEGRAM_ID}")
        logger.info("=" * 50)

        # Проверка обязательных конфигураций
        if not config.TELEGRAM_BOT_TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN не установлен!")
            sys.exit(1)

        if not config.OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY не установлен!")
            sys.exit(1)

        if not config.ADMIN_TELEGRAM_ID:
            logger.error("ADMIN_TELEGRAM_ID не установлен!")
            sys.exit(1)

        # Инициализация базы данных
        logger.info("Initializing database...")
        database.db.init_database()
        logger.info("Database initialized successfully")

        # Создание приложения
        logger.info("Creating bot application...")
        application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

        # === USER HANDLERS ===
        logger.info("Registering user handlers...")

        # Команды
        application.add_handler(CommandHandler("start", handlers.start_command))
        application.add_handler(CommandHandler("help", handlers.help_command))
        application.add_handler(CommandHandler("reset", handlers.reset_command))

        # Callback handlers для inline кнопок
        application.add_handler(CallbackQueryHandler(
            handlers.handle_lead_magnet_callback,
            pattern="^magnet_"
        ))

        # Текстовые сообщения (должны быть последними)
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handlers.handle_message
        ))

        # === ADMIN HANDLERS ===
        logger.info("Registering admin handlers...")

        application.add_handler(CommandHandler("stats", handlers.stats_command))
        application.add_handler(CommandHandler("leads", handlers.leads_command))
        application.add_handler(CommandHandler("export", handlers.export_command))
        application.add_handler(CommandHandler("view_conversation", handlers.view_conversation_command))

        # === ERROR HANDLER ===
        application.add_error_handler(handlers.error_handler)

        logger.info("All handlers registered successfully")

        # Запуск бота
        logger.info("Starting bot polling...")
        logger.info("Bot is ready to receive messages!")
        logger.info("Press Ctrl+C to stop")

        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
