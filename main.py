import os
import logging
import sqlite3
import re
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# ==================== تنظیمات مستقیم ====================
BOT_TOKEN = "8379314037:AAEpz2EuVtkynaFqCi16bCJvRlMRnTr8K7w"
SOURCE_CHANNEL_ID = -1003319450332
DESTINATION_CHANNEL_ID = -1002061481133
REPLACEMENT_USERNAME = "@apmovienet"

# ==================== قالب ثابت فوتر با لینک‌های HTML ====================
FOOTER_TEMPLATE = """📅 تاریخ پخش:{2025/01/25}
🌐 وبسایت و اپلیکیشن: Apmovie.net

───────────────
<a href="https://apmovie.net">⚫️| 🌟 اپی‌مووی | خانه سینما

<a href="https://dl.apmovie.net/APPS/Apmovie.apk">📱 دانلود اپلیکیشن اندروید موبایل</a>

<a href="https://dl.apmovie.net/APPS/Apmovie-TV.apk">🖥 دانلود اپلیکیشن اندروید تی‌وی</a>

🔴 برای ورود به اپلیکیشن ها نیازی به VPN نیست گرچه باز بودن آن هیچ مشکلی در کارکرد برنامه ها ایجاد نمیکند.

───────────────
<a href="https://t.me/apmovienet">⚫️ @apmovienet</a> | اپی‌مووی فارسی
<a href="https://t.me/PakhshinoTV">🟡 @PakhshinoTV</a> | کانال دوم
<a href="https://t.me/apmovie_Support">🔵 @apmovie_Support</a> | پشتیبانی

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

def escape_html(text: str) -> str:
    """فرار کردن کاراکترهای HTML برای جلوگیری از خطا"""
    if not text:
        return text
    
    # فرار کردن کاراکترهای خاص HTML
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    
    return text

def truncate_text(text: str, max_length: int = 900) -> str:
    """کوتاه کردن متن اگر از حد مجاز بیشتر باشد"""
    if len(text) <= max_length:
        return text
    
    logger.warning(f"متن از {max_length} کاراکتر بیشتر است، در حال کوتاه کردن...")
    return text[:max_length] + "..."

def process_content(original_text: str, is_caption: bool = False) -> str:
    """پردازش کامل محتوا و اضافه کردن فوتر ثابت"""
    if not original_text:
        return FOOTER_TEMPLATE
    
    # جایگزینی یوزرنیم‌ها
    main_content = replace_usernames(original_text)
    
    # فرار کردن کاراکترهای HTML در محتوای اصلی
    main_content = escape_html(main_content)
    
    # اگر کپشن است و متن اصلی خیلی طولانی است، آن را کوتاه کن
    if is_caption:
        main_content = truncate_text(main_content, 900)
    
    # ترکیب محتوای اصلی با فوتر جدید
    final_content = f"{main_content}\n\n{FOOTER_TEMPLATE}"
    
    # اگر بازهم طولانی است، کوتاه‌تر کن
    if len(final_content) > 1024:
        logger.warning("متن نهایی هنوز طولانی است، کوتاه کردن بیشتر...")
        available_space = 1024 - len(FOOTER_TEMPLATE) - 50
        if available_space > 100:
            main_content = truncate_text(main_content, available_space)
            final_content = f"{main_content}\n\n{FOOTER_TEMPLATE}"
        else:
            final_content = FOOTER_TEMPLATE
    
    logger.info(f"✅ محتوا پردازش شد (طول: {len(final_content)} کاراکتر)")
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
        is_caption = False
        
        if message.text:
            processed_text = process_content(message.text)
            logger.info("📝 پردازش متن پیام")
        elif message.caption:
            processed_text = process_content(message.caption, is_caption=True)
            is_caption = True
            logger.info("📝 پردازش کپشن مدیا")
        
        if not processed_text:
            processed_text = FOOTER_TEMPLATE
        
        # لاگ طول متن نهایی
        logger.info(f"📏 طول متن نهایی: {len(processed_text)} کاراکتر")
        
        # ارسال به کانال مقصد با فرمت HTML
        if message.text and not message.media:
            await context.bot.send_message(
                chat_id=DESTINATION_CHANNEL_ID,
                text=processed_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False
            )
            logger.info("✅ پیام متتی با لینک‌های HTML ارسال شد")
        
        elif message.photo:
            await context.bot.send_photo(
                chat_id=DESTINATION_CHANNEL_ID,
                photo=message.photo[-1].file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML
            )
            logger.info("✅ عکس با کپشن و لینک‌های HTML ارسال شد")
        
        elif message.video:
            await context.bot.send_video(
                chat_id=DESTINATION_CHANNEL_ID,
                video=message.video.file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML
            )
            logger.info("✅ ویدیو با کپشن و لینک‌های HTML ارسال شد")
        
        elif message.document:
            await context.bot.send_document(
                chat_id=DESTINATION_CHANNEL_ID,
                document=message.document.file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML
            )
            logger.info("✅ فایل با کپشن و لینک‌های HTML ارسال شد")
        
        else:
            if processed_text:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=processed_text,
                    parse_mode=ParseMode.HTML
                )
                logger.info("✅ متن پردازش شده با لینک‌های HTML ارسال شد")
        
        db.mark_message_processed(message.message_id)
        logger.info(f"🎉 پیام {message.message_id} با موفقیت پردازش و ارسال شد")
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش پیام: {e}")
        
        # تلاش برای ارسال بدون HTML در صورت خطا
        try:
            # ایجاد نسخه ساده بدون HTML برای fallback
            simple_footer = """📅 تاریخ پخش:{2025/01/25}
