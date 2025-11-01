"""
Telegram handlers - обработчики команд и сообщений
"""
import logging
import time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database
import ai_brain
import lead_qualifier
import admin_interface
import config
import utils

logger = logging.getLogger(__name__)

# Меню кнопок
MAIN_MENU = [
    [KeyboardButton("📋 Услуги"), KeyboardButton("💰 Цены")],
    [KeyboardButton("📞 Консультация"), KeyboardButton("❓ Помощь")],
    [KeyboardButton("🔄 Начать заново")]
]

LEAD_MAGNET_MENU = [
    [InlineKeyboardButton("📞 Консультация 30 мин", callback_data="magnet_consultation")],
    [InlineKeyboardButton("📄 Чек-лист по договорам", callback_data="magnet_checklist")],
    [InlineKeyboardButton("🎯 Демо-анализ договора", callback_data="magnet_demo")]
]


# === USER HANDLERS ===

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        user = update.effective_user
        logger.info(f"User {user.id} started bot")

        # Создаем или обновляем пользователя в БД
        user_id = database.db.create_or_update_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

        # Приветственное сообщение
        welcome_message = (
            f"Здравствуйте, {user.first_name}! 👋\n\n"
            "Я AI-ассистент Андрея Попова, юриста с 24-летним стажем "
            "и разработчика систем автоматизации юридической работы.\n\n"
            "Могу помочь вам:\n"
            "• Рассказать об услугах по автоматизации юрработы\n"
            "• Подобрать решение под ваши задачи\n"
            "• Ответить на вопросы о технологиях\n\n"
            "Чем могу помочь вам сегодня?"
        )

        reply_markup = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)

        await update.message.reply_text(welcome_message, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте еще раз.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "📖 ПОМОЩЬ\n\n"
        "Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать эту справку\n"
        "/reset - Начать диалог заново\n\n"
        "Вы можете:\n"
        "• Задавать вопросы о услугах\n"
        "• Описать вашу ситуацию\n"
        "• Запросить консультацию\n\n"
        "Я работаю 24/7 и всегда рад помочь!"
    )

    await update.message.reply_text(help_text)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset"""
    try:
        user = update.effective_user
        user_data = database.db.get_user_by_telegram_id(user.id)

        if user_data:
            # Очищаем историю диалога
            database.db.clear_conversation_history(user_data['id'])
            logger.info(f"Conversation reset for user {user.id}")

            await update.message.reply_text(
                "История диалога очищена. Начнем сначала!\n\n"
                "Чем могу помочь вам сегодня?"
            )
        else:
            await start_command(update, context)

    except Exception as e:
        logger.error(f"Error in reset_command: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте /start")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    try:
        user = update.effective_user
        message_text = update.message.text

        logger.info(f"Message from user {user.id}: {message_text[:50]}")

        # Получаем или создаем пользователя
        user_data = database.db.get_user_by_telegram_id(user.id)
        if not user_data:
            user_id = database.db.create_or_update_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            user_data = database.db.get_user_by_telegram_id(user.id)

        # Обработка кнопок меню
        if message_text in ["📋 Услуги", "💰 Цены", "📞 Консультация", "❓ Помощь"]:
            await handle_menu_button(update, context, message_text)
            return

        if message_text == "🔄 Начать заново":
            await reset_command(update, context)
            return

        # Проверяем триггеры передачи админу
        if ai_brain.ai_brain.check_handoff_trigger(message_text):
            await handle_handoff_request(update, context)
            return

        # Сохраняем сообщение пользователя
        database.db.add_message(user_data['id'], 'user', message_text)

        # Показываем индикатор печатания
        await update.message.chat.send_action(action="typing")

        # Получаем историю диалога
        conversation_history = database.db.get_conversation_history(user_data['id'])

        # Генерируем ответ через AI
        response = ai_brain.ai_brain.generate_response(conversation_history)

        # Задержка для естественности
        time.sleep(config.RESPONSE_DELAY)

        # Сохраняем ответ ассистента
        database.db.add_message(user_data['id'], 'assistant', response)

        # Отправляем ответ
        await update.message.reply_text(response)

        # Извлекаем данные лида из диалога
        lead_data = ai_brain.ai_brain.extract_lead_data(conversation_history)

        if lead_data:
            # Обрабатываем данные лида
            lead_id = lead_qualifier.lead_qualifier.process_lead_data(user_data['id'], lead_data)

            if lead_id:
                # Проверяем нужно ли предложить lead magnet
                if ai_brain.ai_brain.should_offer_lead_magnet(lead_data):
                    await offer_lead_magnet(update, context)

                # Проверяем нужно ли уведомить админа
                if utils.is_hot_lead(lead_data):
                    admin_interface.admin_interface.send_admin_notification(
                        context.bot,
                        lead_id,
                        'hot_lead'
                    )

    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        await update.message.reply_text(
            "Извините, произошла ошибка. Попробуйте еще раз или свяжитесь с Андреем напрямую:\n"
            "📞 +7 (909) 233-09-09\n"
            "📧 a.popov.gv@gmail.com"
        )


async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE, button_text: str):
    """Обработчик кнопок меню"""
    responses = {
        "📋 Услуги": (
            "УСЛУГИ ПО АВТОМАТИЗАЦИИ ЮРРАБОТЫ:\n\n"
            "1️⃣ Договорная работа (от 150.000₽)\n"
            "   • Анализ договоров через AI за 5-10 минут\n"
            "   • Генерация договоров\n"
            "   • Экономия 60-80% времени\n\n"
            "2️⃣ Судебная работа (от 200.000₽)\n"
            "   • Анализ судебной практики\n"
            "   • Генерация процессуальных документов\n\n"
            "3️⃣ Корпоративное право и M&A (от 300.000₽)\n"
            "   • Автоматизация Due Diligence\n\n"
            "4️⃣ Земельное право (от 250.000₽)\n\n"
            "5️⃣ Комплаенс (от 200.000₽)\n\n"
            "6️⃣ Аналитика и отчетность (от 150.000₽)\n\n"
            "7️⃣ Кастомные решения (от 300.000₽)\n\n"
            "8️⃣ Юридический аутсорсинг + AI (от 100.000₽/мес)\n\n"
            "Какое направление вас интересует?"
        ),
        "💰 Цены": (
            "СТОИМОСТЬ УСЛУГ:\n\n"
            "Цены зависят от сложности задачи и объема работ.\n\n"
            "Примерные диапазоны:\n"
            "• Договорная работа: от 150.000₽\n"
            "• Судебная работа: от 200.000₽\n"
            "• M&A и корпоративное: от 300.000₽\n"
            "• Кастомные решения: от 300.000₽\n"
            "• Аутсорсинг: от 100.000₽/мес\n\n"
            "ROI внедрения: обычно 5-6 месяцев\n"
            "Экономия для компании с 5 юристами: 2-3 млн руб/год\n\n"
            "Расскажите о вашей ситуации, и я подберу оптимальное решение!"
        ),
        "📞 Консультация": (
            "БЕСПЛАТНАЯ КОНСУЛЬТАЦИЯ:\n\n"
            "Андрей может провести бесплатную консультацию (30 минут), на которой:\n"
            "• Разберет вашу ситуацию\n"
            "• Предложит варианты решений\n"
            "• Оценит сроки и стоимость\n\n"
            "Для записи на консультацию укажите ваш email или телефон."
        ),
        "❓ Помощь": (
            "КАК Я МОГУ ПОМОЧЬ:\n\n"
            "1. Отвечаю на вопросы о услугах\n"
            "2. Подбираю решения под ваши задачи\n"
            "3. Объясняю как работают технологии\n"
            "4. Записываю на консультацию с Андреем\n\n"
            "Просто опишите вашу ситуацию или задайте вопрос!"
        )
    }

    response = responses.get(button_text, "Выберите пункт меню")
    await update.message.reply_text(response)


async def offer_lead_magnet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предложение lead magnet"""
    message = (
        "🎁 ВЫБЕРИТЕ ПОДАРОК:\n\n"
        "Я могу предложить вам на выбор:\n\n"
        "📞 Бесплатную консультацию (30 мин с Андреем)\n"
        "📄 Чек-лист \"15 типовых ошибок в договорах\"\n"
        "🎯 Демо-анализ вашего договора\n\n"
        "Что вас интересует?"
    )

    reply_markup = InlineKeyboardMarkup(LEAD_MAGNET_MENU)
    await update.message.reply_text(message, reply_markup=reply_markup)


