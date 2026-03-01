import sys
import platform
import telebot
import time
import os
import json
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv
from tavily import TavilyClient
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ========== ПРОВЕРКА ВЕРСИИ PYTHON ==========
print(f"\n{'='*60}")
print(f"🐍 Python version: {sys.version}")
print(f"💻 Platform: {platform.platform()}")
print(f"📍 Expected: 3.11.x (для совместимости)")
print(f"{'='*60}\n")

# Предупреждение, если версия не 3.11
if sys.version_info[:2] != (3, 11):
    print("⚠️  ВНИМАНИЕ: Запуск на Python {}.{}".format(sys.version_info[0], sys.version_info[1]))
    print("   Рекомендуется Python 3.11 для максимальной совместимости\n")

# ========== ЗАГРУЗКА ПЕРЕМЕННЫХ ==========
load_dotenv()

# ========== ТВОИ КЛЮЧИ ИЗ .ENV ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Проверка наличия ключей
if not TELEGRAM_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Нет TELEGRAM_TOKEN в .env файле!")
    print("   Добавь строку: TELEGRAM_TOKEN=твой_токен")
    sys.exit(1)

if not GITHUB_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Нет GITHUB_TOKEN в .env файле!")
    print("   Добавь строку: GITHUB_TOKEN=github_pat_...")
    sys.exit(1)

print("=" * 60)
print("🚀 ЗАПУСК УМНОГО БОТА НА GITHUB MODELS")
print("=" * 60)
print(f"📱 Telegram токен: {TELEGRAM_TOKEN[:10]}...")
print(f"🔑 GitHub токен: {GITHUB_TOKEN[:10]}...")
if TAVILY_API_KEY:
    print(f"🌐 Tavily ключ: {TAVILY_API_KEY[:15]}...")
else:
    print("🌐 Tavily: не используется (поиск отключён)")

# ========== НАСТРОЙКА SESSION С ПОВТОРНЫМИ ПОПЫТКАМИ ==========
def create_requests_session():
    """Создаёт сессию с повторными попытками при ошибках"""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        backoff_factor=1
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# ========== ИНИЦИАЛИЗАЦИЯ ==========

# Telegram бот
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Tavily для поиска в интернете (если есть ключ)
tavily = None
if TAVILY_API_KEY:
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
        print("✅ Tavily подключен для поиска в интернете")
    except Exception as e:
        print(f"⚠️ Ошибка подключения Tavily: {e}")

# Хранилище истории разговоров
conversation_history = defaultdict(list)
MAX_HISTORY = 20

# Очистка старых подключений Telegram
print("🔄 Очистка старых подключений...")
bot.remove_webhook()
time.sleep(1)

# ========== НАСТРОЙКИ GITHUB MODELS ==========
GITHUB_MODELS_URL = "https://models.inference.ai.azure.com/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Content-Type": "application/json"
}

# Список доступных бесплатных моделей
AVAILABLE_MODELS = {
    "gpt4o_mini": "gpt-4o-mini",
    "gpt4o": "gpt-4o",
    "gpt4": "gpt-4",
    "gpt35": "gpt-3.5-turbo",
}

# Текущая модель (по умолчанию)
current_model = AVAILABLE_MODELS["gpt4o_mini"]

# ========== ФУНКЦИИ ==========

def call_github_models(messages, model=None, max_tokens=1000, temperature=0.7):
    """
    Прямой вызов GitHub Models API через requests
    (без использования OpenAI SDK, который вызывает проблемы с Pydantic)
    """
    try:
        model = model or current_model
        
        # Формируем запрос
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        # Создаём сессию с повторными попытками
        session = create_requests_session()
        
        # Отправляем запрос
        response = session.post(
            GITHUB_MODELS_URL,
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        
        # Проверяем ответ
        response.raise_for_status()
        
        # Парсим JSON
        result = response.json()
        
        # Извлекаем ответ
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        else:
            return "😔 Не удалось получить ответ от модели"
            
    except requests.exceptions.Timeout:
        return "⏱️ Превышено время ожидания ответа от GitHub Models"
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return "🔑 Ошибка авторизации: проверь GitHub токен"
        elif e.response.status_code == 429:
            return "⏳ Слишком много запросов. Попробуй позже"
        else:
            return f"🌐 Ошибка HTTP: {e}"
    except Exception as e:
        print(f"❌ Ошибка вызова GitHub Models: {e}")
        return f"😔 Извини, техническая ошибка: {str(e)[:100]}"

def get_ai_response(user_message, chat_id):
    """Получение ответа от GitHub Models с учётом истории"""
    try:
        # Получаем последние 10 сообщений из истории
        history = conversation_history[chat_id][-10:]
        
        # Формируем сообщения для API
        messages = [
            {"role": "system", "content": "Ты дружелюбный ассистент в Telegram. Отвечай кратко, по делу и используй эмодзи. Отвечай на том же языке, на котором задан вопрос."}
        ]
        
        # Добавляем историю разговора
        for msg in history:
            messages.append({"role": msg['role'], "content": msg['content']})
        
        # Добавляем текущее сообщение
        messages.append({"role": "user", "content": user_message})
        
        # Отправляем запрос напрямую через requests
        response_text = call_github_models(messages)
        
        return response_text
        
    except Exception as e:
        print(f"❌ Ошибка в get_ai_response: {e}")
        return f"😔 Извини, внутренняя ошибка: {str(e)[:100]}"

def search_web(query):
    """Поиск в интернете через Tavily"""
    if not tavily:
        return "🔍 Поиск в интернете отключён (нет API ключа Tavily)"
    
    try:
        print(f"🔍 Поиск в интернете: {query}")
        
        result = tavily.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_answer=True
        )
        
        response = f"🔍 **Результаты поиска:**\n\n"
        
        if result.get('answer'):
            response += f"📌 {result['answer']}\n\n"
        
        if result.get('results'):
            response += "📰 **Источники:**\n"
            for i, r in enumerate(result['results'][:3], 1):
                response += f"{i}. [{r['title']}]({r['url']})\n"
                if r.get('content'):
                    response += f"   _{r['content'][:100]}..._\n\n"
        
        return response
        
    except Exception as e:
        print(f"❌ Ошибка поиска: {e}")
        return f"❌ Ошибка при поиске: {e}"

