import telebot
import time
import os
from collections import defaultdict
from openai import OpenAI
from dotenv import load_dotenv
from tavily import TavilyClient
import sys
import os

# ПРИНУДИТЕЛЬНАЯ очистка от конфликтующих аргументов
import httpx
original_init = httpx.Client.__init__

def patched_init(self, *args, **kwargs):
    if 'proxies' in kwargs:
        del kwargs['proxies']  # Удаляем проблемный аргумент
    original_init(self, *args, **kwargs)

httpx.Client.__init__ = patched_init
httpx.AsyncClient.__init__ = patched_init

# Дальше твой обычный код
import telebot
from collections import defaultdict
from openai import OpenAI
from dotenv import load_dotenv
from tavily import TavilyClient
import time

# Загружаем ключи из .env
load_dotenv()

# ========== ТВОИ КЛЮЧИ ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # GitHub Personal Access Token
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Проверка ключей
if not TELEGRAM_TOKEN:
    print("❌ ОШИБКА: Нет TELEGRAM_TOKEN в .env файле!")
    exit(1)

if not GITHUB_TOKEN:
    print("❌ ОШИБКА: Нет GITHUB_TOKEN в .env файле!")
    print("Получи токен на https://github.com/settings/tokens")
    exit(1)

print("=" * 60)
print("🚀 ЗАПУСК УМНОГО БОТА НА GITHUB MODELS")
print("=" * 60)
print(f"📱 Telegram токен: {TELEGRAM_TOKEN[:10]}...")
print(f"🔑 GitHub токен: {GITHUB_TOKEN[:10]}...")
print(f"🌐 Tavily ключ: {TAVILY_API_KEY[:15]}..." if TAVILY_API_KEY else "🌐 Tavily: не используется")

# ========== ИНИЦИАЛИЗАЦИЯ GITHUB MODELS ==========
# GitHub Models использует OpenAI-совместимый API [citation:10]
client = OpenAI(
    base_url="https://models.github.ai/inference",  # Новый официальный эндпоинт [citation:8][citation:9]
    api_key=GITHUB_TOKEN,
)

# Telegram бот
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Tavily для поиска
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

# Проверка подключения к GitHub Models
print("🔄 Проверка подключения к GitHub Models...")
try:
    # Используем бесплатную модель для теста [citation:10]
    test_response = client.chat.completions.create(
        model="openai/gpt-4o-mini",  # Важно! Формат: "провайдер/модель" [citation:8]
        messages=[{"role": "user", "content": "Привет"}],
        max_tokens=10,
        temperature=0.7
    )
    print("✅ GitHub Models подключен успешно!")
    print("💰 Статус: ПОЛНОСТЬЮ БЕСПЛАТНО")
    print("🌍 Доступ: ИЗ ЛЮБОГО РЕГИОНА")
except Exception as e:
    print(f"❌ Ошибка подключения к GitHub Models: {e}")
    print("\n💡 Возможные причины:")
    print("   1. Неверный GitHub токен - проверь permissions (нужен доступ к Models)")
    print("   2. Токен просрочен - создай новый")
    print("   3. Нет интернета - проверь соединение")
    exit(1)

# Список доступных бесплатных моделей GitHub Models [citation:5][citation:10]
FREE_MODELS = {
    "gpt4o_mini": "openai/gpt-4o-mini",        # Быстрая, дешевая
    "gpt4o": "openai/gpt-4o",                   # Мощная
    "deepseek": "deepseek-ai/DeepSeek-R1",      # Отличный русский язык
    "llama": "meta-llama/Meta-Llama-3.1-8B-Instruct",  # Открытая модель
    "mistral": "mistralai/Mistral-Small-24B-Instruct-2501",  # Хороша для диалогов
}

# Текущая модель (по умолчанию)
current_model = FREE_MODELS["gpt4o_mini"]

# ========== ФУНКЦИИ ==========

