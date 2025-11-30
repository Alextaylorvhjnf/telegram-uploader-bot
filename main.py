import os
import logging
import sqlite3
import re
import asyncio
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

# ==================== تنظیمات مستقیم ====================
BOT_TOKEN = "8379314037:AAEpz2EuVtkynaFqCi16bCJvRlMRnTr8K7w"
SOURCE_CHANNEL_ID = -1003319450332
DESTINATION_CHANNEL_ID = -1002061481133
REPLACEMENT_USERNAME = "@apmovienet"

# ==================== قالب ثابت فوتر ====================
FOOTER_TEMPLATE = """📅 تاریخ پخش:{2025/01/25}
🌐 وبسایت و اپلیکیشن: Apmovie.net

───────────────
🌟 اپی‌مووی | خانه سینما

📱 دانلود اپلیکیشن اندروید موبایل (https://dl.apmovie.net/APPS/Apmovie.apk)

🖥 دانلود اپلیکیشن اندروید تی‌وی (https://dl.apmovie.net/APPS/Apmovie-TV.apk)

🔴 برای ورود به اپلیکیشن ها نیازی به VPN نیست گرچه باز بودن آن هیچ مشکلی در کارکرد برنامه ها ایجاد نمیکند.

───────────────
⚫️ @apmovienet (https://t.me/apmovienet) | اپی‌مووی فارسی
🟡 @PakhshinoTV (https://t.me/PakhshinoTV) | کانال دوم
🔵 @apmovie_Support (https://t.me/apmovie_Support) | پشتیبانی

───────────────
🎧 پشتیبانی فارسی:
در صورت نیاز به راهنمایی و پشتیبانی، از طریق کانال‌های بالا یا پشتیبانی اقدام کنید.

🙏 از حمایت ارزشمند شما سپاسگزاریم 🌹
🎥 با اپی‌مووی، دنیای سینما در دستان شماست."""

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
    """جایگزینی یوزرنیم‌ها"""
    if not text:
        return text
    
    username_pattern = r'@[a-zA-Z0-9_]{1,32}'
    replaced_text = re.sub(username_pattern, REPLACEMENT_USERNAME, text)
    
    original_usernames = re.findall(username_pattern, text)
    if original_usernames:
        logger.info(f"تغییر {len(original_usernames)} یوزرنیم به {REPLACEMENT_USERNAME}")
    
    return replaced_text

def process_content(original_text: str) -> str:
    """پردازش کامل محتوا و اضافه کردن فوتر ثابت"""
    if not original_text:
        return FOOTER_TEMPLATE
    
    # جایگزینی یوزرنیم‌ها
    main_content = replace_usernames(original_text)
    
    # حذف فوترهای قدیمی اگر وجود دارند
    footer_patterns = [
        r'📅 تاریخ پخش:\{.*?\}.*?🎥 با اپی‌مووی، دنیای سینما در دستان شماست\.',
        r'🌐 وبسایت و اپلیکیشن: Apmovie\.net.*?🎥 با اپی‌مووی، دنیای سینما در دستان شماست\.',
    ]
    
    for pattern in footer_patterns:
        main_content = re.sub(pattern, '', main_content, flags=re.DOTALL)
    
    # پاکسازی خطوط خالی اضافی
    lines = main_content.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped_line = line.strip()
        if stripped_line and not any(keyword in stripped_line for keyword in [
            '📅 تاریخ پخش:', '🌐 وبسایت و اپلیکیشن:', '🌟 اپی‌مووی | خانه سینما',
            '📱 دانلود اپلیکیشن اندروید موبایل', '🖥 دانلود اپلیکیشن اندروید تی‌وی',
            '🔴 برای ورود به اپلیکیشن ها', '⚫️ @', '🟡 @', '🔵 @',
            '🎧 پشتیبانی فارسی:', '🙏 از حمایت ارزشمند', '🎥 با اپی‌مووی'
        ]):
            cleaned_lines.append(line)
    
    main_content_cleaned = '\n'.join(cleaned_lines).strip()
    
    # ترکیب محتوای اصلی با فوتر جدید
    if main_content_cleaned:
        final_content = f"{main_content_cleaned}\n\n{FOOTER_TEMPLATE}"
    else:
        final_content = FOOTER_TEMPLATE
    
    logger.info("✅ محتوا با فوتر جدید پردازش شد")
    return final_content

async def process_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش پست‌های کانال سورس"""
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
            processed_text = process_content(message.text)
        elif message.caption:
            processed_text = process_content(message.caption)
        
        # اگر هیچ متنی برای پردازش نبود، از فوتر ثابت استفاده کن
        if not processed_text:
            processed_text = FOOTER_TEMPLATE
        
        # ارسال به کانال مقصد
        if message.text and not message.media:
            await context.bot.send_message(
                chat_id=DESTINATION_CHANNEL_ID,
                text=processed_text
            )
            logger.info("پیام متنی ارسال شد")
        
        elif message.photo:
            await context.bot.send_photo(
                chat_id=DESTINATION_CHANNEL_ID,
                photo=message.photo[-1].file_id,
                caption=processed_text
            )
            logger.info("عکس ارسال شد")
        
        elif message.video:
            await context.bot.send_video(
                chat_id=DESTINATION_CHANNEL_ID,
                video=message.video.file_id,
                caption=processed_text
            )
            logger.info("ویدیو ارسال شد")
        
        elif message.document:
            await context.bot.send_document(
                chat_id=DESTINATION_CHANNEL_ID,
                document=message.document.file_id,
                caption=processed_text
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

async def main():
    """تابع اصلی"""
    if not BOT_TOKEN:
        logger.error("توکن ربات تنظیم نشده است!")
        return
    
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.Chat(SOURCE_CHANNEL_ID), process_channel_post))
    
    logger.info("ربات راه‌اندازی شد...")
    logger.info(f"کانال مبدأ: {SOURCE_CHANNEL_ID}")
    logger.info(f"کانال مقصد: {DESTINATION_CHANNEL_ID}")
    logger.info(f"جایگزینی با: {REPLACEMENT_USERNAME}")
    logger.info("قالب ثابت فوتر فعال شد")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    asyncio.run(main())
