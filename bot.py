import os
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Admin user ID (set this to your admin user ID)
ADMIN_ID = None  # Configure this with actual admin ID

# Chat history storage
chat_history = []
MAX_HISTORY_SIZE = 1000

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler"""
    await update.message.reply_text(
        "Welcome to the bot! Use /help to see available commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command handler"""
    help_text = """
Available commands:
/start - Start the bot
/help - Show this help message
/history - Show chat history (Admin only)
    """
    await update.message.reply_text(help_text)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show chat history (Admin only)"""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if ADMIN_ID is None or user_id != ADMIN_ID:
        await update.message.reply_text("❌ This command is only available for administrators.")
        return
    
    if not chat_history:
        await update.message.reply_text("📋 Chat history is empty.")
        return
    
    # Format and send history
    history_text = "📋 **Chat History:**\n\n"
    for entry in chat_history[-50:]:  # Show last 50 messages
        timestamp = entry.get('timestamp', 'N/A')
        username = entry.get('username', 'Unknown')
        message = entry.get('message', '')
        history_text += f"[{timestamp}] {username}: {message}\n"
    
    # If history is too long, send in chunks
    if len(history_text) > 4096:
        chunks = [history_text[i:i+4096] for i in range(0, len(history_text), 4096)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode='Markdown')
    else:
        await update.message.reply_text(history_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle regular messages and store in history"""
    message_text = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or f"User_{user_id}"
    
    # Create history entry
    entry = {
        'user_id': user_id,
        'username': username,
        'message': message_text,
        'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Add to history
    chat_history.append(entry)
    
    # Keep history size manageable
    if len(chat_history) > MAX_HISTORY_SIZE:
        chat_history.pop(0)
    
    # Echo the message or process it
    await update.message.reply_text(f"Message received: {message_text}")

def main() -> None:
    """Start the bot"""
    # Get token from environment variable
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("history", history_command))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
