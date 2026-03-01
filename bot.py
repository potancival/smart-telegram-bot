import telebot
import time
import os
from collections import defaultdict
from openai import OpenAI
from dotenv import load_dotenv
from tavily import TavilyClient
import sys
import pydantic

# Загружаем переменные окружения из .env файла
load_dotenv()

# ========== ПРОВЕРКА ВЕРСИЙ ==========
print(f"🐍 Python version: {sys.version}")
print(f"📦 Pydantic version: {pydantic.__version__}")
print("="*60)

# ========== ТВОИ КЛЮЧИ ИЗ .ENV ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Проверка наличия ключей
if not TELEGRAM_TOKEN:
    print("❌ ОШИБКА: Нет TELEGRAM_TOKEN в .env файле!")
    exit(1)

if not GITHUB_TOKEN:
    print("❌ ОШИБКА: Нет GITHUB_TOKEN в .env файле!")
    exit(1)

print("=" * 60)
print("🚀 ЗАПУСК УМНОГО БОТА НА GITHUB MODELS")
print("=" * 60)
print(f"📱 Telegram токен: {TELEGRAM_TOKEN[:10]}...")
print(f"🔑 GitHub токен: {GITHUB_TOKEN[:10]}...")
if TAVILY_API_KEY:
    print(f"🌐 Tavily ключ: {TAVILY_API_KEY[:15]}...")

# ========== ИНИЦИАЛИЗАЦИЯ GITHUB MODELS ==========
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=GITHUB_TOKEN,
)

# Telegram бот
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Tavily для поиска в интернете
tavily = None
if TAVILY_API_KEY:
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
        print("✅ Tavily подключен")
    except Exception as e:
        print(f"⚠️ Ошибка Tavily: {e}")

# Хранилище истории разговоров
conversation_history = defaultdict(list)
MAX_HISTORY = 20

# Очистка старых подключений Telegram
print("🔄 Очистка старых подключений...")
bot.remove_webhook()
time.sleep(1)

# Проверка подключения к GitHub Models
print("🔄 Проверка подключения к GitHub Models...")
try:
    test_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Привет"}],
        max_tokens=5
    )
    print("✅ GitHub Models подключен успешно!")
except Exception as e:
    print(f"❌ Ошибка подключения: {e}")
    print("⚠️ Бот продолжит работу, но AI может быть недоступен")

# Список доступных моделей
AVAILABLE_MODELS = {
    "gpt4o_mini": "gpt-4o-mini",
    "gpt4o": "gpt-4o",
}

current_model = AVAILABLE_MODELS["gpt4o_mini"]

# ========== ФУНКЦИИ ==========

def get_ai_response(user_message, chat_id):
    """Получение ответа от GitHub Models"""
    try:
        history = conversation_history[chat_id][-10:]
        
        messages = [
            {"role": "system", "content": "Ты дружелюбный ассистент в Telegram. Отвечай кратко и по делу."}
        ]
        
        for msg in history:
            messages.append({"role": msg['role'], "content": msg['content']})
        
        messages.append({"role": "user", "content": user_message})
        
        response = client.chat.completions.create(
            model=current_model,
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return f"😔 Извини, ошибка: {str(e)}"

def search_web(query):
    """Поиск в интернете через Tavily"""
    if not tavily:
        return "🔍 Поиск отключён"
    
    try:
        result = tavily.search(query=query, max_results=3, include_answer=True)
        response = f"🔍 **Результаты поиска:**\n\n"
        if result.get('answer'):
            response += f"📌 {result['answer']}\n\n"
        return response
    except Exception as e:
        return f"❌ Ошибка поиска: {e}"

def should_respond(message):
    """Проверяет, нужно ли отвечать на сообщение"""
    if message.chat.type == "private":
        return True
    bot_username = bot.get_me().username
    if message.text and f"@{bot_username}" in message.text:
        return True
    if message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id:
        return True
    return False

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@bot.message_handler(commands=['start'])
def start_command(message):
    welcome = (
        "👋 **Привет! Я умный бот на GitHub Models**\n\n"
        "📌 **Команды:**\n"
        "🔍 `/search запрос` - поиск в интернете\n"
        "🧹 `/clear` - очистить историю\n"
        f"💬 **В группах:** упоминай меня @{bot.get_me().username}"
    )
    bot.reply_to(message, welcome, parse_mode="Markdown")

@bot.message_handler(commands=['search'])
def search_command(message):
    query = message.text.replace('/search', '', 1).strip()
    if not query:
        bot.reply_to(message, "🔍 Напиши запрос")
        return
    status = bot.reply_to(message, f"🔎 Ищу: {query}...")
    result = search_web(query)
    bot.edit_message_text(result, message.chat.id, status.message_id, parse_mode="Markdown")

@bot.message_handler(commands=['clear'])
def clear_command(message):
    chat_id = message.chat.id
    conversation_history[chat_id] = []
    bot.reply_to(message, "🧹 История очищена!")

# ========== ОСНОВНОЙ ОБРАБОТЧИК ==========
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if not should_respond(message):
        return
    
    bot.send_chat_action(message.chat.id, 'typing')
    
    user_text = message.text
    chat_id = message.chat.id
    
    bot_username = bot.get_me().username
    if f"@{bot_username}" in user_text:
        user_text = user_text.replace(f"@{bot_username}", "").strip()
    
    print(f"\n📨 Вопрос: {user_text}")
    
    response = get_ai_response(user_text, chat_id)
    
    conversation_history[chat_id].append({"role": "user", "content": user_text})
    conversation_history[chat_id].append({"role": "assistant", "content": response})
    
    if len(conversation_history[chat_id]) > MAX_HISTORY:
        conversation_history[chat_id] = conversation_history[chat_id][-MAX_HISTORY:]
    
    bot.reply_to(message, response)
    print(f"💬 Ответ: {response[:100]}...")

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 БОТ ЗАПУЩЕН!")
    print("=" * 60)
    print(f"📱 Имя: @{bot.get_me().username}")
    print(f"📦 Pydantic: {pydantic.__version__} (совместимый режим)")
    print("=" * 60)
    
    bot.infinity_polling()