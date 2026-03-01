import google.generativeai as genai
import os
from dotenv import load_dotenv

# Загружаем ключ из .env
load_dotenv()
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

print(f"🔑 Проверяем ключ: {GEMINI_KEY[:10]}...")

try:
    # Настраиваем Gemini
    genai.configure(api_key=GEMINI_KEY)
    
    # Пробуем получить список моделей
    models = genai.list_models()
    print("✅ Подключение к Gemini успешно!")
    print("📋 Доступные модели:")
    for model in models:
        if 'generateContent' in model.supported_generation_methods:
            print(f"  • {model.name}")
            
except Exception as e:
    print(f"❌ Ошибка: {e}")