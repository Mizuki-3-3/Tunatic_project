import os
import logging
import sys
from telegram.ext import Application, CommandHandler, MessageHandler, filters

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

# Упрощенный бот для быстрого запуска
async def start(update, context):
    await update.message.reply_text(
        "🤖 *Бизнес-Консультант AI* запущен!\n\n"
        "Просто напишите вашу бизнес-идею одним сообщением, и я дам подробный анализ.",
        parse_mode='Markdown'
    )

async def handle_message(update, context):
    user_input = update.message.text
    
    await update.message.reply_text("🔄 Анализирую ваш запрос...")
    
    try:
        # Создаем минимальные данные для анализа
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
        
        # Отправляем результат
        response = f"🎯 *РЕКОМЕНДАЦИИ:*\n\n{advice}\n\n---\n💡 Новый запрос? Просто напишите следующую идею!"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка анализа: {e}")
        await update.message.reply_text("❌ Ошибка при анализе. Попробуйте еще раз.")

async def error_handler(update, context):
    """Обработчик ошибок"""
    logger.error(f"Ошибка в боте: {context.error}")

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    logger.info("🚀 Starting bot with python-telegram-bot 21.11.1 on Python 3.13...")
    
    # Запускаем бота
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=['message', 'callback_query']
    )

if __name__ == "__main__":
    main()
