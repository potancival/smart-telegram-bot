#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import telebot
import time
import os
import sys
import random
import requests
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv
from tavily import TavilyClient
from rag_system import rag

# Загружаем переменные окружения
load_dotenv()

# ========== ПРОВЕРКА КЛЮЧЕЙ ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not TELEGRAM_TOKEN or not GITHUB_TOKEN:
    print("❌ Ошибка: Нет токенов в .env файле!")
    sys.exit(1)

# ========== НАСТРОЙКИ БОТА ==========
BOT_NAME = "Владос"
BOT_AGE = 67
BOT_PERSONALITY = (
    f"Меня зовут {BOT_NAME}, мне {BOT_AGE} лет. "
    "Я мудрый, слегка ворчливый, но добрый дед. "
    "Люблю помогать, но не терплю глупости."
)

# Настройки активности
CHAT_ACTIVITY = defaultdict(lambda: 30)
last_message_time = defaultdict(float)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = telebot.TeleBot(TELEGRAM_TOKEN)

tavily = None
if TAVILY_API_KEY:
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
        print("✅ Tavily подключен")
    except Exception as e:
        print(f"⚠️ Ошибка Tavily: {e}")

# GitHub Models
GITHUB_MODELS_URL = "https://models.inference.ai.azure.com/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Content-Type": "application/json"
}

conversation_history = defaultdict(list)
MAX_HISTORY = 20

bot.remove_webhook()
time.sleep(1)

print(f"✅ Бот {BOT_NAME} ({BOT_AGE} лет) готов к работе!")

# ========== ФУНКЦИИ ==========

def call_github_models(messages):
    """Вызов GitHub Models API"""
    try:
        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        response = requests.post(
            GITHUB_MODELS_URL,
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        
        response.raise_for_status()
        result = response.json()
        
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        return "😔 Не удалось получить ответ"
        
    except Exception as e:
        print(f"❌ Ошибка GitHub Models: {e}")
        return f"😔 Ошибка: {str(e)[:100]}"

def get_ai_response(user_message, chat_id, user_name="Пользователь"):
    """Получение ответа с учётом RAG"""
    try:
        current_date = datetime.now().strftime("%d.%m.%Y")
        chat_context = rag.get_chat_context(chat_id, hours=24)
        
        personality_prompt = (
            f"{BOT_PERSONALITY}\n"
            f"Сегодня {current_date}. Ты общаешься с {user_name}.\n"
        )
        
        if chat_context:
            personality_prompt += f"\nКонтекст недавнего разговора:\n{chat_context}\n"
        
        messages = [
            {"role": "system", "content": personality_prompt},
            {"role": "user", "content": user_message}
        ]
        
        response = call_github_models(messages)
        rag.add_conversation(chat_id, user_name, user_message, response)
        
        return response
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return f"😔 Извини, {user_name}, у меня что-то с памятью стало..."

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
    """Проверка, нужно ли отвечать"""
    if message.chat.type == "private":
        return True
    
    bot_username = bot.get_me().username
    
    if message.text and f"@{bot_username}" in message.text:
        return True
    
    if message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id:
        return True
    
    now = time.time()
    activity = CHAT_ACTIVITY[message.chat.id]
    
    if activity == 0:
        return False
    
    if message.chat.id in last_message_time:
        if now - last_message_time[message.chat.id] < 60:
            return False
    
    if random.randint(1, 100) <= activity:
        last_message_time[message.chat.id] = now
        return True
    
    return False

# ========== КОМАНДЫ ==========

@bot.message_handler(commands=['start'])
def start_command(message):
    welcome = (
        f"👴 **Привет! Я {BOT_NAME}, мне {BOT_AGE} лет.**\n\n"
        "📌 **Команды:**\n"
        "🔍 `/search запрос` - поиск в интернете\n"
        "📊 `/activ [0-100]` - установить активность\n"
        "📚 `/knowledge` - статистика базы знаний\n"
        "🧹 `/clear` - очистить историю\n\n"
        f"💬 Активность в чате: {CHAT_ACTIVITY[message.chat.id]}%"
    )
    bot.reply_to(message, welcome, parse_mode="Markdown")

@bot.message_handler(commands=['activ'])
def activity_command(message):
    chat_id = message.chat.id
    
    if message.chat.type != "private":
        user_status = bot.get_chat_member(chat_id, message.from_user.id).status
        if user_status not in ['administrator', 'creator']:
            bot.reply_to(message, "👴 Только админы могут менять мою активность!")
            return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, f"📊 Текущая активность: {CHAT_ACTIVITY[chat_id]}%\nИспользование: /activ число (0-100)")
            return
        
        new_activity = int(parts[1])
        if 0 <= new_activity <= 100:
            CHAT_ACTIVITY[chat_id] = new_activity
            bot.reply_to(message, f"✅ Активность изменена на {new_activity}%")
        else:
            bot.reply_to(message, "👴 Число должно быть от 0 до 100!")
    except ValueError:
        bot.reply_to(message, "👴 Напиши число, например: /activ 50")

