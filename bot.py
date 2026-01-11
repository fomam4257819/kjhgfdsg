import logging
from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
WELCOME_TEXT = """
👋 Welcome to our bot!

This bot provides useful features and commands.
Type /help to see available commands.
"""

class BotConfig:
    """Configuration class for bot settings."""
    def __init__(self, token: str):
        self.token = token
        self.command_handlers: Dict[str, Any] = {}
    
    def register_handler(self, command: str, handler) -> None:
        """Register a command handler."""
        self.command_handlers[command] = handler


class TelegramBot:
    """Main bot class with improved error handling and structure."""
    
    def __init__(self, config: BotConfig):
        self.config = config
        self.application: Optional[Application] = None
        self._validate_config()
    
    def _validate_config(self) -> None:
        """Validate bot configuration."""
        if not self.config.token:
            raise ValueError("Bot token must be provided")
        if not isinstance(self.config.token, str):
            raise TypeError("Bot token must be a string")
        logger.info("Configuration validated successfully")
    
    async def start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        try:
            await update.message.reply_text(WELCOME_TEXT)
            logger.info(f"Start command handled for user {update.effective_user.id}")
        except Exception as e:
            logger.error(f"Error in start_handler: {e}", exc_info=True)
            await update.message.reply_text("An error occurred. Please try again later.")
    
    async def help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        try:
            help_text = """
Available commands:
/start - Start the bot
/help - Show this message
/info - Get bot information
            """
            await update.message.reply_text(help_text)
            logger.info(f"Help command handled for user {update.effective_user.id}")
        except Exception as e:
            logger.error(f"Error in help_handler: {e}", exc_info=True)
            await update.message.reply_text("An error occurred. Please try again later.")
    
    async def info_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /info command."""
        try:
            info_text = "This is an improved bot with better error handling and structure."
            await update.message.reply_text(info_text)
            logger.info(f"Info command handled for user {update.effective_user.id}")
        except Exception as e:
            logger.error(f"Error in info_handler: {e}", exc_info=True)
            await update.message.reply_text("An error occurred. Please try again later.")
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular messages."""
        try:
            if update.message and update.message.text:
                logger.info(f"Message received from user {update.effective_user.id}: {update.message.text}")
                await update.message.reply_text("Message received. Use /help for available commands.")
            else:
                logger.warning("Received message with no text content")
        except Exception as e:
            logger.error(f"Error in message_handler: {e}", exc_info=True)
            await update.message.reply_text("An error occurred while processing your message.")
    
    async def error_handler(self, update: Optional[Update], context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors."""
        logger.error(f"Update {update} caused error {context.error}", exc_info=True)
    
    def setup_handlers(self) -> None:
        """Setup all command and message handlers."""
        try:
            if not self.application:
                raise RuntimeError("Application not initialized")
            
            self.application.add_handler(CommandHandler("start", self.start_handler))
            self.application.add_handler(CommandHandler("help", self.help_handler))
            self.application.add_handler(CommandHandler("info", self.info_handler))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler))
            self.application.add_error_handler(self.error_handler)
            
            logger.info("All handlers registered successfully")
        except Exception as e:
            logger.error(f"Error setting up handlers: {e}", exc_info=True)
            raise
    
    async def initialize(self) -> None:
        """Initialize the bot application."""
        try:
            self.application = Application.builder().token(self.config.token).build()
            self.setup_handlers()
            logger.info("Bot initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing bot: {e}", exc_info=True)
            raise
    
    async def start(self) -> None:
        """Start the bot."""
        try:
            if not self.application:
                await self.initialize()
            
            logger.info("Bot starting...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            logger.info("Bot is running")
        except Exception as e:
            logger.error(f"Error starting bot: {e}", exc_info=True)
            raise
    
    async def stop(self) -> None:
        """Stop the bot gracefully."""
        try:
            if self.application:
                await self.application.stop()
                await self.application.shutdown()
                logger.info("Bot stopped gracefully")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}", exc_info=True)
            raise


async def main():
    """Main entry point."""
    try:
        # Get bot token from environment or config
        import os
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
        
        config = BotConfig(token)
        bot = TelegramBot(config)
        await bot.initialize()
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
