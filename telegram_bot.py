import os
import logging
import sys
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from telegram import Update

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Состояния диалога
COLLECTING_DATA = 1

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

class InteractiveBusinessBot:
    def __init__(self):
        self.user_sessions = {}
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало диалога - команда /start"""
        user_id = update.effective_user.id
        
        # Создаем нового сборщика данных для пользователя
        collector = DataCollectorAgent()
        first_question = collector.start_conversation()
        
        # Сохраняем сессию пользователя
        self.user_sessions[user_id] = {
            'collector': collector,
            'collected_data': None
        }
        
        welcome_text = """
🤖 *Бизнес-Консультант AI*

Я помогу вам проанализировать бизнес-идею. Будем собирать информацию по шагам.

*Давайте начнем!*
        """
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
        await update.message.reply_text(first_question)
        
        return COLLECTING_DATA
    
    async def handle_user_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ответов пользователя в диалоге"""
        user_id = update.effective_user.id
        user_input = update.message.text
        
        # Проверяем активную сессию
        if user_id not in self.user_sessions:
            await update.message.reply_text("Напишите /start чтобы начать консультацию")
            return ConversationHandler.END
        
        session = self.user_sessions[user_id]
        collector = session['collector']
        
        try:
            # Обрабатываем ввод пользователя
            next_question, collected_data = collector.process_user_input(user_input)
            
            if collected_data:
                # Данные собраны, переходим к анализу
                session['collected_data'] = collected_data
                
                await update.message.reply_text(
                    "✅ *Данные собраны! Анализирую вашу бизнес-идею...*\n"
                    "⏳ Это займет 1-2 минуты",
                    parse_mode='Markdown'
                )
                
                # Запускаем анализ
                await self._generate_analysis(update, collected_data, user_id)
                
                # Завершаем диалог
                if user_id in self.user_sessions:
                    del self.user_sessions[user_id]
                
                return ConversationHandler.END
                
            else:
                # Задаем следующий вопрос
                await update.message.reply_text(next_question)
                return COLLECTING_DATA
                
        except Exception as e:
            logger.error(f"Ошибка обработки ввода: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка. Давайте попробуем еще раз - /start"
            )
            return ConversationHandler.END
    
    async def _generate_analysis(self, update: Update, user_data: dict, user_id: int):
        """Генерация анализа и рекомендаций"""
        try:
            # Создаем анализатор
            analyzer = DataAnalyzerAgent(JSONDatabase("data/database.json"))
            
            # Показываем действие "печатает"
            await update.message.reply_chat_action(action="typing")
            
            # Генерируем рекомендации
            advice = analyzer.generate_advice(user_data)
            
            # Форматируем ответ
            response_text = f"""
🎯 *РЕКОМЕНДАЦИИ ДЛЯ ВАШЕГО БИЗНЕСА*

{advice}

---
💡 *Хотите проанализировать другую идею?* Напишите /start
            """
            
            # Отправляем результат
            if len(response_text) > 4096:
                parts = [response_text[i:i+4096] for i in range(0, len(response_text), 4096)]
                for part in parts:
                    await update.message.reply_text(part, parse_mode='Markdown')
            else:
                await update.message.reply_text(response_text, parse_mode='Markdown')
            
            logger.info(f"✅ Анализ завершен для пользователя {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка генерации анализа: {e}")
            await update.message.reply_text("❌ Ошибка при анализе данных. Попробуйте еще раз - /start")
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена диалога"""
        user_id = update.effective_user.id
        
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
        
        await update.message.reply_text("Диалог прерван. /start - начать заново")
        return ConversationHandler.END
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда помощи"""
        help_text = """
📖 *Помощь по боту:*
/start - Начать консультацию
/help - Эта справка  
/cancel - Прервать диалог
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        # Игнорируем ошибки связанные с proxies
        if "proxies" in str(context.error):
            logger.warning("⚠️  Ignored proxies error (not supported in this version)")
            return
        logger.error(f"Ошибка в боте: {context.error}")
    
    def run(self):
        """Запуск бота БЕЗ proxies"""
        try:
            # ВАЖНО: создаем Application БЕЗ параметра proxies
            application = Application.builder().token(TOKEN).build()
            
            # ConversationHandler для диалога
            conv_handler = ConversationHandler(
                entry_points=[CommandHandler('start', self.start_command)],
                states={
                    COLLECTING_DATA: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_user_input)
                    ],
                },
                fallbacks=[CommandHandler('cancel', self.cancel_command)]
            )
            
            application.add_handler(conv_handler)
            application.add_handler(CommandHandler('help', self.help_command))
            application.add_error_handler(self.error_handler)
            
            logger.info("🚀 Запускаем бота с интерактивным диалогом...")
            application.run_polling(drop_pending_updates=True)
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка запуска: {e}")

def main():
    bot = InteractiveBusinessBot()
    bot.run()

if __name__ == "__main__":
    main()