def should_respond(message):
    """Проверяет, нужно ли отвечать на сообщение"""
    # В личных сообщениях отвечаем всегда
    if message.chat.type == "private":
        return True
    
    # В группах проверяем условия
    bot_username = bot.get_me().username
    
    # Если бота упомянули
    if message.text and f"@{bot_username}" in message.text:
        return True
    
    # Если это ответ на сообщение бота
    if message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id:
        return True
    
    return False

# ========== ПРОВЕРКА ПОДКЛЮЧЕНИЯ ==========
print("🔄 Проверка подключения к GitHub Models...")
try:
    test_messages = [
        {"role": "system", "content": "Ты ассистент"},
        {"role": "user", "content": "Привет, проверка связи"}
    ]
    test_response = call_github_models(test_messages, max_tokens=10)
    if test_response and not test_response.startswith("😔"):
        print("✅ GitHub Models подключен успешно!")
        print("💰 Статус: БЕСПЛАТНО")
        print("🌍 Доступ: ИЗ ЛЮБОГО РЕГИОНА")
    else:
        print(f"⚠️ GitHub Models ответил: {test_response}")
except Exception as e:
    print(f"⚠️ Предупреждение при проверке GitHub Models: {e}")
    print("   Бот продолжит работу, но AI может быть недоступен")

print("=" * 60)

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@bot.message_handler(commands=['start'])
def start_command(message):
    """Приветственное сообщение"""
    welcome = (
        "👋 **Привет! Я умный бот на GitHub Models**\n\n"
        "🤖 **Что я умею:**\n"
        "• Отвечать на любые вопросы (GPT-4o и другие модели)\n"
        "• Искать информацию в интернете\n"
        "• Помнить историю разговора\n"
        "• Работать в групповых чатах\n\n"
        "📌 **Команды:**\n"
        "🔍 `/search запрос` - поиск в интернете\n"
        "🔄 `/model` - сменить модель AI\n"
        "🧹 `/clear` - очистить историю\n"
        "ℹ️ `/info` - информация о боте\n\n"
        f"💬 **В группах:** упоминай меня @{bot.get_me().username}"
    )
    bot.reply_to(message, welcome, parse_mode="Markdown")

@bot.message_handler(commands=['info'])
def info_command(message):
    """Информация о боте"""
    info_text = (
        "ℹ️ **Информация о боте:**\n\n"
        "• **Провайдер:** GitHub Models (бесплатно)\n"
        f"• **Текущая модель:** {current_model}\n"
        "• **Доступ:** ИЗ ЛЮБОГО РЕГИОНА\n"
        "• **Поиск:** Tavily API\n"
        "• **Память:** 20 последних сообщений\n"
        f"• **Версия Python:** {sys.version_info.major}.{sys.version_info.minor}"
    )
    bot.reply_to(message, info_text, parse_mode="Markdown")

@bot.message_handler(commands=['model'])
def model_command(message):
    """Смена модели AI"""
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=1)
    
    for key, model in AVAILABLE_MODELS.items():
        # Красивое название для отображения
        display_name = {
            "gpt4o_mini": "🤖 GPT-4o Mini (быстрый, бесплатный)",
            "gpt4o": "🚀 GPT-4o (мощный)",
            "gpt4": "🧠 GPT-4 (классический)",
            "gpt35": "⚡ GPT-3.5 Turbo (очень быстрый)"
        }.get(key, model)
        
        btn = telebot.types.InlineKeyboardButton(
            f"{display_name}", 
            callback_data=f"model_{key}"
        )
        keyboard.add(btn)
    
    bot.send_message(
        message.chat.id,
        "🎯 **Выбери модель AI:**\n\n"
        "Все модели бесплатны в GitHub Models!",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('model_'))
