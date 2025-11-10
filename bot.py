#!/usr/bin/env python3
import logging
import sys
import database
from handlers import *
import admin_interface
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.ext import BaseHandler, TypeHandler
import config
import asyncio

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(config.LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Функция для настройки кнопок меню бота
async def setup_bot_commands(application):
    """Настройка кнопок меню бота (иконка ☰ в строке ввода)"""
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("menu", "Показать меню услуг"),
        BotCommand("help", "Показать справку"),
        BotCommand("reset", "Очистить историю диалога"),
    ]
    
    try:
        await application.bot.set_my_commands(commands)
        logger.info("✅ Bot menu commands configured successfully")
    except Exception as e:
        logger.error(f"❌ Failed to set bot commands: {e}")

# Background job для проверки лидов готовых к уведомлению
async def check_pending_leads_job(context):
    """
    Фоновая задача: проверяет лиды у которых прошло 5+ минут с последнего сообщения
    и отправляет уведомления админу (новые или обновленные)
    """
    try:
        logger.debug("Checking for pending leads ready for notification...")
        
        # Получаем лиды готовые к уведомлению (5 минут без новых сообщений)
        pending_leads = database.db.get_leads_ready_for_notification(idle_minutes=5)
        
        if pending_leads:
            logger.info(f"Found {len(pending_leads)} leads ready for notification")
            
            for lead in pending_leads:
                try:
                    # Получаем данные пользователя
                    user_data = database.db.get_user_by_id(lead['user_id'])
                    
                    if not user_data:
                        logger.warning(f"User {lead['user_id']} not found for lead {lead['id']}")
                        continue
                    
                    # Проверяем - это новый лид или обновление?
                    is_update = lead.get('notification_sent') == 1  # Если уже было уведомление
                    
                    # Формируем lead_data из сохраненных данных
                    lead_data = {
                        'name': lead.get('name'),
                        'email': lead.get('email'),
                        'phone': lead.get('phone'),
                        'company': lead.get('company'),
                        'team_size': lead.get('team_size'),
                        'contracts_per_month': lead.get('contracts_per_month'),
                        'pain_point': lead.get('pain_point'),
                        'budget': lead.get('budget'),
                        'urgency': lead.get('urgency'),
                        'industry': lead.get('industry'),
                        'service_category': lead.get('service_category'),
                        'specific_need': lead.get('specific_need'),
                        'temperature': lead.get('temperature'),
                        'lead_temperature': lead.get('temperature'),  # для совместимости
                    }
                    
                    # Отправляем уведомление админу
                    await notify_admin_new_lead(context, lead['id'], lead_data, user_data, is_update=is_update)
                    
                    action = "ОБНОВЛЕН" if is_update else "НОВЫЙ"
                    logger.info(f"✅ {action} лид: Notification sent for lead {lead['id']} (user {user_data.get('first_name')})")
                    
                except Exception as e:
                    logger.error(f"Error processing lead {lead.get('id')}: {e}", exc_info=True)
        
    except Exception as e:
        logger.error(f"Error in check_pending_leads_job: {e}", exc_info=True)

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
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("menu", menu_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("reset", reset_command))

        logger.info("Registering callback handlers...")
        application.add_handler(CallbackQueryHandler(handle_admin_panel_callback, pattern="^admin_"))
        application.add_handler(CallbackQueryHandler(handle_cleanup_callback, pattern="^cleanup_"))
        application.add_handler(CallbackQueryHandler(handle_business_menu_callback, pattern="^menu_"))

        logger.info("Registering message handlers...")
        # Обычные сообщения (НЕ команды, НЕ бизнес)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("Registering business handlers...")
        # Business connection (подключение/отключение Business аккаунта)
        application.add_handler(TypeHandler(Update, handle_business_connection, block=False), group=1)
        # Business messages (сообщения через Business аккаунт)
        application.add_handler(TypeHandler(Update, handle_business_message, block=False), group=1)

        logger.info("Registering admin handlers...")
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("leads", leads_command))
        
        logger.info("Setting up background jobs...")
        # Запускаем background job для проверки лидов (каждые 2 минуты)
        job_queue = application.job_queue
        if job_queue:
            job_queue.run_repeating(check_pending_leads_job, interval=120, first=60)
            logger.info("Background job 'check_pending_leads' scheduled (every 2 minutes)")
        else:
            logger.warning("⚠️ JobQueue not available. Install via: pip install 'python-telegram-bot[job-queue]'")
            logger.warning("⚠️ Delayed lead notifications will NOT work without JobQueue")
        
        logger.info("All handlers registered successfully")
        
        logger.info("Starting bot polling...")
        logger.info("Bot is ready to receive messages!")
        logger.info("Press Ctrl+C to stop")
        
        # Настраиваем кнопки меню бота после запуска
        async def post_init(app: Application) -> None:
            await setup_bot_commands(app)
        
        application.post_init = post_init
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")

if __name__ == '__main__':
    main()
