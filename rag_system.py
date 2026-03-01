# rag_system.py
import sqlite3
import json
import hashlib
from datetime import datetime
from collections import defaultdict

class RAGSystem:
    """Retrieval-Augmented Generation система для обучения на разговорах"""
    
    def __init__(self, db_path="knowledge.db"):
        self.db_path = db_path
        self.init_database()
        
    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица для фактов и знаний
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                topic TEXT,
                content TEXT,
                embedding TEXT,
                timestamp DATETIME,
                source TEXT,
                importance INTEGER DEFAULT 1
            )
        ''')
        
        # Таблица для истории диалогов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                user_id TEXT,
                user_message TEXT,
                bot_response TEXT,
                timestamp DATETIME,
                topic TEXT
            )
        ''')
        
        # Таблица для фактов о пользователях
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                user_id TEXT,
                user_name TEXT,
                fact TEXT,
                timestamp DATETIME
            )
        ''')
        
        conn.commit()
        conn.close()
        print("📚 RAG система инициализирована")
    
    def add_conversation(self, chat_id, user_id, user_message, bot_response, topic="general"):
        """Добавление диалога в историю"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO conversations (chat_id, user_id, user_message, bot_response, timestamp, topic)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (str(chat_id), str(user_id), user_message, bot_response, datetime.now(), topic))
        
        conn.commit()
        conn.close()
    
    def search_knowledge(self, query, chat_id=None, limit=5):
        """Поиск релевантных знаний по запросу"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Простой поиск по ключевым словам
        words = query.lower().split()
        conditions = " OR ".join([f"content LIKE ?" for _ in words])
        params = [f"%{word}%" for word in words]
        
        sql = f"SELECT content, importance FROM knowledge WHERE {conditions}"
        
        if chat_id:
            sql += " AND chat_id = ?"
            params.append(str(chat_id))
        
        sql += " ORDER BY importance DESC, timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(sql, params)
        results = cursor.fetchall()
        
        conn.close()
        
        return [r[0] for r in results]
    
    def get_chat_context(self, chat_id, hours=24):
        """Получение контекста чата за последние N часов"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_message, bot_response FROM conversations 
            WHERE chat_id = ? AND timestamp > datetime('now', ?)
            ORDER BY timestamp DESC LIMIT 10
        ''', (str(chat_id), f'-{hours} hours'))
        
        results = cursor.fetchall()
        conn.close()
        
        context = []
        for user_msg, bot_msg in results:
            context.append(f"Пользователь: {user_msg}")
            context.append(f"Владос: {bot_msg}")
        
        return "\n".join(context[-6:])  # Последние 3 диалога
    
    def get_stats(self):
        """Статистика базы знаний"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        cursor.execute("SELECT COUNT(*) FROM knowledge")
        stats['knowledge'] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM conversations")
        stats['conversations'] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM user_facts")
        stats['user_facts'] = cursor.fetchone()[0]
        
        conn.close()
        return stats

# Создаём глобальный экземпляр
rag = RAGSystem()