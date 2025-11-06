import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app для Render
app = Flask(__name__)

# Глобальные переменные
application = None
USER_SESSIONS = {}

# Состояния диалога
COLLECTING_DATA = 1

@app.route('/')
def home():
    return "🤖 Business Consultant Bot is running on Render!"

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Webhook endpoint для Telegram"""
    if request.method == "POST":
        if application:
            update = Update.de_json(request.get_json(), application.bot)
            await application.process_update(update)
        return "OK"
    return "Method not allowed", 405

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает новый диалог с пользователем."""
    user_id = update.effective_user.id
    
    try:
        from agents.data_collector import DataCollectorAgent
        
        collector = DataCollectorAgent()
        first_question = collector.start_conversation()
        
        USER_SESSIONS[user_id] = {
            'collector': collector,
            'collected_data': None
        }
        
        await update.message.reply_text(
            "🤖 *Бизнес-Консультант AI*\n\nДавайте начнем сбор информации!",
            parse_mode='Markdown'
        )
        await update.message.reply_text(first_question)
        return COLLECTING_DATA
        
    except Exception as e:
        logger.error(f"Start error: {e}")
        await update.message.reply_text("❌ Ошибка инициализации. Попробуйте позже.")
        return ConversationHandler.END

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод пользователя."""
    user_id = update.effective_user.id
    user_input = update.message.text
    
    if user_id not in USER_SESSIONS:
        await update.message.reply_text("Начните с /start")
        return ConversationHandler.END
    
    session = USER_SESSIONS[user_id]
    collector = session['collector']
    
    try:
        next_question, collected_data = collector.process_user_input(user_input)
        
        if collected_data:
            session['collected_data'] = collected_data
            await update.message.reply_text("✅ *Данные собраны! Анализирую...*", parse_mode='Markdown')
            
            # Анализ данных
            from agents.data_analyzer import DataAnalyzerAgent
            from database.json_db import JSONDatabase
            
            db = JSONDatabase()
            analyzer = DataAnalyzerAgent(db)
            advice = analyzer.generate_advice(collected_data)
            
            response_text = f"🎯 *РЕКОМЕНДАЦИИ:*\n\n{advice}\n\n---\n💡 /start - новая консультация"
            
            # Разбиваем длинные сообщения
            if len(response_text) > 4096:
                parts = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
                for part in parts:
                    await update.message.reply_text(part, parse_mode='Markdown')
            else:
                await update.message.reply_text(response_text, parse_mode='Markdown')
            
            # Сохраняем в базу
            db.add_parsed_source({
                "type": "telegram_query",
                "user_id": user_id,
                "data": collected_data,
                "response_preview": advice[:200] + "..."
            })
            
            del USER_SESSIONS[user_id]
            return ConversationHandler.END
        else:
            await update.message.reply_text(next_question)
            return COLLECTING_DATA
            
    except Exception as e:
        logger.error(f"Input handling error: {e}")
        await update.message.reply_text("❌ Ошибка обработки. /start - начать заново")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет диалог."""
    user_id = update.effective_user.id
    if user_id in USER_SESSIONS:
        del USER_SESSIONS[user_id]
    await update.message.reply_text("❌ Диалог прерван. /start - начать заново")
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает справку."""
    help_text = """
📖 *Бизнес-Консультант AI*

/start - Начать консультацию
/help - Справка  
/cancel - Прервать диалог
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ошибки."""
    logger.error(f"Update {update} caused error {context.error}")

def setup_bot():
    """Настраивает бота."""
    global application
    
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found")
        return False
    
    try:
        # Создаем application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Настройка обработчиков
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                COLLECTING_DATA: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input)
                ],
            },
            fallbacks=[
                CommandHandler('cancel', cancel),
                CommandHandler('help', help_command)
            ]
        )
        
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler('help', help_command))
        application.add_error_handler(error_handler)
        
        logger.info("Bot setup completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Bot setup failed: {e}")
        return False

def main():
    """Запуск приложения."""
    port = int(os.environ.get("PORT", 5000))
    
    # Настраиваем бота
    if setup_bot():
        # На Render используем webhook
        render_url = os.getenv("RENDER_EXTERNAL_URL")
        
        if render_url and application:
            # Webhook режим для Render
            webhook_url = f"{render_url}/webhook"
            logger.info(f"Starting webhook on {webhook_url}")
            
            application.run_webhook(
                listen="0.0.0.0",
                port=port,
                url_path=BOT_TOKEN,
                webhook_url=webhook_url,
                drop_pending_updates=True
            )
        else:
            # Polling режим для локального тестирования
            logger.info("Starting polling mode...")
            application.run_polling(drop_pending_updates=True)
    else:
        logger.error("Failed to setup bot")
        # Запускаем Flask даже если бот не настроен
        app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    main()
