import os
import logging
import sqlite3
import re
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# ==================== تنظیمات از Environment Variables ====================
BOT_TOKEN = os.getenv('BOT_TOKEN')
SOURCE_CHANNEL_ID = int(os.getenv('SOURCE_CHANNEL_ID', '-1003319450332'))
DESTINATION_CHANNEL_ID = int(os.getenv('DESTINATION_CHANNEL_ID', '-1002061481133'))
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
        self.conn = sqlite3.connect(
            '/tmp/processed_messages.db' if 'RAILWAY_ENVIRONMENT' in os.environ else 'processed_messages.db',
            check_same_thread=False
        )
        self.create_table()
    
    def create_table(self):
        """ایجاد جدول برای ذخیره پیام‌های پردازش شده"""
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
        """بررسی اینکه آیا پیام قبلاً پردازش شده است"""
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT 1 FROM processed_messages WHERE message_id = ? AND source_channel_id = ?',
            (message_id, SOURCE_CHANNEL_ID)
        )
        return cursor.fetchone() is not None
    
    def mark_message_processed(self, message_id: int):
        """علامت گذاری پیام به عنوان پردازش شده"""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO processed_messages (message_id, source_channel_id) VALUES (?, ?)',
                (message_id, SOURCE_CHANNEL_ID)
            )
            self.conn.commit()
            logger.info(f"📝 پیام {message_id} در دیتابیس ثبت شد")
        except sqlite3.IntegrityError:
            logger.info(f"⏭️ پیام {message_id} قبلاً در دیتابیس وجود داشت")
    
    def close(self):
        """بستن اتصال دیتابیس"""
        self.conn.close()

# ==================== پردازش متن ====================
def replace_usernames(text: str) -> str:
    """
    جایگزینی تمام یوزرنیم‌های @ با مقدار ثابت
    """
    if not text:
        return text
    
    # الگو برای پیدا کردن یوزرنیم‌های تلگرام
    username_pattern = r'@[a-zA-Z0-9_]{1,32}'
    
    # جایگزینی همه یوزرنیم‌ها
    replaced_text = re.sub(username_pattern, REPLACEMENT_USERNAME, text)
    
    # لاگ تغییرات
    original_usernames = re.findall(username_pattern, text)
    if original_usernames:
        logger.info(f"🔁 جایگزینی {len(original_usernames)} یوزرنیم: {set(original_usernames)} -> {REPLACEMENT_USERNAME}")
    
    return replaced_text

# ==================== پردازش پیام ====================
async def process_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش پست‌های کانال سورس"""
    
    # اطمینان از اینکه پیام از کانال سورس است
    if update.channel_post.chat.id != SOURCE_CHANNEL_ID:
        return
    
    message = update.channel_post
    db = Database()
    
    try:
        # بررسی تکراری نبودن پیام
        if db.is_message_processed(message.message_id):
            logger.info(f"⏭️ پیام {message.message_id} قبلاً پردازش شده است")
            return
        
        logger.info(f"📨 دریافت پیام جدید: {message.message_id}")
        
        # پردازش متن/کپشن
        processed_text = None
        if message.text:
            processed_text = replace_usernames(message.text)
            logger.info("📝 پردازش متن پیام")
        elif message.caption:
            processed_text = replace_usernames(message.caption)
            logger.info("📝 پردازش کپشن مدیا")
        
        # ارسال به کانال مقصد بر اساس نوع محتوا
        if message.text and not message.media:
            # پیام متنی ساده
            await context.bot.send_message(
                chat_id=DESTINATION_CHANNEL_ID,
                text=processed_text,
                parse_mode=ParseMode.HTML if message.entities else None
            )
            logger.info("✅ پیام متنی ارسال شد")
        
        elif message.photo:
            # پیام با عکس
            await context.bot.send_photo(
                chat_id=DESTINATION_CHANNEL_ID,
                photo=message.photo[-1].file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML if message.caption_entities else None
            )
            logger.info("✅ عکس با کپشن ارسال شد")
        
        elif message.video:
            # پیام با ویدیو
            await context.bot.send_video(
                chat_id=DESTINATION_CHANNEL_ID,
                video=message.video.file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML if message.caption_entities else None
            )
            logger.info("✅ ویدیو با کپشن ارسال شد")
        
        elif message.document:
            # پیام با فایل
            await context.bot.send_document(
                chat_id=DESTINATION_CHANNEL_ID,
                document=message.document.file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML if message.caption_entities else None
            )
            logger.info("✅ فایل با کپشن ارسال شد")
        
        elif message.audio:
            # پیام با audio
            await context.bot.send_audio(
                chat_id=DESTINATION_CHANNEL_ID,
                audio=message.audio.file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML if message.caption_entities else None
            )
            logger.info("✅ audio با کپشن ارسال شد")
        
        else:
            # انواع دیگر پیام
            if processed_text:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=processed_text
                )
                logger.info("✅ متن پردازش شده ارسال شد")
            else:
                logger.warning(f"⚠️ نوع پیام پشتیبانی نمی‌شود: {message.message_id}")
                return
        
        # علامت گذاری پیام به عنوان پردازش شده
        db.mark_message_processed(message.message_id)
        logger.info(f"🎉 پیام {message.message_id} با موفقیت پردازش و ارسال شد")
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش پیام {message.message_id}: {str(e)}")
    
    finally:
        db.close()

# ==================== راه‌اندازی ربات ====================
def main():
    """تابع اصلی راه‌اندازی ربات"""
    
    # اعتبارسنجی متغیرهای محیطی
    required_vars = ['BOT_TOKEN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ متغیرهای محیطی زیر تنظیم نشده‌اند: {missing_vars}")
        return
    
    # ایجاد اپلیکیشن
    application = Application.builder().token(BOT_TOKEN).build()
    
    # افزودن هندلر برای پست‌های کانال
    application.add_handler(MessageHandler(filters.Chat(SOURCE_CHANNEL_ID), process_channel_post))
    
    # راه‌اندازی ربات
    logger.info("🤖 ربات در حال راه‌اندازی...")
    logger.info(f"📥 کانال سورس: {SOURCE_CHANNEL_ID}")
    logger.info(f"📤 کانال مقصد: {DESTINATION_CHANNEL_ID}")
    logger.info(f"🔁 جایگزینی یوزرنیم‌ها با: {REPLACEMENT_USERNAME}")
    logger.info("🟢 ربات آماده دریافت پیام‌ها است...")
    
    # شروع polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