@bot.message_handler(commands=['knowledge'])
def knowledge_command(message):
    stats = rag.get_stats()
    response = (
        "📚 **База знаний RAG:**\n\n"
        f"• Всего знаний: {stats['knowledge']}\n"
        f"• Сохранено диалогов: {stats['conversations']}\n"
        f"• Фактов о пользователях: {stats['user_facts']}\n\n"
        "Чем больше общаемся, тем умнее я становлюсь!"
    )
    bot.reply_to(message, response, parse_mode="Markdown")

@bot.message_handler(commands=['search'])
def search_command(message):
    query = message.text.replace('/search', '', 1).strip()
    if not query:
        bot.reply_to(message, "🔍 Напиши запрос после команды")
        return
    
    if not tavily:
        bot.reply_to(message, "❌ Поиск отключён (нет Tavily ключа)")
        return
    
    status = bot.reply_to(message, f"🔎 Ищу: {query}...")
    result = search_web(query)
    bot.edit_message_text(result, message.chat.id, status.message_id, parse_mode="Markdown")

@bot.message_handler(commands=['clear'])
def clear_command(message):
    conversation_history[message.chat.id] = []
    bot.reply_to(message, "🧹 История диалога очищена!")

# ========== ОСНОВНОЙ ОБРАБОТЧИК ==========
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    if not should_respond(message):
        return
    
    bot.send_chat_action(message.chat.id, 'typing')
    
    user_text = message.text
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "Пользователь"
    
    bot_username = bot.get_me().username
    if f"@{bot_username}" in user_text:
        user_text = user_text.replace(f"@{bot_username}", "").strip()
    
    print(f"\n📨 [{datetime.now().strftime('%H:%M:%S')}] {user_name}: {user_text}")
    
    response = get_ai_response(user_text, chat_id, user_name)
    
    conversation_history[chat_id].append({"role": "user", "content": user_text})
    conversation_history[chat_id].append({"role": "assistant", "content": response})
    
    if len(conversation_history[chat_id]) > MAX_HISTORY:
        conversation_history[chat_id] = conversation_history[chat_id][-MAX_HISTORY:]
    
    bot.reply_to(message, response)
    print(f"💬 {BOT_NAME}: {response[:100]}...")

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(f"🚀 БОТ {BOT_NAME.upper()} ЗАПУЩЕН НА RENDER!")
    print("=" * 60)
    print(f"👴 Имя: {BOT_NAME}, {BOT_AGE} лет")
    print(f"📱 Username: @{bot.get_me().username}")
    print(f"📚 RAG: активен (база: knowledge.db)")
    print("=" * 60)
    print("✅ Бот работает! Render будет держать его 24/7")
    print("-" * 60)
    
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")