#!/usr/bin/env python3
import logging
import sys
import database
import handlers
import admin_interface
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.ext import BaseHandler, TypeHandler
import config

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(config.LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Background job для проверки лидов готовых к уведомлению
async def check_pending_leads_job(context):
    """
    Фоновая задача: проверяет лиды у которых прошло 5+ минут с последнего сообщения
    и отправляет уведомления админу
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
                    await handlers.notify_admin_new_lead(context, lead['id'], lead_data, user_data)
                    
                    logger.info(f"✅ Notification sent for lead {lead['id']} (user {user_data.get('first_name')})")
                    
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
        application.add_handler(CommandHandler("start", handlers.start_command))
        application.add_handler(CommandHandler("help", handlers.help_command))
        application.add_handler(CommandHandler("reset", handlers.reset_command))
        
        logger.info("Registering callback handlers...")
        application.add_handler(CallbackQueryHandler(handlers.handle_admin_panel_callback, pattern="^admin_"))
        application.add_handler(CallbackQueryHandler(handlers.handle_cleanup_callback, pattern="^cleanup_"))

        logger.info("Registering message handlers...")
        # Обычные сообщения (НЕ команды, НЕ бизнес)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))

        logger.info("Registering business handlers...")
        # Business connection (подключение/отключение Business аккаунта)
        application.add_handler(TypeHandler(Update, handlers.handle_business_connection, block=False), group=1)
        # Business messages (сообщения через Business аккаунт)
        application.add_handler(TypeHandler(Update, handlers.handle_business_message, block=False), group=1)

        logger.info("Registering admin handlers...")
        application.add_handler(CommandHandler("stats", handlers.stats_command))
        application.add_handler(CommandHandler("leads", handlers.leads_command))
        
        logger.info("Setting up background jobs...")
        # Запускаем background job для проверки лидов (каждые 2 минуты)
        job_queue = application.job_queue
        job_queue.run_repeating(check_pending_leads_job, interval=120, first=60)
        logger.info("Background job 'check_pending_leads' scheduled (every 2 minutes)")
        
        logger.info("All handlers registered successfully")
        logger.info("Starting bot polling...")
        logger.info("Bot is ready to receive messages!")
        logger.info("Press Ctrl+C to stop")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")

if __name__ == '__main__':
    main()
