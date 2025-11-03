"""
AI Brain - интеграция с OpenAI GPT
"""
import logging
from typing import List, Dict, Optional, AsyncGenerator
import json
from openai import OpenAI
import config
import prompts

logger = logging.getLogger(__name__)


class AIBrain:
    """Класс для работы с OpenAI API"""

    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.OPENAI_MODEL
        self.max_tokens = config.MAX_TOKENS
        self.temperature = config.TEMPERATURE

    async def generate_response_stream(self, conversation_history: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        """
        Генерация ответа с потоковой передачей (streaming) от OpenAI

        Args:
            conversation_history: История диалога в формате [{"role": "user"/"assistant", "message": "..."}]

        Yields:
            Части ответа ассистента по мере их генерации
        """
        try:
            # Преобразуем историю в формат OpenAI
            messages = [{"role": "system", "content": prompts.SYSTEM_PROMPT}]

            for msg in conversation_history:
                messages.append({
                    "role": msg["role"],
                    "content": msg["message"]
                })

            logger.debug(f"Sending streaming request to OpenAI with {len(messages)} messages")

            # Запрос к OpenAI с включенным streaming
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True  # Включаем потоковую передачу!
            )

            # Отдаем части ответа по мере их поступления
            for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

            logger.info("Streaming response completed")

        except Exception as e:
            logger.error(f"Error generating streaming response: {e}")
            yield "Извините, произошла ошибка при обработке вашего запроса. Попробуйте еще раз или свяжитесь с нашей командой напрямую."

    def generate_response(self, conversation_history: List[Dict[str, str]]) -> str:
        """
        Генерация ответа на основе истории диалога

        Args:
            conversation_history: История диалога в формате [{"role": "user"/"assistant", "message": "..."}]

        Returns:
            Ответ ассистента
        """
        try:
            # Преобразуем историю в формат OpenAI
            messages = [{"role": "system", "content": prompts.SYSTEM_PROMPT}]

            for msg in conversation_history:
                messages.append({
                    "role": msg["role"],
                    "content": msg["message"]
                })

            logger.debug(f"Sending request to OpenAI with {len(messages)} messages")

            # Запрос к OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

            assistant_message = response.choices[0].message.content
            logger.info(f"Received response from OpenAI: {len(assistant_message)} chars")

            return assistant_message

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "Извините, произошла ошибка при обработке вашего запроса. Попробуйте еще раз или свяжитесь с Андреем напрямую."

    def extract_lead_data(self, conversation_history: List[Dict[str, str]]) -> Optional[Dict]:
        """
        Извлечение данных лида из истории диалога

        Args:
            conversation_history: История диалога

        Returns:
            Словарь с данными лида или None в случае ошибки
        """
        try:
            # Формируем контекст диалога
            conversation_text = "\n".join([
                f"{msg['role']}: {msg['message']}"
                for msg in conversation_history
            ])

            messages = [
                {"role": "system", "content": prompts.EXTRACT_DATA_PROMPT},
                {"role": "user", "content": f"Диалог:\n{conversation_text}"}
            ]

            logger.debug("Extracting lead data from conversation")

            # Запрос к OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=500,
                temperature=0.3  # Низкая температура для более точного извлечения
            )

            response_text = response.choices[0].message.content
            logger.debug(f"Received extraction response: {response_text[:100]}")

            # Парсим JSON ответ
            # Убираем возможные markdown блоки
            response_text = response_text.strip()
            if response_text.startswith("```"):
                # Убираем markdown обертку
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            lead_data = json.loads(response_text)
            logger.info(f"Successfully extracted lead data: temperature={lead_data.get('lead_temperature')}")

            return lead_data

        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}, response: {response_text}")
            return None
        except Exception as e:
            logger.error(f"Error extracting lead data: {e}")
            return None

    def check_handoff_trigger(self, user_message: str) -> bool:
        """
        Проверка триггеров передачи админу

        Args:
            user_message: Сообщение пользователя

        Returns:
            True если нужно передать админу
        """
        message_lower = user_message.lower()

        for trigger in prompts.HANDOFF_TRIGGERS:
            if trigger.lower() in message_lower:
                logger.info(f"Handoff trigger detected: {trigger}")
                return True

        return False

    def should_offer_lead_magnet(self, lead_data: Optional[Dict]) -> bool:
        """
        Определение нужно ли предложить lead magnet

        Args:
            lead_data: Данные лида

        Returns:
            True если нужно предложить lead magnet
        """
        if not lead_data:
            return False

        # Предлагаем lead magnet если:
        # 1. Есть боль
        # 2. Есть хотя бы один контакт (email или phone) ИЛИ
        # 3. Лид теплый или горячий

        has_pain = lead_data.get('pain_point') and len(lead_data.get('pain_point', '')) > 10
        has_contact = lead_data.get('email') or lead_data.get('phone')
        temperature = lead_data.get('lead_temperature', 'cold')

        should_offer = has_pain and (has_contact or temperature in ['warm', 'hot'])

        logger.debug(f"Should offer lead magnet: {should_offer} (pain={has_pain}, contact={has_contact}, temp={temperature})")

        return should_offer


# Создание глобального экземпляра
ai_brain = AIBrain()


if __name__ == '__main__':
    # Тестирование
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing AIBrain...")

    # Тест генерации ответа
    test_conversation = [
        {"role": "user", "message": "Здравствуйте, интересует автоматизация договоров"}
    ]

    response = ai_brain.generate_response(test_conversation)
    print(f"\nResponse: {response[:200]}...")

    # Тест извлечения данных
    test_conversation_full = [
        {"role": "user", "message": "Здравствуйте, интересует автоматизация договоров"},
        {"role": "assistant", "message": "Здравствуйте! Расскажите подробнее о вашей команде"},
        {"role": "user", "message": "У нас 5 юристов, около 50 договоров в месяц"},
        {"role": "assistant", "message": "Понятно. Какая основная проблема?"},
        {"role": "user", "message": "Не успеваем проверять все, иногда пропускаем важные моменты. Бюджет до 500 тысяч. Мой email: ivan@company.ru"}
    ]

    lead_data = ai_brain.extract_lead_data(test_conversation_full)
    print(f"\nExtracted lead data: {json.dumps(lead_data, indent=2, ensure_ascii=False)}")
