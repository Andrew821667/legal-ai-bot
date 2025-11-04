"""
Admin Interface - админские функции и уведомления
"""
import logging
import csv
import io
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import database
import utils
import config

logger = logging.getLogger(__name__)


class AdminInterface:
    """Класс для админских функций"""

    def __init__(self, db: database.Database):
        self.db = db
        self.admin_id = config.ADMIN_TELEGRAM_ID

    def format_statistics(self, days: int = 30) -> str:
        """
        Форматирование статистики для вывода

        Args:
            days: Период в днях

        Returns:
            Отформатированная статистика
        """
        try:
            stats = self.db.get_statistics(days)

            # Получаем время начала учета статистики (первый пользователь)
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MIN(created_at) FROM users")
            first_user_time = cursor.fetchone()[0]
            conn.close()

            message = f"📊 СТАТИСТИКА БОТА\n\n"

            if first_user_time:
                from datetime import datetime
                stats_start = datetime.strptime(first_user_time, '%Y-%m-%d %H:%M:%S')
                message += f"📅 Статистика с: {stats_start.strftime('%d.%m.%Y %H:%M')}\n\n"

            message += f"Период: последние {days} дней\n\n"

            message += f"👥 Пользователи:\n"
            message += f"• Всего: {stats['total_users']}\n"
            message += f"• Новых за период: {stats['new_users']}\n\n"

            message += f"💬 Диалоги:\n"
            message += f"• Всего сообщений: {stats['total_messages']}\n"
            message += f"• Средняя длина диалога: {stats['avg_conversation_length']}\n\n"

            message += f"🎯 Лиды:\n"
            message += f"• Всего: {stats['total_leads']}\n"
            message += f"  🔥 Горячие: {stats['hot_leads']}\n"
            message += f"  ♨️ Теплые: {stats['warm_leads']}\n"
            message += f"  ❄️ Холодные: {stats['cold_leads']}\n\n"

            # Конверсия
            if stats['total_users'] > 0:
                conversion_rate = round((stats['total_leads'] / stats['total_users']) * 100, 1)
                message += f"📈 Конверсия:\n"
                message += f"• Посетитель → Лид: {conversion_rate}%\n\n"

            message += f"🎁 Lead Magnets:\n"
            message += f"• Консультаций: {stats['consultations']}\n"
            message += f"• Чек-листов: {stats['checklists']}\n"
            message += f"• Демо: {stats['demos']}\n"

            return message

        except Exception as e:
            logger.error(f"Error formatting statistics: {e}")
            return "Ошибка при получении статистики"

    def format_leads_list(self, temperature: Optional[str] = None,
                         status: Optional[str] = None, limit: int = 10) -> str:
        """
        Форматирование списка лидов

        Args:
            temperature: Фильтр по температуре
            status: Фильтр по статусу
            limit: Максимальное количество

        Returns:
            Отформатированный список лидов
        """
        try:
            leads = self.db.get_all_leads(temperature, status, limit)

            if not leads:
                return "Лидов не найдено"

            # Получаем время начала учета лидов (первый лид)
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MIN(created_at) FROM leads")
            first_lead_time = cursor.fetchone()[0]
            conn.close()

            message = f"📋 СПИСОК ЛИДОВ\n\n"

            if first_lead_time:
                from datetime import datetime
                leads_start = datetime.strptime(first_lead_time, '%Y-%m-%d %H:%M:%S')
                message += f"📅 Статистика с: {leads_start.strftime('%d.%m.%Y %H:%M')}\n\n"

            if temperature:
                temp_names = {'hot': 'Горячие', 'warm': 'Теплые', 'cold': 'Холодные'}
                message += f"Фильтр: {temp_names.get(temperature, temperature)}\n"

            if status:
                message += f"Статус: {status}\n"

            message += f"\nВсего найдено: {len(leads)}\n\n"

            for i, lead in enumerate(leads[:limit], 1):
                emoji = utils.get_lead_temperature_emoji(lead['temperature'])
                message += f"{i}. {emoji} "

                if lead.get('name'):
                    message += f"{lead['name']}"
                else:
                    message += "Без имени"

                if lead.get('company'):
                    message += f" ({lead['company']})"

                message += "\n"

                # Время создания лида
                if lead.get('created_at'):
                    from datetime import datetime
                    lead_time = datetime.strptime(lead['created_at'], '%Y-%m-%d %H:%M:%S')
                    message += f"   🕐 {lead_time.strftime('%d.%m.%Y %H:%M')}\n"

                if lead.get('email'):
                    message += f"   📧 {lead['email']}\n"

                if lead.get('budget'):
                    message += f"   💰 {lead['budget']}\n"

                if lead.get('pain_point'):
                    pain = utils.truncate_text(lead['pain_point'], 50)
                    message += f"   💭 {pain}\n"

                message += "\n"

            return message

        except Exception as e:
            logger.error(f"Error formatting leads list: {e}")
            return "Ошибка при получении списка лидов"

    def export_leads_to_csv(self) -> io.StringIO:
        """
        Экспорт лидов в CSV

        Returns:
            StringIO объект с CSV данными
        """
        try:
            leads = self.db.get_all_leads(limit=1000)

            # Создаем CSV в памяти
            output = io.StringIO()
            writer = csv.writer(output)

            # Заголовки
            headers = [
                'ID', 'Имя', 'Email', 'Телефон', 'Компания',
                'Команда', 'Договоров/мес', 'Боль', 'Бюджет',
                'Срочность', 'Отрасль', 'Температура', 'Статус',
                'Lead Magnet', 'Дата создания'
            ]
            writer.writerow(headers)

            # Данные
            for lead in leads:
                row = [
                    lead.get('id', ''),
                    lead.get('name', ''),
                    lead.get('email', ''),
                    lead.get('phone', ''),
                    lead.get('company', ''),
                    lead.get('team_size', ''),
                    lead.get('contracts_per_month', ''),
                    lead.get('pain_point', ''),
                    lead.get('budget', ''),
                    lead.get('urgency', ''),
                    lead.get('industry', ''),
                    lead.get('temperature', ''),
                    lead.get('status', ''),
                    lead.get('lead_magnet_type', ''),
                    lead.get('created_at', '')
                ]
                writer.writerow(row)

            output.seek(0)
            logger.info(f"Exported {len(leads)} leads to CSV")

            return output

        except Exception as e:
            logger.error(f"Error exporting leads to CSV: {e}")
            return None

    def send_admin_notification(self, bot, lead_id: int, notification_type: str,
                               additional_message: str = None):
        """
        Отправка уведомления админу

        Args:
            bot: Telegram bot instance
            lead_id: ID лида
            notification_type: Тип уведомления
            additional_message: Дополнительное сообщение
        """
        try:
            # Получаем данные лида
            lead = self.db.get_lead_by_user_id(lead_id)
            if not lead:
                logger.error(f"Lead {lead_id} not found")
                return

            # Получаем данные пользователя
            user = self.db.get_user_by_telegram_id(lead.get('telegram_id'))
            if not user:
                logger.error(f"User for lead {lead_id} not found")
                return

            # Формируем сообщение
            message = utils.format_lead_notification(lead, user)

            if additional_message:
                message += f"\n\n{additional_message}"

            # Создаем кнопки для быстрых действий
            keyboard = [
                [
                    InlineKeyboardButton("💬 Написать клиенту",
                                       callback_data=f"contact_user_{user['telegram_id']}"),
                    InlineKeyboardButton("📜 Посмотреть диалог",
                                       callback_data=f"view_conversation_{user['telegram_id']}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Отправляем уведомление
            bot.send_message(
                chat_id=self.admin_id,
                text=message,
                reply_markup=reply_markup
            )

            # Сохраняем уведомление в БД
            self.db.create_notification(lead_id, notification_type, message)

            logger.info(f"Admin notification sent for lead {lead_id}, type: {notification_type}")

        except Exception as e:
            logger.error(f"Error sending admin notification: {e}")

    def get_conversation_history_text(self, telegram_id: int, limit: int = 50) -> str:
        """
        Получение текстовой версии истории диалога

        Args:
            telegram_id: Telegram ID пользователя
            limit: Максимальное количество сообщений

        Returns:
            Отформатированная история диалога
        """
        try:
            # Получаем пользователя
            user = self.db.get_user_by_telegram_id(telegram_id)
            if not user:
                return "Пользователь не найден"

            # Получаем историю диалога
            history = self.db.get_conversation_history(user['id'], limit)

            if not history:
                return "История диалога пуста"

            message = f"💬 ИСТОРИЯ ДИАЛОГА\n\n"
            message += f"Пользователь: {user.get('first_name', 'Неизвестно')}"

            if user.get('username'):
                message += f" (@{user['username']})"

            message += f"\nВсего сообщений: {len(history)}\n\n"
            message += "─" * 30 + "\n\n"

            for msg in history:
                role_emoji = "👤" if msg['role'] == 'user' else "🤖"
                role_name = "Клиент" if msg['role'] == 'user' else "Бот"

                message += f"{role_emoji} {role_name}:\n"
                message += f"{msg['message']}\n\n"

            return message

        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return "Ошибка при получении истории диалога"


# Создание глобального экземпляра
admin_interface = AdminInterface(database.db)


if __name__ == '__main__':
    # Тестирование
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing AdminInterface...")

    # Тест форматирования статистики
    stats_message = admin_interface.format_statistics(30)
    print("\n=== Statistics ===")
    print(stats_message)

    # Тест списка лидов
    leads_message = admin_interface.format_leads_list()
    print("\n=== Leads List ===")
    print(leads_message)

    print("\nTest completed!")
