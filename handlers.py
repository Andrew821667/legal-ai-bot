"""
Telegram handlers - обработчики команд и сообщений
"""
import logging
import time
import re
import asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database
import ai_brain
import lead_qualifier
import admin_interface
import config
import utils
import email_sender
import security
import prompts

logger = logging.getLogger(__name__)

# Меню кнопок
MAIN_MENU = [
    [KeyboardButton("📋 Услуги"), KeyboardButton("💰 Цены")],
    [KeyboardButton("📞 Консультация"), KeyboardButton("❓ Помощь")],
    [KeyboardButton("🔄 Начать заново")]
]

# Админское меню (видно только админу)
ADMIN_MENU = [
    [KeyboardButton("📋 Услуги"), KeyboardButton("💰 Цены")],
    [KeyboardButton("📞 Консультация"), KeyboardButton("❓ Помощь")],
    [KeyboardButton("⚙️ Админ-панель"), KeyboardButton("🔄 Начать заново")]
]

LEAD_MAGNET_MENU = [
    [InlineKeyboardButton("📞 Консультация 30 мин", callback_data="magnet_consultation")],
    [InlineKeyboardButton("📄 Чек-лист по договорам", callback_data="magnet_checklist")],
    [InlineKeyboardButton("🎯 Демо-анализ договора", callback_data="magnet_demo")]
]

