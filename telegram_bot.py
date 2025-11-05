import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from dotenv import load_dotenv

# Импорты ваших агентов
from agents.data_collector import DataCollectorAgent
from agents.data_analyzer import DataAnalyzerAgent
from database.json_db import JSONDatabase

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

# Состояния диалога
COLLECTING_DATA = 1

# Flask app для Render
app = Flask(__name__)

class BusinessConsultantBot:
    def __init__(self, token):
        self.token = token
        self.db = JSONDatabase("data/database.json")
        self.user_sessions = {}
        self.application = None
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начинает новый диалог с пользователем."""
        user_id = update.effective_user.id
        
        collector = DataCollectorAgent()
        first_question = collector.start_conversation()
        
        self.user_sessions[user_id] = {
            'collector': collector,
            'collected_data': None
        }
        
        await update.message.reply_text(
            "🤖 *Бизнес-Консультант AI*\n\n"
            "Я помогу вам проанализировать бизнес-идею.\n\n"
            "*Давайте начнем!*",
            parse_mode='Markdown'
        )
        await update.message.reply_text(first_question)
        return COLLECTING_DATA
    
    async def handle_user_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обрабатывает ввод пользователя."""
        user_id = update.effective_user.id
        user_input = update.message.text
        
        if user_id not in self.user_sessions:
            await update.message.reply_text("Начните заново с /start")
            return ConversationHandler.END
        
        session = self.user_sessions[user_id]
        collector = session['collector']
        
        try:
            next_question, collected_data = collector.process_user_input(user_input)
            
            if collected_data:
                session['collected_data'] = collected_data
                await update.message.reply_text("✅ *Данные собраны! Анализирую...*", parse_mode='Markdown')
                
                await self._generate_business_advice(update, collected_data, user_id)
                del self.user_sessions[user_id]
                return ConversationHandler.END
            else:
                await update.message.reply_text(f"🤖 {next_question}")
                return COLLECTING_DATA
                
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await update.message.reply_text("❌ Ошибка. Начните заново - /start")
            return ConversationHandler.END
    
    async def _generate_business_advice(self, update: Update, user_data: dict, user_id: int):
        """Генерирует бизнес-рекомендации."""
        try:
            analyzer = DataAnalyzerAgent(self.db)
            await update.message.reply_chat_action(action="typing")
            
            advice = analyzer.generate_advice(user_data)
            
            response_text = f"""
🎯 *РЕКОМЕНДАЦИИ ДЛЯ ВАШЕГО БИЗНЕСА:*

{advice}

---
💡 */start* - новая консультация
            """
            
            # Отправляем частями если длинное сообщение
            if len(response_text) > 4096:
                parts = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
                for part in parts:
                    await update.message.reply_text(part, parse_mode='Markdown')
            else:
                await update.message.reply_text(response_text, parse_mode='Markdown')
            
            # Сохраняем в базу
            self.db.add_parsed_source({
                "type": "telegram_user_query",
                "user_id": user_id,
                "data": user_data,
                "response_preview": advice[:200] + "..."
            })
            
        except Exception as e:
            logger.error(f"Ошибка анализа: {e}")
            await update.message.reply_text("❌ Ошибка анализа. Попробуйте еще раз - /start")
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отменяет диалог."""
        user_id = update.effective_user.id
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
        await update.message.reply_text("❌ Диалог прерван. /start - начать заново")
        return ConversationHandler.END
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает справку."""
        help_text = """
📖 *Бизнес-Консультант AI*

/start - Начать консультацию
/help - Справка  
/cancel - Прервать диалог

*Как работает:*
1. Задаю вопросы по одному
2. Вы отвечаете последовательно
3. Анализирую данные
4. Даю рекомендации
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    def setup_handlers(self):
        """Настраивает обработчики для бота."""
        self.application = Application.builder().token(self.token).build()
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                COLLECTING_DATA: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_user_input)
                ],
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel),
                CommandHandler('help', self.help_command)
            ]
        )
        
        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler('help', self.help_command))
    
    async def process_update(self, update_data):
        """Обрабатывает обновление от Telegram."""
        update = Update.de_json(update_data, self.application.bot)
        await self.application.process_update(update)

# Глобальный экземпляр бота
bot = None

@app.route('/')
def home():
    return "🤖 Business Consultant Bot is running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook endpoint для Telegram."""
    if request.method == "POST":
        update = request.get_json()
        if bot and bot.application:
            # Обрабатываем асинхронно в отдельном потоке
            import asyncio
            asyncio.run(bot.process_update(update))
        return "OK"
    return "Method not allowed", 405

def main():
    """Запускает бота для Render."""
    global bot
    
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render предоставляет этот URL
    
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не найден")
        return
    
    # Инициализируем бота
    bot = BusinessConsultantBot(BOT_TOKEN)
    bot.setup_handlers()
    
    # Настраиваем webhook для Render
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"
        bot.application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", 5000)),
            url_path=BOT_TOKEN,
            webhook_url=webhook_url
        )
    else:
        # Локальный запуск с polling
        logger.info("Локальный запуск с polling...")
        bot.application.run_polling()

if __name__ == "__main__":
    main()