async def handle_lead_magnet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора lead magnet"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_data = database.db.get_user_by_telegram_id(user.id)

    if not user_data:
        await query.message.reply_text("Ошибка. Попробуйте /start")
        return

    magnet_type = query.data.replace("magnet_", "")

    messages = {
        "consultation": (
            "Отлично! Андрей свяжется с вами для согласования времени консультации.\n\n"
            "Укажите ваш email или телефон для связи:"
        ),
        "checklist": (
            "Отлично! Чек-лист \"15 типовых ошибок в договорах\" будет отправлен вам на email.\n\n"
            "Укажите ваш email:"
        ),
        "demo": (
            "Отлично! Для демо-анализа вашего договора:\n\n"
            "1. Отправьте мне договор (файл или фото)\n"
            "2. Укажите ваш email\n\n"
            "Анализ будет готов в течение 24 часов."
        )
    }

    # Сохраняем выбор lead magnet
    lead = database.db.get_lead_by_user_id(user_data['id'])
    if lead:
        lead_qualifier.lead_qualifier.update_lead_magnet(lead['id'], magnet_type)

        # Уведомляем админа
        admin_interface.admin_interface.send_admin_notification(
            context.bot,
            lead['id'],
            'lead_magnet_requested',
            f"Запрошен: {magnet_type}"
        )

    await query.message.reply_text(messages.get(magnet_type, "Спасибо!"))


