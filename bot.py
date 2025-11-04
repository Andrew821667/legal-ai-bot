#!/usr/bin/env python3
import logging
import sys
import database
import handlers
import admin_interface
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import config

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(config.LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def main():
    try:
        logger.info("="*50)
        logger.info("Starting Legal AI Telegram Bot")
        logger.info(f"Admin ID: {config.ADMIN_TELEGRAM_ID}")
        logger.info("="*50)
        
        logger.info("Initializing database...")
        database.db = database.Database()
        database.db.init_database()
        logger.info("Database initialized successfully")
        
        admin_interface.admin_interface = admin_interface.AdminInterface(database.db)
        
        logger.info("Creating bot application...")
        application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        
        logger.info("Registering user handlers...")
        application.add_handler(CommandHandler("start", handlers.start_command))
        application.add_handler(CommandHandler("help", handlers.help_command))
        application.add_handler(CommandHandler("reset", handlers.reset_command))
        
        logger.info("Registering business handlers...")
        application.add_handler(CallbackQueryHandler(handlers.handle_admin_panel_callback, pattern="^admin_"))
        application.add_handler(CallbackQueryHandler(handlers.handle_cleanup_callback, pattern="^cleanup_"))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
        
        logger.info("Registering admin handlers...")
        application.add_handler(CommandHandler("stats", handlers.stats_command))
        application.add_handler(CommandHandler("leads", handlers.leads_command))
        
        logger.info("All handlers registered successfully")
        logger.info("Starting bot polling...")
        logger.info("Bot is ready to receive messages!")
        logger.info("Press Ctrl+C to stop")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")

if __name__ == '__main__':
    main()
