import os
import logging
import sys
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Проверка переменных
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN not found!")
    sys.exit(1)

logger.info("✅ Environment variables loaded")

try:
    from agents.data_collector import DataCollectorAgent
    from agents.data_analyzer import DataAnalyzerAgent
    from database.json_db import JSONDatabase
    logger.info("✅ All imports successful")
except ImportError as e:
    logger.error(f"❌ Import error: {e}")
    sys.exit(1)

# Упрощенный бот
def start(update, context):
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🤖 *Бизнес-Консультант AI* запущен! Напишите вашу бизнес-идею.",
        parse_mode='Markdown'
    )

def handle_message(update, context):
    user_input = update.message.text
    
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🔄 Анализирую ваш запрос..."
    )
    
    try:
        # Создаем минимальные данные
        user_data = {
            "industry": "auto",
            "idea": user_input,
            "city": "auto", 
            "budget": "auto",
            "experience": "auto",
            "target_audience": "auto",
            "special_requirements": "auto"
        }
        
        # Анализируем
        db = JSONDatabase("data/database.json")
        analyzer = DataAnalyzerAgent(db)
        advice = analyzer.generate_advice(user_data)
        
        response = f"🎯 *РЕКОМЕНДАЦИИ:*\n\n{advice}\n\n---\n💡 Новый запрос? Просто напишите!"
        
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=response,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка анализа: {e}")
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Ошибка при анализе. Попробуйте еще раз."
        )

def main():
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    logger.info("🚀 Starting bot on Render with python-telegram-bot 13.15...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