async def handle_handoff_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса на передачу админу"""
    try:
        user = update.effective_user
        user_data = database.db.get_user_by_telegram_id(user.id)

        if not user_data:
            await update.message.reply_text("Ошибка. Попробуйте /start")
            return

        # Уведомляем пользователя
        await update.message.reply_text(
            "Понял, сейчас передам ваш запрос Андрею.\n\n"
            "Он свяжется с вами в ближайшее время:\n"
            "📞 +7 (909) 233-09-09\n"
            "📧 a.popov.gv@gmail.com\n\n"
            "Если есть еще вопросы - спрашивайте, я на связи!"
        )

        # Создаем или обновляем лид
        lead = database.db.get_lead_by_user_id(user_data['id'])
        if not lead:
            lead_id = database.db.create_or_update_lead(user_data['id'], {
                'name': user.first_name
            })
        else:
            lead_id = lead['id']

        # Уведомляем админа
        admin_interface.admin_interface.send_admin_notification(
            context.bot,
            lead_id,
            'handoff_request',
            f"Последнее сообщение: {update.message.text[:100]}"
        )

        logger.info(f"Handoff request from user {user.id}")

    except Exception as e:
        logger.error(f"Error in handle_handoff_request: {e}")


# === ADMIN HANDLERS ===

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats - статистика (только для админа)"""
    try:
        user = update.effective_user

        if user.id != config.ADMIN_TELEGRAM_ID:
            await update.message.reply_text("У вас нет доступа к этой команде")
            return

        stats_message = admin_interface.admin_interface.format_statistics(30)
        await update.message.reply_text(stats_message)

    except Exception as e:
        logger.error(f"Error in stats_command: {e}")
        await update.message.reply_text("Ошибка при получении статистики")


async def leads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /leads - список лидов (только для админа)"""
    try:
        user = update.effective_user

        if user.id != config.ADMIN_TELEGRAM_ID:
            await update.message.reply_text("У вас нет доступа к этой команде")
            return

        # Парсим аргументы (например: /leads hot)
        args = context.args
        temperature = args[0] if args else None

        leads_message = admin_interface.admin_interface.format_leads_list(
            temperature=temperature,
            limit=20
        )
        await update.message.reply_text(leads_message)

    except Exception as e:
        logger.error(f"Error in leads_command: {e}")
        await update.message.reply_text("Ошибка при получении списка лидов")


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /export - экспорт лидов в CSV (только для админа)"""
    try:
        user = update.effective_user

        if user.id != config.ADMIN_TELEGRAM_ID:
            await update.message.reply_text("У вас нет доступа к этой команде")
            return

        csv_data = admin_interface.admin_interface.export_leads_to_csv()

        if csv_data:
            await update.message.reply_document(
                document=csv_data.getvalue().encode('utf-8'),
                filename='leads_export.csv',
                caption="Экспорт лидов"
            )
        else:
            await update.message.reply_text("Ошибка при экспорте данных")

    except Exception as e:
        logger.error(f"Error in export_command: {e}")
        await update.message.reply_text("Ошибка при экспорте данных")


async def view_conversation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /view_conversation <telegram_id> - просмотр истории диалога (только для админа)"""
    try:
        user = update.effective_user

        if user.id != config.ADMIN_TELEGRAM_ID:
            await update.message.reply_text("У вас нет доступа к этой команде")
            return

        # Парсим аргументы
        args = context.args
        if not args:
            await update.message.reply_text("Использование: /view_conversation <telegram_id>")
            return

        telegram_id = int(args[0])

        history_text = admin_interface.admin_interface.get_conversation_history_text(telegram_id)

        # Разбиваем на части если слишком длинное
        max_length = 4000
        if len(history_text) > max_length:
            parts = [history_text[i:i+max_length] for i in range(0, len(history_text), max_length)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(history_text)

    except ValueError:
        await update.message.reply_text("Неверный telegram_id")
    except Exception as e:
        logger.error(f"Error in view_conversation_command: {e}")
        await update.message.reply_text("Ошибка при получении истории диалога")


# === ERROR HANDLER ===

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")

    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Произошла непредвиденная ошибка. Попробуйте еще раз или свяжитесь с поддержкой."
        )
