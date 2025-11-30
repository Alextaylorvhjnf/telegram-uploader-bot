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
🌟 اپی‌مووی | خانه سینما

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

def clean_old_footer(content: str) -> str:
    """پاک کردن فوترهای قدیمی از محتوای اصلی"""
    if not content:
        return content
    
    # الگوهای مختلف برای شناسایی فوترهای قدیمی
    footer_patterns = [
        r'📅 تاریخ پخش:\{.*?\}.*?🎥 با اپی‌مووی، دنیای سینما در دستان شماست\.',
        r'🌐 وبسایت و اپلیکیشن: Apmovie\.net.*?🎥 با اپی‌مووی، دنیای سینما در دستان شماست\.',
        r'───────────────.*?🎥 با اپی‌مووی، دنیای سینما در دستان شماست\.',
    ]
    
    cleaned_content = content
    for pattern in footer_patterns:
        cleaned_content = re.sub(pattern, '', cleaned_content, flags=re.DOTALL)
    
    # حذف خطوط خالی اضافی در انتها
    cleaned_content = cleaned_content.rstrip()
    
    return cleaned_content

def process_content(original_text: str, is_caption: bool = False) -> str:
    """پردازش کامل محتوا و اضافه کردن فوتر ثابت"""
    if not original_text:
        return FOOTER_TEMPLATE
    
    # پاک کردن فوترهای قدیمی
    main_content = clean_old_footer(original_text)
    
    # جایگزینی یوزرنیم‌ها
    main_content = replace_usernames(main_content)
    
    # فرار کردن کاراکترهای HTML در محتوای اصلی
    main_content = escape_html(main_content)
    
    # ترکیب محتوای اصلی با فوتر جدید
    final_content = f"{main_content}\n\n{FOOTER_TEMPLATE}"
    
    # اگر طولانی است، محتوای اصلی را کوتاه کن اما فوتر را کامل نگه دار
    if len(final_content) > 4096:  # حداکثر طول مجاز تلگرام
        logger.warning("متن نهایی از 4096 کاراکتر بیشتر است، در حال کوتاه کردن محتوای اصلی...")
        
        # محاسبه فضای قابل استفاده برای محتوای اصلی
        available_space = 4096 - len(FOOTER_TEMPLATE) - 50  # فضای برای جداکننده
        
        if available_space > 500:  # حداقل 500 کاراکتر برای محتوای اصلی
            # کوتاه کردن محتوای اصلی اما حفظ ساختار
            lines = main_content.split('\n')
            shortened_content = []
            current_length = 0
            
            for line in lines:
                if current_length + len(line) + 1 <= available_space:
                    shortened_content.append(line)
                    current_length += len(line) + 1
                else:
                    # اگر خط جدید فضای کافی ندارد، سعی کن آن را کوتاه کن
                    remaining_space = available_space - current_length
                    if remaining_space > 50:  # حداقل 50 کاراکتر برای خط آخر
                        shortened_line = line[:remaining_space - 3] + "..."
                        shortened_content.append(shortened_line)
                    break
            
            main_content = '\n'.join(shortened_content)
            final_content = f"{main_content}\n\n{FOOTER_TEMPLATE}"
        else:
            # اگر فضای کافی نیست، فقط فوتر را بفرست
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
        
        logger.info(f"📨 دریافت پیام جدید: {message.message_id}")
        
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
            logger.info("✅ پیام متنی با لینک‌های HTML ارسال شد")
        
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
            
            # استفاده از محتوای اصلی ساده شده
            simple_content = ""
            if message.text:
                simple_content = replace_usernames(message.text)
            elif message.caption:
                simple_content = replace_usernames(message.caption)
            
            if simple_content:
                final_simple_content = f"{simple_content}\n\n{simple_footer}"
            else:
                final_simple_content = simple_footer
            
            if message.photo:
                await context.bot.send_photo(
                    chat_id=DESTINATION_CHANNEL_ID,
                    photo=message.photo[-1].file_id,
                    caption=final_simple_content
                )
            elif message.video:
                await context.bot.send_video(
                    chat_id=DESTINATION_CHANNEL_ID,
                    video=message.video.file_id,
                    caption=final_simple_content
                )
            elif message.document:
                await context.bot.send_document(
                    chat_id=DESTINATION_CHANNEL_ID,
                    document=message.document.file_id,
                    caption=final_simple_content
                )
            else:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=final_simple_content
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
    logger.info("⚠️ مدیریت طول متن فعال شد (حداکثر 4096 کاراکتر)")
    logger.info("🔗 لینک‌های قابل کلیک فعال شدند")
    logger.info("📖 حفظ کامل محتوای اصلی (شامل خلاصه داستان) فعال شد")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
