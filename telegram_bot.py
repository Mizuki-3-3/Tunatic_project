import os
import logging
import sys
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler

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
    # Импорты ваших агентов
    from agents.data_collector import DataCollectorAgent
    from agents.data_analyzer import DataAnalyzerAgent
    from database.json_db import JSONDatabase
    
    logger.info("✅ All imports successful")
    
except ImportError as e:
    logger.error(f"❌ Import error: {e}")
    sys.exit(1)

class SimpleBusinessBot:
    def __init__(self):
        self.token = TOKEN
        self.db = JSONDatabase("data/database.json")
        self.user_sessions = {}
    
    async def start_command(self, update, context):
        """Начало диалога"""
        user_id = update.effective_user.id
        
        collector = DataCollectorAgent()
        first_question = collector.start_conversation()
        
        self.user_sessions[user_id] = {
            'collector': collector,
            'collected_data': None
        }
        
        await update.message.reply_text("🤖 *Бизнес-Консультант AI* - Давайте начнем!", parse_mode='Markdown')
        await update.message.reply_text(first_question)
        
        return 1
    
    async def handle_user_input(self, update, context):
        """Обработка ответов пользователя"""
        user_id = update.effective_user.id
        user_input = update.message.text
        
        if user_id not in self.user_sessions:
            await update.message.reply_text("Напишите /start чтобы начать")
            return 1
        
        session = self.user_sessions[user_id]
        collector = session['collector']
        
        try:
            next_question, collected_data = collector.process_user_input(user_input)
            
            if collected_data:
                # Данные собраны - анализируем
                await update.message.reply_text("✅ *Данные собраны! Анализирую...*", parse_mode='Markdown')
                
                analyzer = DataAnalyzerAgent(self.db)
                advice = analyzer.generate_advice(collected_data)
                
                response_text = f"🎯 *РЕКОМЕНДАЦИИ:*\n\n{advice}\n\n---\n💡 /start - новый анализ"
                await update.message.reply_text(response_text, parse_mode='Markdown')
                
                # Очистка сессии
                if user_id in self.user_sessions:
                    del self.user_sessions[user_id]
                
                return ConversationHandler.END
            else:
                await update.message.reply_text(next_question)
                return 1
                
        except Exception as e:
            logger.error(f"Ошибка обработки: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте /start")
            return ConversationHandler.END
    
    async def cancel_command(self, update, context):
        """Отмена диалога"""
        user_id = update.effective_user.id
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
        await update.message.reply_text("Диалог прерван. /start - начать заново")
        return ConversationHandler.END
    
    def run(self):
        """Запуск бота"""
        application = Application.builder().token(self.token).build()
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start_command)],
            states={
                1: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_user_input)]
            },
            fallbacks=[CommandHandler('cancel', self.cancel_command)]
        )
        
        application.add_handler(conv_handler)
        
        logger.info("🚀 Starting bot on Render...")
        application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    bot = SimpleBusinessBot()
    bot.run()