🌐 وبسایت و اپلیکیشن: Apmovie.net

───────────────
🌟 اپی‌مووی | خانه سینما

📱 دانلود اپلیکیشن اندروید موبایل
🖥 دانلود اپلیکیشن اندروید تی‌وی

🔴 برای ورود به اپلیکیشن ها نیازی به VPN نیست...

───────────────
⚫️ @apmovienet | اپی‌مووی فارسی
🟡 @PakhshinoTV | کانال دوم
🔵 @apmovie_Support | پشتیبانی

───────────────
🎧 پشتیبانی فارسی:
در صورت نیاز به راهنمایی و پشتیبانی، از طریق کانال‌های بالا یا پشتیبانی اقدام کنید.

🙏 از حمایت ارزشمند شما سپاسگزاریم 🌹
🎥 با اپی‌مووی، دنیای سینما در دستان شماست."""
            
            if message.photo:
                await context.bot.send_photo(
                    chat_id=DESTINATION_CHANNEL_ID,
                    photo=message.photo[-1].file_id,
                    caption=simple_footer
                )
            elif message.video:
                await context.bot.send_video(
                    chat_id=DESTINATION_CHANNEL_ID,
                    video=message.video.file_id,
                    caption=simple_footer
                )
            elif message.document:
                await context.bot.send_document(
                    chat_id=DESTINATION_CHANNEL_ID,
                    document=message.document.file_id,
                    caption=simple_footer
                )
            else:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=simple_footer
                )
            logger.info("✅ پست با متن ساده ارسال شد")
        except Exception as fallback_error:
            logger.error(f"❌ خطا در ارسال جایگزین: {fallback_error}")
    
    finally:
        db.close()

def main():
    """تابع اصلی"""
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.Chat(SOURCE_CHANNEL_ID), process_channel_post))
    
    logger.info("🤖 ربات راه‌اندازی شد...")
    logger.info(f"📥 کانال مبدأ: {SOURCE_CHANNEL_ID}")
    logger.info(f"📤 کانال مقصد: {DESTINATION_CHANNEL_ID}")
    logger.info(f"🔁 جایگزینی با: {REPLACEMENT_USERNAME}")
    logger.info("📋 قالب ثابت فوتر با لینک‌های HTML فعال شد")
    logger.info("⚠️ مدیریت طول متن فعال شد (حداکثر 1024 کاراکتر)")
    logger.info("🔗 لینک‌های قابل کلیک فعال شدند")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
