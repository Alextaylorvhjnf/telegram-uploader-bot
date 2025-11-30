import os
import logging
import sqlite3
import re
import asyncio
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# ==================== تنظیمات از Environment Variables ====================
BOT_TOKEN = os.getenv('BOT_TOKEN')
SOURCE_CHANNEL_ID = int(os.getenv('SOURCE_CHANNEL_ID'))
DESTINATION_CHANNEL_ID = int(os.getenv('DESTINATION_CHANNEL_ID'))
REPLACEMENT_USERNAME = os.getenv('REPLACEMENT_USERNAME', '@apmovienet')

# ==================== قالب ثابت فوتر ====================
FOOTER_TEMPLATE = """📅 تاریخ پخش: {release_date}
🌐 وبسایت و اپلیکیشن: Apmovie.net

───────────────
🌟 اپی‌مووی | خانه سینما

[📱 دانلود اپلیکیشن اندروید موبایل](https://dl.apmovie.net/APPS/Apmovie.apk)

[🖥 دانلود اپلیکیشن اندروید تی‌وی](https://dl.apmovie.net/APPS/Apmovie-TV.apk)

🔴 برای ورود به اپلیکیشن ها نیازی به VPN نیست گرچه باز بودن آن هیچ مشکلی در کارکرد برنامه ها ایجاد نمیکند.

───────────────
[⚫️ @apmovienet](https://t.me/apmovienet) | اپی‌مووی فارسی
[🟡 @PakhshinoTV](https://t.me/PakhshinoTV) | کانال دوم
[🔵 @apmovie_Support](https://t.me/apmovie_Support) | پشتیبانی

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
            logger.info(f"📝 پیام {message_id} در دیتابیس ثبت شد")
        except sqlite3.IntegrityError:
            logger.info(f"⏭️ پیام {message_id} قبلاً در دیتابیس وجود داشت")
    
    def close(self):
        self.conn.close()

def extract_release_date(text: str) -> str:
    """استخراج تاریخ پخش از متن اصلی"""
    date_pattern = r'📅\s*تاریخ\s*پخش:\s*{([^}]+)}'
    match = re.search(date_pattern, text)
    if match:
        return match.group(1)
    return "2025/01/25"  # تاریخ پیش‌فرض

def replace_usernames(text: str) -> str:
    """جایگزینی یوزرنیم‌ها و پردازش متن اصلی"""
    if not text:
        return text
    
    # الگو برای پیدا کردن یوزرنیم‌های تلگرام
    username_pattern = r'@[a-zA-Z0-9_]{1,32}'
    replaced_text = re.sub(username_pattern, REPLACEMENT_USERNAME, text)
    
    # حذف بخش فوتر قدیمی (اگر وجود دارد)
    footer_patterns = [
        r'📅\s*تاریخ\s*پخش:.*$',
        r'🌐\s*وبسایت\s*و\s*اپلیکیشن:.*$',
        r'───────────────.*$',
        r'📱\s*دانلود\s*اپلیکیشن.*$',
        r'🖥\s*دانلود\s*اپلیکیشن.*$',
        r'🔴\s*برای\s*ورود\s*به\s*اپلیکیشن.*$',
        r'⚫️\s*@.*$',
        r'🟡\s*@.*$', 
        r'🔵\s*@.*$',
        r'🎧\s*پشتیبانی\s*فارسی:.*$',
        r'🙏\s*از\s*حمایت\s*ارزشمند.*$',
        r'🎥\s*با\s*اپی‌مووی.*$'
    ]
    
    for pattern in footer_patterns:
        replaced_text = re.sub(pattern, '', replaced_text, flags=re.MULTILINE | re.DOTALL)
    
    # پاکسازی خطوط خالی اضافی
    lines = replaced_text.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.strip() and not any(footer in line for footer in ['📅', '🌐', '📱', '🖥', '🔴', '⚫️', '🟡', '🔵', '🎧', '🙏', '🎥']):
            cleaned_lines.append(line)
    
    cleaned_text = '\n'.join(cleaned_lines).strip()
    
    # لاگ تغییرات
    original_usernames = re.findall(username_pattern, text)
    if original_usernames:
        logger.info(f"🔁 جایگزینی {len(original_usernames)} یوزرنیم: {set(original_usernames)} -> {REPLACEMENT_USERNAME}")
    
    return cleaned_text

def process_content(original_text: str) -> str:
    """پردازش کامل محتوا و اضافه کردن فوتر ثابت"""
    if not original_text:
        return FOOTER_TEMPLATE.format(release_date="2025/01/25")
    
    # استخراج تاریخ از متن اصلی
    release_date = extract_release_date(original_text)
    
    # جایگزینی یوزرنیم‌ها و حذف فوتر قدیمی
    main_content = replace_usernames(original_text)
    
    # ترکیب محتوای اصلی با فوتر جدید
    final_content = f"{main_content}\n\n{FOOTER_TEMPLATE.format(release_date=release_date)}"
    
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
            logger.info(f"⏭️ پیام {message.message_id} قبلاً پردازش شده")
            return
        
        logger.info(f"📨 دریافت پیام جدید: {message.message_id}")
        
        processed_text = None
        if message.text:
            processed_text = process_content(message.text)
            logger.info("📝 پردازش متن پیام")
        elif message.caption:
            processed_text = process_content(message.caption)
            logger.info("📝 پردازش کپشن مدیا")
        
        # ارسال به کانال مقصد
        if message.text and not message.media:
            await context.bot.send_message(
                chat_id=DESTINATION_CHANNEL_ID,
                text=processed_text,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=False
            )
            logger.info("✅ پیام متنی با فوتر جدید ارسال شد")
        
        elif message.photo:
            await context.bot.send_photo(
                chat_id=DESTINATION_CHANNEL_ID,
                photo=message.photo[-1].file_id,
                caption=processed_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.info("✅ عکس با کپشن و فوتر جدید ارسال شد")
        
        elif message.video:
            await context.bot.send_video(
                chat_id=DESTINATION_CHANNEL_ID,
                video=message.video.file_id,
                caption=processed_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.info("✅ ویدیو با کپشن و فوتر جدید ارسال شد")
        
        elif message.document:
            await context.bot.send_document(
                chat_id=DESTINATION_CHANNEL_ID,
                document=message.document.file_id,
                caption=processed_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.info("✅ فایل با کپشن و فوتر جدید ارسال شد")
        
        elif message.audio:
            await context.bot.send_audio(
                chat_id=DESTINATION_CHANNEL_ID,
                audio=message.audio.file_id,
                caption=processed_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.info("✅ audio با کپشن و فوتر جدید ارسال شد")
        
        else:
            if processed_text:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=processed_text,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                logger.info("✅ متن پردازش شده با فوتر جدید ارسال شد")
            else:
                # اگر محتوایی برای پردازش نبود، فقط فوتر را ارسال کن
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=FOOTER_TEMPLATE.format(release_date="2025/01/25"),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                logger.info("✅ فوتر ثابت ارسال شد")
        
        db.mark_message_processed(message.message_id)
        logger.info(f"🎉 پیام {message.message_id} با موفقیت پردازش و ارسال شد")
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش پیام {message.message_id}: {str(e)}")
        # تلاش برای ارسال بدون markdown در صورت خطا
        try:
            if message.text and not message.media:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=processed_text or message.text
                )
            elif message.media:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text="پیام جدید - خطا در پردازش markdown"
                )
        except Exception as fallback_error:
            logger.error(f"❌ خطا در ارسال جایگزین: {fallback_error}")
    
    finally:
        db.close()

async def main():
    """تابع اصلی با async"""
    if not BOT_TOKEN:
        logger.error("❌ توکن ربات تنظیم نشده است!")
        return
    
    try:
        # ایجاد اپلیکیشن با تنظیمات بهینه
        application = Application.builder().token(BOT_TOKEN).build()
        
        # افزودن هندلر
        application.add_handler(MessageHandler(filters.Chat(SOURCE_CHANNEL_ID), process_channel_post))
        
        logger.info("🤖 ربات در حال راه‌اندازی...")
        logger.info(f"📥 کانال سورس: {SOURCE_CHANNEL_ID}")
        logger.info(f"📤 کانال مقصد: {DESTINATION_CHANNEL_ID}")
        logger.info(f"🔁 جایگزینی یوزرنیم‌ها با: {REPLACEMENT_USERNAME}")
        logger.info("📋 قالب ثابت فوتر فعال شده است")
        
        # راه‌اندازی با تنظیمات بهینه برای Railway
        await application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False
        )
        
    except Exception as e:
        logger.error(f"❌ خطای جدی در ربات: {e}")

if __name__ == '__main__':
    # اجرای اصلی
    asyncio.run(main())