def get_github_models_response(user_message, chat_id, model_name=None):
    """Получение ответа от GitHub Models с учётом истории"""
    try:
        # Выбираем модель
        model = model_name or current_model
        
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
        
        # Отправляем запрос к GitHub Models
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
            stream=False
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"❌ Ошибка GitHub Models: {e}")
        return f"😔 Извини, ошибка: {str(e)}"

def search_web(query):
    """Поиск в интернете через Tavily"""
    if not tavily:
        return "🔍 Поиск не доступен (нет API ключа Tavily)"
    
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

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@bot.message_handler(commands=['start'])
def start_command(message):
    """Приветственное сообщение"""
    welcome = (
        "👋 **Привет! Я умный бот на GitHub Models**\n\n"
        "🤖 **Что я умею:**\n"
        "• Отвечать на любые вопросы (GPT-4o, DeepSeek, Llama)\n"
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
        "• **Провайдер:** GitHub Models\n"
        f"• **Текущая модель:** {current_model}\n"
        "• **Доступ:** ИЗ ЛЮБОГО РЕГИОНА\n"
        "• **Стоимость:** ПОЛНОСТЬЮ БЕСПЛАТНО\n"
        "• **Поиск:** Tavily API\n"
        "• **Память:** 20 последних сообщений\n"
        "• **Приватность:** Данные не используются для обучения [citation:5]"
    )
    bot.reply_to(message, info_text, parse_mode="Markdown")

@bot.message_handler(commands=['model'])
def model_command(message):
    """Смена модели AI"""
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=1)
    
    for key, model in FREE_MODELS.items():
        # Красивое название для отображения
        display_name = {
            "gpt4o_mini": "🤖 GPT-4o Mini (быстрый)",
            "gpt4o": "🚀 GPT-4o (мощный)",
            "deepseek": "🧠 DeepSeek-R1 (русский)",
            "llama": "🦙 Llama 3.1 8B",
            "mistral": "🌪️ Mistral Small"
        }.get(key, model)
        
        btn = telebot.types.InlineKeyboardButton(
            f"{display_name}", 
            callback_data=f"model_{key}"
        )
        keyboard.add(btn)
    
    bot.send_message(
        message.chat.id,
        "🎯 **Выбери модель AI:**\n\n"
        "Все модели полностью бесплатны на GitHub Models!",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('model_'))
def model_callback(call):
    """Обработка выбора модели"""
    global current_model
    model_key = call.data.replace('model_', '')
    
    if model_key in FREE_MODELS:
        current_model = FREE_MODELS[model_key]
        
        # Красивое название
        display_names = {
            "gpt4o_mini": "GPT-4o Mini",
            "gpt4o": "GPT-4o",
            "deepseek": "DeepSeek-R1",
            "llama": "Llama 3.1",
            "mistral": "Mistral Small"
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
    print(f"📨 Чат: {chat_id} | От: {username}")
    print(f"📝 Вопрос: {user_text}")
    print(f"🤖 Модель: {current_model}")
    
    # Получаем ответ от GitHub Models
    response = get_github_models_response(user_text, chat_id)
    
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
    print("=" * 60)
    print("🚀 УМНЫЙ TELEGRAM БОТ УСПЕШНО ЗАПУЩЕН!")
    print("=" * 60)
    print(f"📱 Имя бота: @{bot.get_me().username}")
    print(f"🤖 Провайдер: GitHub Models")
    print(f"🌍 Доступ: ИЗ ЛЮБОГО РЕГИОНА")
    print(f"💰 Цена: ПОЛНОСТЬЮ БЕСПЛАТНО")
    print(f"📚 Память: {MAX_HISTORY} сообщений")
    print(f"🤖 Текущая модель: {current_model}")
    print("=" * 60)
    print("✅ Бот работает! Нажми Ctrl+C для остановки")
    print("📝 Логи сообщений будут появляться здесь:")
    print("-" * 60)
    
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")