# Админ-панель inline кнопки
ADMIN_PANEL_MENU = [
    [InlineKeyboardButton("📊 Общая статистика", callback_data="admin_stats")],
    [InlineKeyboardButton("🛡️ Безопасность", callback_data="admin_security")],
    [InlineKeyboardButton("👥 Список лидов", callback_data="admin_leads")],
    [InlineKeyboardButton("📋 Логи (последние)", callback_data="admin_logs")],
    [InlineKeyboardButton("🔥 Горячие лиды", callback_data="admin_hot_leads")],
    [InlineKeyboardButton("📥 Экспорт данных", callback_data="admin_export")],
    [InlineKeyboardButton("🗑️ Очистка данных", callback_data="admin_cleanup")],
    [InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")]
]

# Меню очистки данных
ADMIN_CLEANUP_MENU = [
    [InlineKeyboardButton("🗑️ Очистить диалоги", callback_data="cleanup_conversations")],
    [InlineKeyboardButton("🗑️ Очистить лиды", callback_data="cleanup_leads")],
    [InlineKeyboardButton("🗑️ Очистить логи", callback_data="cleanup_logs")],
    [InlineKeyboardButton("🗑️ Сбросить счетчики безопасности", callback_data="cleanup_security")],
    [InlineKeyboardButton("⚠️ ОЧИСТИТЬ ВСЁ", callback_data="cleanup_all")],
    [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
]


# === HELPER FUNCTIONS ===

def extract_email(text: str) -> str:
    """Извлекает email из текста"""
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    match = re.search(email_pattern, text)
    return match.group(0) if match else None


async def send_message_gradually(update: Update, text: str):
    """
    Отправляет сообщение постепенно, создавая эффект печатания как в ChatGPT

    Args:
        update: Telegram update
        text: Текст для отправки
    """
    import asyncio
    import re

    # Показываем индикатор печатания
    await update.message.chat.send_action(action="typing")

    # Разбиваем текст на предложения (по точкам, вопр/воскл знакам, переносам строк)
    sentences = re.split(r'([.!?]\s+|\n)', text)

    full_message = ""
    sent_message = None
    last_update_time = 0

    for i, part in enumerate(sentences):
        if not part.strip():
            continue

        # Добавляем часть к сообщению
        full_message += part

        # Показываем typing перед добавлением каждого предложения
        await update.message.chat.send_action(action="typing")

        # Задержка для имитации печатания (0.8-1.2 секунды)
        # Длиннее для предложений, короче для переносов строк
        if part.strip() in ['.', '!', '?', '\n']:
            delay = 0.3
        else:
            delay = min(len(part) / 50, 1.5)  # от длины текста, но не больше 1.5 сек

        await asyncio.sleep(delay)

        # Обновляем сообщение каждые несколько частей или когда достаточно текста
        current_time = i
        should_update = (current_time - last_update_time >= 2) or (len(full_message) - len(str(sent_message.text if sent_message else "")) > 30)

        if sent_message is None:
            # Первая отправка - когда накопилось хотя бы немного текста
            if len(full_message.strip()) > 20:
                sent_message = await update.message.reply_text(full_message)
                last_update_time = current_time
        else:
            # Обновляем существующее сообщение
            if should_update or i == len(sentences) - 1:  # Обновляем или в конце
                try:
                    await sent_message.edit_text(full_message)
                    last_update_time = current_time
                except Exception as e:
                    # Если ошибка редактирования - пропускаем
                    pass

    # Финальное обновление - убеждаемся что весь текст отправлен
    if sent_message:
        try:
            await sent_message.edit_text(text)
        except Exception:
            pass
    else:
        # Если вообще не отправили (очень короткий текст)
        await update.message.reply_text(text)


async def send_lead_magnet_email(update: Update, user_data: dict, lead: dict, email: str):
    """Отправляет email с lead magnet"""
    try:
        magnet_type = lead.get('lead_magnet_type')
        user_name = lead.get('name') or user_data.get('first_name')

        # Показываем индикатор печатания
        await update.message.chat.send_action(action="typing")

        # Отправляем email в зависимости от типа
        success = False
        if magnet_type == 'consultation':
            success = email_sender.email_sender.send_consultation_confirmation(email, user_name)
        elif magnet_type == 'checklist':
            success = email_sender.email_sender.send_checklist(email, user_name)
        elif magnet_type == 'demo':
            success = email_sender.email_sender.send_demo_request_confirmation(email, user_name)

        if success:
            # Обновляем email в lead если его там нет
            if not lead.get('email'):
                database.db.create_or_update_lead(user_data['id'], {'email': email})

            # Отмечаем lead magnet как доставленный
            lead_qualifier.lead_qualifier.mark_lead_magnet_delivered(lead['id'])

            # Подтверждение пользователю
            messages = {
                'consultation': (
                    f"✅ Отлично! Подтверждение консультации отправлено на {email}\n\n"
                    "Наша команда свяжется с вами в ближайшее время для согласования времени.\n\n"
                    "Если есть еще вопросы - спрашивайте, я на связи!"
                ),
                'checklist': (
                    f"✅ Отлично! Чек-лист отправлен на {email}\n\n"
                    "Проверьте почту (иногда письма попадают в спам).\n\n"
                    "Если хотите обсудить автоматизацию - готов ответить на вопросы!"
                ),
                'demo': (
                    f"✅ Отлично! Инструкции отправлены на {email}\n\n"
                    "Теперь вы можете отправить нам ваш договор для демо-анализа:\n"
                    "📱 Telegram: @AndrewPopov821667\n"
                    "📧 Email: a.popov.gv@gmail.com"
                )
            }

            await update.message.reply_text(messages.get(magnet_type, "✅ Спасибо! Письмо отправлено."))
            logger.info(f"Lead magnet {magnet_type} sent to {email}")
        else:
            # Ошибка отправки
            await update.message.reply_text(
                "Произошла ошибка при отправке email. Пожалуйста, свяжитесь с нами напрямую:\n\n"
                "📧 a.popov.gv@gmail.com\n"
                "📱 @AndrewPopov821667\n"
                "📞 +7 (909) 233-09-09"
            )
            logger.error(f"Failed to send lead magnet {magnet_type} to {email}")

    except Exception as e:
        logger.error(f"Error in send_lead_magnet_email: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Пожалуйста, свяжитесь с нами напрямую:\n"
            "📧 a.popov.gv@gmail.com"
        )


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
            "Я AI-ассистент команды юристов-практиков с опытом более 20 лет, "
            "которые САМИ РАЗРАБАТЫВАЮТ программное обеспечение для автоматизации юридической работы.\n\n"
            "Могу помочь вам:\n"
            "• Рассказать о наших услугах по разработке AI-решений\n"
            "• Подобрать решение под ваши задачи\n"
            "• Ответить на вопросы о технологиях\n\n"
            "Чем могу помочь вам сегодня?"
        )

        # Админу показываем расширенное меню с кнопкой админ-панели
        if user.id == config.ADMIN_TELEGRAM_ID:
            reply_markup = ReplyKeyboardMarkup(ADMIN_MENU, resize_keyboard=True)
            welcome_message += "\n\n⚙️ Доступна админ-панель!"
        else:
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
        message_text = update.effective_message.text

        # 🛡️ ЗАЩИТА: проверяем что это текстовое сообщение
        if not update.effective_message or not update.effective_message.text:
            logger.warning(f"Skipping non-text message update type: {update.update_id}")
            return

        logger.info(f"Message from user {user.id}: {message_text[:50]}")

        # 🛡️ ПРОВЕРКА БЕЗОПАСНОСТИ
        is_allowed, block_reason = security.security_manager.check_all_security(user.id, message_text)
        if not is_allowed:
            logger.warning(f"Security check failed for user {user.id}: {block_reason}")
            await update.effective_message.reply_text(block_reason)
            return

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

        # Проверяем есть ли pending lead magnet и email в сообщении
        lead = database.db.get_lead_by_user_id(user_data['id'])
        if lead and lead.get('lead_magnet_type') and not lead.get('lead_magnet_delivered'):
            email = extract_email(message_text)
            if email:
                await send_lead_magnet_email(update, user_data, lead, email)
                return

        # Обработка кнопок меню
        if message_text in ["📋 Услуги", "💰 Цены", "📞 Консультация", "❓ Помощь"]:
            await handle_menu_button(update, context, message_text)
            return

        if message_text == "🔄 Начать заново":
            await reset_command(update, context)
            return

        # Админ-панель (только для админа)
        if message_text == "⚙️ Админ-панель":
            if user.id == config.ADMIN_TELEGRAM_ID:
                await show_admin_panel(update, context)
            else:
                await update.effective_message.reply_text("У вас нет доступа к этой функции")
            return

        # Проверяем триггеры передачи админу
        if ai_brain.ai_brain.check_handoff_trigger(message_text):
            await handle_handoff_request(update, context)
            return

        # Сохраняем сообщение пользователя
        database.db.add_message(user_data['id'], 'user', message_text)

        # Получаем историю диалога
        conversation_history = database.db.get_conversation_history(user_data['id'])

        # Генерируем ответ через AI с постепенным streaming (как в GPT)
        full_response = ""
        sent_message = None
        chunk_buffer = ""
        last_update_length = 0
        last_update_time = 0
        original_message = update.effective_message

        # Показываем typing индикатор в начале
        try:
            await original_message.chat.send_action(action="typing")
            logger.info(f"Typing indicator sent for user {user_data['telegram_id']}")
        except Exception as e:
            logger.warning(f"Failed to send typing indicator: {e}")

        # Собираем ответ от OpenAI и постепенно обновляем сообщение
        start_generation = time.time()
        async for chunk in ai_brain.ai_brain.generate_response_stream(conversation_history):
            full_response += chunk
            chunk_buffer += chunk

            # Обновляем сообщение когда накопилось достаточно новых символов
            # ИЛИ прошло достаточно времени (для избежания rate limit)
            current_time = time.time()
            should_update = (
                (len(full_response) - last_update_length >= 150 and current_time - last_update_time >= 2.0) or  # Каждые 150 символов И минимум 2 сек
                (len(chunk_buffer) > 300 and current_time - last_update_time >= 3.0)  # Или каждые 3 секунды при 300+ символах
            )

            if should_update:
                if sent_message is None:
                    # Первая отправка - когда накопилось хотя бы 100 символов (снижаем частоту обновлений)
                    if len(full_response.strip()) >= 100:
                        try:
                            sent_message = await original_message.reply_text(full_response)
                            last_update_length = len(full_response)
                            last_update_time = current_time
                            chunk_buffer = ""
                            logger.debug(f"Initial message sent: {len(full_response)} chars")
                        except Exception as e:
                            logger.warning(f"Failed to send initial message: {e}")
                else:
                    # Обновляем существующее сообщение
                    try:
                        await sent_message.edit_text(full_response)
                        last_update_length = len(full_response)
                        last_update_time = current_time
                        chunk_buffer = ""
                        logger.debug(f"Message updated: {len(full_response)} chars")
                    except Exception as e:
                        # Telegram rate limit - просто пропускаем это обновление
                        logger.debug(f"Skipped update (rate limit): {e}")
                        pass

        # Финальное обновление с полным текстом
        generation_time = time.time() - start_generation
        logger.info(f"Response generated in {generation_time:.2f}s ({len(full_response)} chars)")

        # Проверяем нужно ли разбить на части (лимит Telegram 4096 символов)
        if len(full_response) > 4096:
            logger.warning(f"Response too long ({len(full_response)} chars), splitting into parts")
            # Разбиваем на части
            parts = utils.split_long_message(full_response, max_length=4000)  # Оставляем запас
            
            # Удаляем первое сообщение если оно было отправлено
            if sent_message:
                try:
                    await sent_message.delete()
                except Exception:
                    pass
            
            # Отправляем по частям
            for i, part in enumerate(parts):
                part_msg = f"[Часть {i+1}/{len(parts)}]\n\n{part}" if len(parts) > 1 else part
                await original_message.reply_text(part_msg)
                # Небольшая задержка между частями
                if i < len(parts) - 1:
                    await original_message.chat.send_action(action="typing")
                    await asyncio.sleep(0.5)
        else:
            # Обычное обновление для коротких сообщений
            if sent_message:
                try:
                    await sent_message.edit_text(full_response)
                    logger.debug("Final message update sent")
                except Exception:
                    pass
            else:
                # Если текст был слишком коротким для постепенного вывода
                await original_message.reply_text(full_response)

        # Сохраняем ответ ассистента
        database.db.add_message(user_data['id'], 'assistant', full_response)

        # 🛡️ УЧЕТ ИСПОЛЬЗОВАННЫХ ТОКЕНОВ
        # Оцениваем токены: user message + assistant response + system prompt
        user_tokens = security.security_manager.estimate_tokens(message_text)
        assistant_tokens = security.security_manager.estimate_tokens(full_response)
        system_tokens = security.security_manager.estimate_tokens(prompts.SYSTEM_PROMPT)
        total_tokens = user_tokens + assistant_tokens + system_tokens
        security.security_manager.add_tokens_used(total_tokens)
        logger.debug(f"Tokens used: user={user_tokens}, assistant={assistant_tokens}, system={system_tokens}, total={total_tokens}")

        # Извлекаем данные лида из диалога (ТОЛЬКО если это НЕ админ!)
        # Админские сообщения НЕ должны создавать лиды
        if user.id != config.ADMIN_TELEGRAM_ID:
            lead_data = ai_brain.ai_brain.extract_lead_data(conversation_history)

            if lead_data:
                # Обрабатываем данные лида
                lead_id = lead_qualifier.lead_qualifier.process_lead_data(user_data['id'], lead_data)

                if lead_id:
                    # ОБНОВЛЯЕМ ВРЕМЯ ПОСЛЕДНЕГО СООБЩЕНИЯ
                    database.db.update_lead_last_message_time(user_data['id'])
                    
                    # НЕ ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ СРАЗУ!
                    # Уведомление отправится автоматически через 5 минут без новых сообщений
                    # (см. check_pending_leads_job)
                    
                    logger.info(f"Lead {lead_id} updated, waiting for conversation to finish before notifying admin")

                # Проверяем был ли уже предложен lead magnet
                existing_lead = database.db.get_lead_by_user_id(user_data['id'])
                lead_magnet_already_offered = existing_lead and existing_lead.get('lead_magnet_type') is not None

                # Проверяем нужно ли предложить lead magnet (ТОЛЬКО ОДИН РАЗ!)
                if not lead_magnet_already_offered and ai_brain.ai_brain.should_offer_lead_magnet(lead_data):
                    await offer_lead_magnet(update, context)

                # Проверяем нужно ли уведомить админа (старая система, оставляем для совместимости)
                if utils.is_hot_lead(lead_data):
                    admin_interface.admin_interface.send_admin_notification(
                        context.bot,
                        lead_id,
                        'hot_lead'
                    )

    except Exception as e:
        # Пропускаем Peer_id_invalid - нормально для бизнес-сообщений
        if "Peer_id_invalid" not in str(e):
            logger.error(f"Error in handle_message: {e}")
            # НЕ пытаемся отправлять ошибки - может быть None или уже отправлено


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
            "Наша команда может провести бесплатную консультацию (30 минут), на которой:\n"
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
            "4. Записываю на консультацию с нашей командой\n\n"
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
        "📞 Бесплатную консультацию (30 мин с нашей командой)\n"
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
            "Отлично! Наша команда свяжется с вами для согласования времени консультации.\n\n"
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
            "Понял, сейчас передам ваш запрос нашей команде.\n\n"
            "Мы свяжемся с вами в ближайшее время:\n"
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
                document=csv_data.encode('utf-8') if isinstance(csv_data, str) else csv_data,
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


async def security_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /security_stats - статистика безопасности (только для админа)"""
    try:
        user = update.effective_user

        if user.id != config.ADMIN_TELEGRAM_ID:
            await update.message.reply_text("У вас нет доступа к этой команде")
            return

        stats = security.security_manager.get_stats()

        stats_message = (
            "🛡️ СТАТИСТИКА БЕЗОПАСНОСТИ\n\n"
            f"📊 Токены:\n"
            f"• Использовано сегодня: {stats['total_tokens_today']:,}\n"
            f"• Дневной бюджет: {stats['daily_budget']:,}\n"
            f"• Осталось: {stats['budget_remaining']:,}\n"
            f"• Использовано: {stats['budget_percentage']:.1f}%\n\n"
            f"🚫 Безопасность:\n"
            f"• Заблокированных пользователей: {stats['blacklisted_users']}\n"
            f"• Подозрительных пользователей: {stats['suspicious_users']}\n\n"
            f"⚙️ Лимиты:\n"
            f"• Сообщений в минуту: {security.security_manager.RATE_LIMITS['messages_per_minute']}\n"
            f"• Сообщений в час: {security.security_manager.RATE_LIMITS['messages_per_hour']}\n"
            f"• Сообщений в день: {security.security_manager.RATE_LIMITS['messages_per_day']}\n"
            f"• Cooldown: {security.security_manager.COOLDOWN_SECONDS} сек\n"
            f"• Макс длина сообщения: {security.security_manager.MAX_MESSAGE_LENGTH} символов"
        )

        await update.message.reply_text(stats_message)

    except Exception as e:
        logger.error(f"Error in security_stats_command: {e}")
        await update.message.reply_text("Ошибка при получении статистики безопасности")


async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /blacklist <telegram_id> - добавить в черный список (только для админа)"""
    try:
        user = update.effective_user

        if user.id != config.ADMIN_TELEGRAM_ID:
            await update.message.reply_text("У вас нет доступа к этой команде")
            return

        # Парсим аргументы
        args = context.args
        if not args:
            await update.message.reply_text(
                "Использование: /blacklist <telegram_id> [причина]\n\n"
                "Пример: /blacklist 123456789 Спам"
            )
            return

        target_user_id = int(args[0])
        reason = " ".join(args[1:]) if len(args) > 1 else "Заблокирован админом"

        # Добавляем в черный список
        security.security_manager.add_to_blacklist(target_user_id, reason)

        await update.message.reply_text(
            f"✅ Пользователь {target_user_id} добавлен в черный список\n"
            f"Причина: {reason}"
        )

        logger.info(f"Admin {user.id} blacklisted user {target_user_id}: {reason}")

    except ValueError:
        await update.message.reply_text("Неверный telegram_id. Должно быть число.")
    except Exception as e:
        logger.error(f"Error in blacklist_command: {e}")
        await update.message.reply_text("Ошибка при добавлении в черный список")


async def unblacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /unblacklist <telegram_id> - удалить из черного списка (только для админа)"""
    try:
        user = update.effective_user

        if user.id != config.ADMIN_TELEGRAM_ID:
            await update.message.reply_text("У вас нет доступа к этой команде")
            return

        # Парсим аргументы
        args = context.args
        if not args:
            await update.message.reply_text(
                "Использование: /unblacklist <telegram_id>\n\n"
                "Пример: /unblacklist 123456789"
            )
            return

        target_user_id = int(args[0])

        # Проверяем что пользователь в черном списке
        if target_user_id not in security.security_manager.blacklist:
            await update.message.reply_text(f"Пользователь {target_user_id} не найден в черном списке")
            return

        # Удаляем из черного списка
        security.security_manager.remove_from_blacklist(target_user_id)

        await update.message.reply_text(f"✅ Пользователь {target_user_id} удален из черного списка")

        logger.info(f"Admin {user.id} unblacklisted user {target_user_id}")

    except ValueError:
        await update.message.reply_text("Неверный telegram_id. Должно быть число.")
    except Exception as e:
        logger.error(f"Error in unblacklist_command: {e}")
        await update.message.reply_text("Ошибка при удалении из черного списка")


async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ админ-панели"""
    try:
        admin_panel_message = (
            "⚙️ АДМИН-ПАНЕЛЬ\n\n"
            "Выберите действие:"
        )

        reply_markup = InlineKeyboardMarkup(ADMIN_PANEL_MENU)
        await update.message.reply_text(admin_panel_message, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error in show_admin_panel: {e}")
        await update.message.reply_text("Ошибка при открытии админ-панели")


async def handle_admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback кнопок админ-панели"""
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Проверка что это админ
    if user.id != config.ADMIN_TELEGRAM_ID:
        await query.message.reply_text("У вас нет доступа к этой функции")
        return

    action = query.data

    try:
        if action == "admin_stats":
            # Общая статистика
            stats_message = admin_interface.admin_interface.format_statistics(30)
            await query.message.reply_text(stats_message)

        elif action == "admin_security":
            # Статистика безопасности
            stats = security.security_manager.get_stats()

            # Форматируем время начала статистики
            stats_since = stats['stats_start_time'].strftime("%d.%m.%Y %H:%M")

            stats_message = (
                "🛡️ СТАТИСТИКА БЕЗОПАСНОСТИ\n\n"
                f"📅 Статистика с: {stats_since}\n\n"
                f"📊 Токены:\n"
                f"• Использовано сегодня: {stats['total_tokens_today']:,}\n"
                f"• Дневной бюджет: {stats['daily_budget']:,}\n"
                f"• Осталось: {stats['budget_remaining']:,}\n"
                f"• Использовано: {stats['budget_percentage']:.1f}%\n\n"
                f"🚫 Безопасность:\n"
                f"• Заблокированных пользователей: {stats['blacklisted_users']}\n"
                f"• Подозрительных пользователей: {stats['suspicious_users']}\n\n"
                f"⚙️ Лимиты:\n"
                f"• Сообщений в минуту: {security.security_manager.RATE_LIMITS['messages_per_minute']}\n"
                f"• Сообщений в час: {security.security_manager.RATE_LIMITS['messages_per_hour']}\n"
                f"• Сообщений в день: {security.security_manager.RATE_LIMITS['messages_per_day']}\n"
                f"• Cooldown: {security.security_manager.COOLDOWN_SECONDS} сек\n"
                f"• Макс длина сообщения: {security.security_manager.MAX_MESSAGE_LENGTH} символов"
            )
            await query.message.reply_text(stats_message)

        elif action == "admin_leads":
            # Список всех лидов
            leads_message = admin_interface.admin_interface.format_leads_list(limit=20)
            await query.message.reply_text(leads_message)

        elif action == "admin_hot_leads":
            # Только горячие лиды
            leads_message = admin_interface.admin_interface.format_leads_list(temperature='hot', limit=10)
            await query.message.reply_text(leads_message)

        elif action == "admin_logs":
            # Последние строки логов
            import subprocess
            result = subprocess.run(['tail', '-50', config.LOG_FILE], capture_output=True, text=True)
            logs = result.stdout

            # Добавляем цветные индикаторы для ошибок и предупреждений
            formatted_lines = []
            for line in logs.split('\n'):
                if ' - ERROR - ' in line:
                    formatted_lines.append(f"🔴 {line}")  # Красный индикатор для ошибок
                elif ' - WARNING - ' in line:
                    formatted_lines.append(f"⚠️ {line}")  # Желтый индикатор для предупреждений
                else:
                    formatted_lines.append(line)

            formatted_logs = '\n'.join(formatted_lines)

            if len(formatted_logs) > 4000:
                formatted_logs = formatted_logs[-4000:]  # Telegram limit

            await query.message.reply_text(f"📋 ПОСЛЕДНИЕ ЛОГИ:\n\n```\n{formatted_logs}\n```", parse_mode="Markdown")

        elif action == "admin_export":
            # Экспорт лидов в CSV
            csv_data = admin_interface.admin_interface.export_leads_to_csv()

            if csv_data:
                await query.message.reply_document(
                    document=csv_data.encode('utf-8') if isinstance(csv_data, str) else csv_data,
                    filename=f'leads_export_{datetime.now().strftime("%Y%m%d")}.csv',
                    caption="📥 Экспорт лидов"
                )
            else:
                await query.message.reply_text("Ошибка при экспорте данных")

        elif action == "admin_cleanup":
            # Меню очистки данных
            cleanup_message = (
                "🗑️ ОЧИСТКА ДАННЫХ\n\n"
                "⚠️ ВНИМАНИЕ: Данные будут удалены безвозвратно!\n\n"
                "Выберите что очистить:"
            )
            reply_markup = InlineKeyboardMarkup(ADMIN_CLEANUP_MENU)
            await query.message.edit_text(cleanup_message, reply_markup=reply_markup)

        elif action == "admin_panel":
            # Вернуться в главное меню админ-панели
            admin_panel_message = (
                "⚙️ АДМИН-ПАНЕЛЬ\n\n"
                "Выберите действие:"
            )
            reply_markup = InlineKeyboardMarkup(ADMIN_PANEL_MENU)
            await query.message.edit_text(admin_panel_message, reply_markup=reply_markup)

        elif action == "admin_close":
            # Закрыть админ-панель
            await query.message.edit_text("⚙️ Админ-панель закрыта")

    except Exception as e:
        logger.error(f"Error in handle_admin_panel_callback: {e}")
        await query.message.reply_text(f"Ошибка: {str(e)}")


async def handle_cleanup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик cleanup операций"""
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Проверка что это админ
    if user.id != config.ADMIN_TELEGRAM_ID:
        await query.message.reply_text("У вас нет доступа к этой функции")
        return

    action = query.data

    try:
        if action == "cleanup_conversations":
            # Очистка всех диалогов
            conn = database.db.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM conversations")
                conn.commit()
                count = cursor.rowcount

                await query.message.reply_text(f"✅ Удалено {count} сообщений из диалогов")
                logger.info(f"Admin {user.id} cleared {count} conversations")
            finally:
                conn.close()

        elif action == "cleanup_leads":
            # Очистка всех лидов
            conn = database.db.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM leads")
                conn.commit()
                count = cursor.rowcount

                await query.message.reply_text(f"✅ Удалено {count} лидов")
                logger.info(f"Admin {user.id} cleared {count} leads")
            finally:
                conn.close()

        elif action == "cleanup_logs":
            # Очистка логов
            import os
            if os.path.exists(config.LOG_FILE):
                # Создаем backup
                backup_file = f"{config.LOG_FILE}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.rename(config.LOG_FILE, backup_file)
                # Создаем новый пустой файл
                open(config.LOG_FILE, 'w').close()
                await query.message.reply_text(f"✅ Логи очищены\nBackup: {backup_file}")
                logger.info(f"Admin {user.id} cleared logs, backup: {backup_file}")
            else:
                await query.message.reply_text("Файл логов не найден")

        elif action == "cleanup_security":
            # Сброс счетчиков безопасности
            security.security_manager.message_timestamps.clear()
            security.security_manager.token_usage.clear()
            security.security_manager.cooldowns.clear()
            security.security_manager.suspicious_users.clear()
            security.security_manager.blacklist.clear()
            security.security_manager.total_tokens_today = 0
            security.security_manager.reset_stats_time()

            new_time = security.security_manager.stats_start_time.strftime("%d.%m.%Y %H:%M")
            await query.message.reply_text(f"✅ Счетчики безопасности сброшены\n📅 Статистика теперь с: {new_time}")
            logger.info(f"Admin {user.id} reset security counters")

        elif action == "cleanup_all":
            # Очистка всего
            conn = database.db.get_connection()
            cursor = conn.cursor()

            try:
                # Диалоги
                cursor.execute("DELETE FROM conversations")
                conv_count = cursor.rowcount

                # Лиды
                cursor.execute("DELETE FROM leads")
                leads_count = cursor.rowcount

                # Уведомления
                cursor.execute("DELETE FROM admin_notifications")
                notif_count = cursor.rowcount

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise
            finally:
                conn.close()

            # Логи
            import os
            if os.path.exists(config.LOG_FILE):
                backup_file = f"{config.LOG_FILE}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.rename(config.LOG_FILE, backup_file)
                open(config.LOG_FILE, 'w').close()

            # Безопасность
            security.security_manager.message_timestamps.clear()
            security.security_manager.token_usage.clear()
            security.security_manager.cooldowns.clear()
            security.security_manager.suspicious_users.clear()
            security.security_manager.blacklist.clear()
            security.security_manager.total_tokens_today = 0

            result_message = (
                "✅ ВСЕ ДАННЫЕ ОЧИЩЕНЫ\n\n"
                f"🗑️ Диалоги: {conv_count}\n"
                f"🗑️ Лиды: {leads_count}\n"
                f"🗑️ Уведомления: {notif_count}\n"
                f"🗑️ Логи: очищены (backup создан)\n"
                f"🗑️ Счетчики безопасности: сброшены"
            )

            await query.message.reply_text(result_message)
            logger.warning(f"Admin {user.id} cleared ALL data")

    except Exception as e:
        logger.error(f"Error in handle_cleanup_callback: {e}")
        await query.message.reply_text(f"Ошибка: {str(e)}")


async def notify_admin_new_lead(context, lead_id: int, lead_data: dict, user_data: dict):
    """Отправка уведомления админу о новом лиде (ОДИН РАЗ!)"""
    try:
        # Получаем информацию о лиде
        lead = database.db.get_lead_by_id(lead_id)
        if not lead:
            return

        # Проверяем было ли уже отправлено уведомление
        if lead.get('notification_sent'):
            logger.info(f"Lead {lead_id} notification already sent, skipping")
            return

        # Формируем сообщение для админа
        # ИСПРАВЛЕНИЕ: проверяем оба поля - 'temperature' и 'lead_temperature'
        temperature = lead.get('temperature') or lead_data.get('temperature') or lead_data.get('lead_temperature', 'cold')
        logger.info(f"Lead {lead_id} notification: temperature={temperature} (from lead_data: {lead_data.get('temperature') or lead_data.get('lead_temperature')})")
        
        temperature_emoji = {
            'hot': '🔥',
            'warm': '♨️',
            'cold': '❄️'
        }.get(temperature, '❓')

        # Получаем telegram username
        username = user_data.get('username')
        username_str = f"@{username}" if username else "нет"
        telegram_id = user_data.get('telegram_id') or user_data.get('id')

        notification_message = (
            f"{temperature_emoji} НОВЫЙ ЛИД!\n\n"
            f"👤 Имя: {lead.get('name') or 'Не указано'}\n"
            f"📱 Telegram: {username_str} (ID: {telegram_id})\n"
            f"🏢 Компания: {lead.get('company') or 'Не указана'}\n"
            f"📧 Email: {lead.get('email') or 'Не указан'}\n"
            f"📞 Телефон: {lead.get('phone') or 'Не указан'}\n\n"
        )
        
        # Добавляем СПЕЦИАЛИЗАЦИЮ (новое!)
        if lead.get('service_category') or lead.get('specific_need') or lead.get('industry'):
            notification_message += "🎯 Специализация:\n"
            
            if lead.get('service_category'):
                notification_message += f"• Направление: {lead.get('service_category')}\n"
            
            if lead.get('specific_need'):
                notification_message += f"• Потребность: {lead.get('specific_need')}\n"
            
            if lead.get('industry'):
                notification_message += f"• Отрасль: {lead.get('industry')}\n"
            
            notification_message += "\n"
        
        # Остальные детали - ТОЛЬКО ЕСЛИ ЕСТЬ ДАННЫЕ
        details = []
        if lead.get('team_size'):
            details.append(f"• Юристов: {lead.get('team_size')}")
        if lead.get('contracts_per_month'):
            details.append(f"• Договоров/мес: {lead.get('contracts_per_month')}")
        if lead.get('budget'):
            details.append(f"• Бюджет: {lead.get('budget')}")
        if lead.get('urgency'):
            urgency_emoji = {'high': '🔥', 'medium': '⏱️', 'low': '🐌'}.get(lead.get('urgency'), '')
            details.append(f"• Срочность: {urgency_emoji} {lead.get('urgency')}")
        
        if details:
            notification_message += "📊 Детали:\n" + "\n".join(details) + "\n\n"
        
        # Боль и температура
        if lead.get('pain_point'):
            notification_message += f"💭 Боль: {lead.get('pain_point')}\n\n"
        
        notification_message += f"🌡️ Температура: {temperature.upper()}"

        # Отправляем в Telegram
        # Если задан LEADS_CHAT_ID - отправляем в отдельный чат, иначе напрямую админу
        target_chat_id = config.LEADS_CHAT_ID if config.LEADS_CHAT_ID else config.ADMIN_TELEGRAM_ID

        await context.bot.send_message(
            chat_id=target_chat_id,
            text=notification_message
        )

        # Помечаем что уведомление отправлено
        database.db.mark_lead_notification_sent(lead_id)

        logger.info(f"Lead notification sent to chat {target_chat_id} for lead {lead_id}")

        # Отправляем на email (если настроен SMTP)
        if config.SMTP_USER and config.SMTP_PASSWORD:
            try:
                email_subject = f"[Legal AI Bot] Новый лид: {lead.get('name') or user_data.get('first_name')}"
                email_body = notification_message

                email_sender.email_sender.send_email(
                    to_email=config.SMTP_USER,  # Админу на почту
                    subject=email_subject,
                    body=email_body
                )

                logger.info(f"Email notification sent to admin about lead {lead_id}")
            except Exception as e:
                logger.error(f"Error sending email notification: {e}")

    except Exception as e:
        logger.error(f"Error in notify_admin_new_lead: {e}")


# === ERROR HANDLER ===

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")

    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Произошла непредвиденная ошибка. Попробуйте еще раз или свяжитесь с поддержкой."
        )



# ========================================
# BUSINESS HANDLERS
# ========================================

async def handle_business_connection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка подключения/отключения Business аккаунта"""
    try:
        if update.business_connection:
            connection = update.business_connection
            if connection.is_enabled:
                logger.info(f"✅ Business connection enabled: {connection.id} for user {connection.user_chat_id}")
                await context.bot.send_message(
                    chat_id=connection.user_chat_id,
                    text="✅ Бот успешно подключен к вашему Telegram Business аккаунту!\n\n"
                         "Теперь я буду автоматически отвечать на сообщения ваших клиентов."
                )
            else:
                logger.info(f"❌ Business connection disabled: {connection.id}")
    except Exception as e:
        logger.error(f"Error in handle_business_connection: {e}", exc_info=True)


async def handle_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений через Business аккаунт"""
    try:
        if not update.business_message:
            return
            
        message = update.business_message
        user_id = message.from_user.id
        text = message.text or ""
        
        logger.info(f"📨 Business message from {user_id}: {text}")
        
        # Получаем пользователя
        user = database.db.create_or_update_user(
            telegram_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        
        # Сохраняем сообщение пользователя
        database.db.add_message(user, 'user', text)
        
        # Получаем историю диалога
        conversation_history = database.db.get_conversation_history(user)

        # Получаем ответ от AI с постепенным streaming (как в GPT)
        full_response = ""
        sent_message = None
        chunk_buffer = ""
        last_update_length = 0
        last_update_time = 0

        # Показываем typing в начале
        try:
            await context.bot.send_chat_action(
                chat_id=message.chat.id,
                action="typing",
                business_connection_id=message.business_connection_id
            )
            logger.info(f"[Business] Typing indicator sent for user {user_id}")
        except Exception as e:
            logger.warning(f"[Business] Failed to send typing indicator: {e}")

        # Собираем ответ от OpenAI и постепенно обновляем сообщение
        start_generation = time.time()
        async for chunk in ai_brain.ai_brain.generate_response_stream(conversation_history):
            full_response += chunk
            chunk_buffer += chunk

            # Обновляем сообщение когда накопилось достаточно новых символов
            # ИЛИ прошло достаточно времени (для избежания rate limit)
            current_time = time.time()
            should_update = (
                (len(full_response) - last_update_length >= 150 and current_time - last_update_time >= 3.5) or  # Каждые 150 символов И минимум 3.5 сек (было 2)
                (len(chunk_buffer) > 300 and current_time - last_update_time >= 5.0)  # Или каждые 5 секунд при 300+ символах (было 3)
            )

            if should_update:
                if sent_message is None:
                    # Первая отправка - когда накопилось хотя бы 100 символов (снижаем частоту обновлений)
                    if len(full_response.strip()) >= 100:
                        try:
                            sent_message = await context.bot.send_message(
                                chat_id=message.chat.id,
                                text=full_response,
                                business_connection_id=message.business_connection_id
                            )
                            last_update_length = len(full_response)
                            last_update_time = current_time
                            chunk_buffer = ""
                            logger.debug(f"[Business] Initial message sent: {len(full_response)} chars")
                        except Exception as e:
                            logger.warning(f"[Business] Failed to send initial message: {e}")
                else:
                    # Обновляем существующее сообщение
                    try:
                        await context.bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=sent_message.message_id,
                            text=full_response,
                            business_connection_id=message.business_connection_id
                        )
                        last_update_length = len(full_response)
                        last_update_time = current_time
                        chunk_buffer = ""
                        logger.debug(f"[Business] Message updated: {len(full_response)} chars")
                    except Exception as e:
                        # Telegram rate limit - просто пропускаем это обновление
                        logger.debug(f"[Business] Skipped update (rate limit): {e}")
                        pass

        # Финальное обновление с полным текстом
        generation_time = time.time() - start_generation
        logger.info(f"[Business] Response generated in {generation_time:.2f}s ({len(full_response)} chars)")

        # Проверяем нужно ли разбить на части (лимит Telegram 4096 символов)
        if len(full_response) > 4096:
            logger.warning(f"[Business] Response too long ({len(full_response)} chars), splitting into parts")
            # Разбиваем на части
            parts = utils.split_long_message(full_response, max_length=4000)
            
            # Удаляем первое сообщение если оно было отправлено
            if sent_message:
                try:
                    await context.bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=sent_message.message_id
                    )
                except Exception:
                    pass
            
            # Отправляем по частям
            for i, part in enumerate(parts):
                part_msg = f"[Часть {i+1}/{len(parts)}]\n\n{part}" if len(parts) > 1 else part
                await context.bot.send_message(
                    chat_id=message.chat.id,
                    text=part_msg,
                    business_connection_id=message.business_connection_id
                )
                # Небольшая задержка между частями
                if i < len(parts) - 1:
                    await context.bot.send_chat_action(
                        chat_id=message.chat.id,
                        action="typing",
                        business_connection_id=message.business_connection_id
                    )
                    await asyncio.sleep(0.5)
        else:
            # Обычное обновление для коротких сообщений
            if sent_message:
                try:
                    await context.bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=sent_message.message_id,
                        text=full_response,
                        business_connection_id=message.business_connection_id
                    )
                    logger.debug("[Business] Final message update sent")
                except Exception:
                    pass
            else:
                # Если текст был слишком коротким для постепенного вывода
                await context.bot.send_message(
                    chat_id=message.chat.id,
                    text=full_response,
                    business_connection_id=message.business_connection_id
                )

        # Сохраняем ответ
        database.db.add_message(user, 'assistant', full_response)
        
        # Извлекаем и сохраняем лид данные (аналогично handle_message)
        if user_id != config.ADMIN_TELEGRAM_ID:
            lead_data = ai_brain.ai_brain.extract_lead_data(conversation_history)
            
            if lead_data:
                # Обрабатываем данные лида
                lead_id = lead_qualifier.lead_qualifier.process_lead_data(user, lead_data)
                
                if lead_id:
                    # Уведомляем админа о новом лиде
                    # ИСПРАВЛЕНИЕ: AI возвращает 'lead_temperature', приводим к 'temperature'
                    temperature = lead_data.get('temperature') or lead_data.get('lead_temperature', 'cold')
                    
                    should_notify = (
                        temperature in ['hot', 'warm'] or
                        (lead_data.get('name') and
                         (lead_data.get('email') or lead_data.get('phone')) and
                         lead_data.get('pain_point'))
                    )
                    
                    logger.info(f"[Business] Lead {lead_id}: temperature={temperature}, should_notify={should_notify}")
                    
                    if should_notify:
                        await notify_admin_new_lead(context, lead_id, lead_data, {"id": user, "telegram_id": user_id})
                
                # Проверяем нужно ли предложить lead magnet
                existing_lead = database.db.get_lead_by_user_id(user)
                lead_magnet_already_offered = existing_lead and existing_lead.get('lead_magnet_type') is not None
                
                if not lead_magnet_already_offered and ai_brain.ai_brain.should_offer_lead_magnet(lead_data):
                    # Формируем сообщение с lead magnet кнопками
                    lead_magnet_msg = "🎁 Чтобы помочь вам лучше, я подготовил специальные материалы:\n\n"
                    reply_markup = InlineKeyboardMarkup(LEAD_MAGNET_MENU)
                    await context.bot.send_message(
                        chat_id=message.chat.id,
                        text=lead_magnet_msg,
                        reply_markup=reply_markup,
                        business_connection_id=message.business_connection_id
                    )

        logger.info(f"✅ [Business] Response sent to user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in handle_business_message: {e}", exc_info=True)
        try:
            if update.business_message:
                await context.bot.send_message(
                    chat_id=update.business_message.chat.id,
                    text="❌ Произошла ошибка. Попробуйте позже.",
                    business_connection_id=update.business_message.business_connection_id
                )
        except:
            pass
