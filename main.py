import os
import logging
import sqlite3
import re
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# ==================== تنظیمات از Environment Variables ====================
BOT_TOKEN = os.getenv('BOT_TOKEN')
SOURCE_CHANNEL_ID = int(os.getenv('SOURCE_CHANNEL_ID'))
DESTINATION_CHANNEL_ID = int(os.getenv('DESTINATION_CHANNEL_ID'))
REPLACEMENT_USERNAME = os.getenv('REPLACEMENT_USERNAME', '@apmovienet')

# ==================== تنظیمات لاگ ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== دیتابیس ====================
class Database:
    def __init__(self):
        db_path = '/tmp/processed_messages.db' if 'RAILWAY_ENVIRONMENT' in os.environ else 'processed_messages.db'
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_table()
    
    def create_table(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER UNIQUE,
                source_channel_id INTEGER,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
    
    def is_message_processed(self, message_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT 1 FROM processed_messages WHERE message_id = ? AND source_channel_id = ?',
            (message_id, SOURCE_CHANNEL_ID)
        )
        return cursor.fetchone() is not None
    
    def mark_message_processed(self, message_id: int):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO processed_messages (message_id, source_channel_id) VALUES (?, ?)',
                (message_id, SOURCE_CHANNEL_ID)
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass
    
    def close(self):
        self.conn.close()

def replace_usernames(text: str) -> str:
    if not text:
        return text
    
    username_pattern = r'@[a-zA-Z0-9_]{1,32}'
    replaced_text = re.sub(username_pattern, REPLACEMENT_USERNAME, text)
    
    original_usernames = re.findall(username_pattern, text)
    if original_usernames:
        logger.info(f"تغییر {len(original_usernames)} یوزرنیم به {REPLACEMENT_USERNAME}")
    
    return replaced_text

async def process_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post.chat.id != SOURCE_CHANNEL_ID:
        return
    
    message = update.channel_post
    db = Database()
    
    try:
        if db.is_message_processed(message.message_id):
            logger.info(f"پیام {message.message_id} قبلاً پردازش شده")
            return
        
        logger.info(f"دریافت پیام جدید: {message.message_id}")
        
        processed_text = None
        if message.text:
            processed_text = replace_usernames(message.text)
        elif message.caption:
            processed_text = replace_usernames(message.caption)
        
        if message.text and not message.media:
            await context.bot.send_message(
                chat_id=DESTINATION_CHANNEL_ID,
                text=processed_text,
                parse_mode=ParseMode.HTML if message.entities else None
            )
            logger.info("پیام متنی ارسال شد")
        
        elif message.photo:
            await context.bot.send_photo(
                chat_id=DESTINATION_CHANNEL_ID,
                photo=message.photo[-1].file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML if message.caption_entities else None
            )
            logger.info("عکس ارسال شد")
        
        elif message.video:
            await context.bot.send_video(
                chat_id=DESTINATION_CHANNEL_ID,
                video=message.video.file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML if message.caption_entities else None
            )
            logger.info("ویدیو ارسال شد")
        
        elif message.document:
            await context.bot.send_document(
                chat_id=DESTINATION_CHANNEL_ID,
                document=message.document.file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML if message.caption_entities else None
            )
            logger.info("فایل ارسال شد")
        
        else:
            if processed_text:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=processed_text
                )
        
        db.mark_message_processed(message.message_id)
        logger.info(f"پیام {message.message_id} با موفقیت ارسال شد")
        
    except Exception as e:
        logger.error(f"خطا در پردازش پیام: {e}")
    
    finally:
        db.close()

def main():
    if not BOT_TOKEN:
        logger.error("توکن ربات تنظیم نشده است!")
        return
    
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.Chat(SOURCE_CHANNEL_ID), process_channel_post))
    
    logger.info("ربات راه‌اندازی شد...")
    logger.info(f"کانال مبدأ: {SOURCE_CHANNEL_ID}")
    logger.info(f"کانال مقصد: {DESTINATION_CHANNEL_ID}")
    logger.info(f"جایگزینی با: {REPLACEMENT_USERNAME}")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