def model_callback(call):
    """Обработка выбора модели"""
    global current_model
    model_key = call.data.replace('model_', '')
    
    if model_key in AVAILABLE_MODELS:
        current_model = AVAILABLE_MODELS[model_key]
        
        # Красивое название
        display_names = {
            "gpt4o_mini": "GPT-4o Mini",
            "gpt4o": "GPT-4o",
            "gpt4": "GPT-4",
            "gpt35": "GPT-3.5 Turbo"
        }
        
        bot.edit_message_text(
            f"✅ Модель изменена на: **{display_names.get(model_key, model_key)}**\n\nТеперь я буду использовать эту модель для ответов.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        
        bot.answer_callback_query(call.id, f"Модель изменена")
    else:
        bot.answer_callback_query(call.id, "Неизвестная модель")

@bot.message_handler(commands=['search'])
def search_command(message):
    """Поиск в интернете"""
    # Получаем текст запроса
    query = message.text.replace('/search', '', 1).strip()
    
    if not query:
        bot.reply_to(message, "🔍 Напиши запрос после команды, например: /search погода в Москве")
        return
    
    if not tavily:
        bot.reply_to(message, "❌ Поиск не доступен: нет API ключа Tavily в .env файле")
        return
    
    # Отправляем сообщение, что ищем
    status_msg = bot.reply_to(message, f"🔎 Ищу в интернете: _{query}_...", parse_mode="Markdown")
    
    # Выполняем поиск
    result = search_web(query)
    
    try:
        # Обновляем сообщение с результатами
        bot.edit_message_text(
            result,
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        # Если ошибка, отправляем новым сообщением
        bot.reply_to(message, result, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=['clear'])
def clear_command(message):
    """Очистка истории"""
    chat_id = message.chat.id
    conversation_history[chat_id] = []
    bot.reply_to(message, "🧹 История диалога очищена!")

# ========== ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ==========
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    """Обрабатывает все текстовые сообщения"""
    
    # Проверяем, нужно ли отвечать
    if not should_respond(message):
        return
    
    # Показываем статус "печатает"
    bot.send_chat_action(message.chat.id, 'typing')
    
    # Получаем текст сообщения
    user_text = message.text
    chat_id = message.chat.id
    username = message.from_user.first_name or "Пользователь"
    
    # Убираем упоминание бота из текста
    bot_username = bot.get_me().username
    if f"@{bot_username}" in user_text:
        user_text = user_text.replace(f"@{bot_username}", "").strip()
    
    # Логируем в консоль
    print(f"\n{'='*50}")
    print(f"📨 [{datetime.now().strftime('%H:%M:%S')}] Чат: {chat_id} | От: {username}")
    print(f"📝 Вопрос: {user_text}")
    print(f"🤖 Модель: {current_model}")
    
    # Получаем ответ от AI
    response = get_ai_response(user_text, chat_id)
    
    # Сохраняем в историю
    conversation_history[chat_id].append({"role": "user", "content": user_text})
    conversation_history[chat_id].append({"role": "assistant", "content": response})
    
    # Ограничиваем длину истории
    if len(conversation_history[chat_id]) > MAX_HISTORY:
        conversation_history[chat_id] = conversation_history[chat_id][-MAX_HISTORY:]
    
    # Отправляем ответ
    try:
        bot.reply_to(message, response)
        print(f"💬 Ответ: {response[:100]}...")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        bot.reply_to(message, "😔 Произошла ошибка при отправке ответа")

# ========== ЗАПУСК БОТА ==========
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🚀 УМНЫЙ TELEGRAM БОТ УСПЕШНО ЗАПУЩЕН!")
    print("=" * 60)
    print(f"📱 Имя бота: @{bot.get_me().username}")
    print(f"🤖 Провайдер: GitHub Models (прямые HTTP запросы)")
    print(f"🌍 Доступ: ИЗ ЛЮБОГО РЕГИОНА")
    print(f"💰 Цена: ПОЛНОСТЬЮ БЕСПЛАТНО")
    print(f"📚 Память: {MAX_HISTORY} сообщений")
    print(f"🤖 Модель по умолчанию: {current_model}")
    print("=" * 60)
    print("✅ Бот работает! Нажми Ctrl+C для остановки")
    print("📝 Логи сообщений будут появляться здесь:")
    print("-" * 60)
    
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        print("🔧 Перезапусти бота командой: python bot.py")