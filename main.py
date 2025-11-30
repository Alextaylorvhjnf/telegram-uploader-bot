import os
import logging
import sqlite3
import re
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

# ==================== تنظیمات مستقیم ====================
BOT_TOKEN = "8379314037:AAEpz2EuVtkynaFqCi16bCJvRlMRnTr8K7w"
SOURCE_CHANNELS = [
    -1003319450332,  # کانال سورس اول
    -1003442708764   # کانال سورس دوم
]
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
                message_id INTEGER,
                source_channel_id INTEGER,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(message_id, source_channel_id)
            )
        ''')
        self.conn.commit()
    
    def is_message_processed(self, message_id: int, source_channel_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT 1 FROM processed_messages WHERE message_id = ? AND source_channel_id = ?',
            (message_id, source_channel_id)
        )
        return cursor.fetchone() is not None
    
    def mark_message_processed(self, message_id: int, source_channel_id: int):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO processed_messages (message_id, source_channel_id) VALUES (?, ?)',
                (message_id, source_channel_id)
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

async def test_channel_access(context: ContextTypes.DEFAULT_TYPE):
    """تست دسترسی به کانال‌ها"""
    try:
        for channel_id in SOURCE_CHANNELS:
            try:
                chat = await context.bot.get_chat(channel_id)
                logger.info(f"✅ دسترسی به کانال {channel_id} تأیید شد: {chat.title}")
            except Exception as e:
                logger.error(f"❌ خطا در دسترسی به کانال {channel_id}: {e}")
        
        # تست دسترسی به کانال مقصد
        try:
            dest_chat = await context.bot.get_chat(DESTINATION_CHANNEL_ID)
            logger.info(f"✅ دسترسی به کانال مقصد تأیید شد: {dest_chat.title}")
        except Exception as e:
            logger.error(f"❌ خطا در دسترسی به کانال مقصد: {e}")
            
    except Exception as e:
        logger.error(f"❌ خطا در تست دسترسی: {e}")

async def process_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش پست‌های کانال‌های سورس"""
    message = update.channel_post
    source_channel_id = message.chat.id
    
    # بررسی اینکه پیام از یکی از کانال‌های سورس مورد نظر است
    if source_channel_id not in SOURCE_CHANNELS:
        logger.info(f"پیام از کانال ناشناخته {source_channel_id} دریافت شد (مورد انتظار: {SOURCE_CHANNELS})")
        return
    
    db = Database()
    
    try:
        if db.is_message_processed(message.message_id, source_channel_id):
            logger.info(f"پیام {message.message_id} از کانال {source_channel_id} قبلاً پردازش شده")
            return
        
        logger.info(f"📨 دریافت پیام جدید از کانال {source_channel_id}: {message.message_id}")
        
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
        
        # ارسال به کانال مقصد
        if message.text and not message.media:
            await context.bot.send_message(
                chat_id=DESTINATION_CHANNEL_ID,
                text=processed_text
            )
            logger.info("✅ پیام متنی ارسال شد")
        
        elif message.photo:
            await context.bot.send_photo(
                chat_id=DESTINATION_CHANNEL_ID,
                photo=message.photo[-1].file_id,
                caption=processed_text
            )
            logger.info("✅ عکس با کپشن ارسال شد")
        
        elif message.video:
            await context.bot.send_video(
                chat_id=DESTINATION_CHANNEL_ID,
                video=message.video.file_id,
                caption=processed_text
            )
            logger.info("✅ ویدیو با کپشن ارسال شد")
        
        elif message.document:
            await context.bot.send_document(
                chat_id=DESTINATION_CHANNEL_ID,
                document=message.document.file_id,
                caption=processed_text
            )
            logger.info("✅ فایل با کپشن ارسال شد")
        
        else:
            if processed_text:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=processed_text
                )
                logger.info("✅ متن پردازش شده ارسال شد")
        
        db.mark_message_processed(message.message_id, source_channel_id)
        logger.info(f"🎉 پیام {message.message_id} از کانال {source_channel_id} با موفقیت پردازش و ارسال شد")
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش پیام از کانال {source_channel_id}: {e}")
        
        # تلاش برای ارسال بدون فوتر در صورت خطا
        try:
            if message.photo:
                await context.bot.send_photo(
                    chat_id=DESTINATION_CHANNEL_ID,
                    photo=message.photo[-1].file_id,
                    caption="پست جدید - خطا در پردازش متن کامل"
                )
            elif message.video:
                await context.bot.send_video(
                    chat_id=DESTINATION_CHANNEL_ID,
                    video=message.video.file_id,
                    caption="پست جدید - خطا در پردازش متن کامل"
                )
            elif message.document:
                await context.bot.send_document(
                    chat_id=DESTINATION_CHANNEL_ID,
                    document=message.document.file_id,
                    caption="پست جدید - خطا در پردازش متن کامل"
                )
            else:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=FOOTER_TEMPLATE
                )
            logger.info("✅ پست با متن جایگزین ارسال شد")
        except Exception as fallback_error:
            logger.error(f"❌ خطا در ارسال جایگزین: {fallback_error}")
    
    finally:
        db.close()

async def post_init(application: Application):
    """تابع اجرایی بعد از راه‌اندازی ربات"""
    await test_channel_access(application)

def main():
    """تابع اصلی"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # افزودن هندلر برای تمام کانال‌های سورس
    application.add_handler(MessageHandler(filters.Chat(SOURCE_CHANNELS), process_channel_post))
    
    # افزودن تابع post_init
    application.post_init = post_init
    
    logger.info("🤖 ربات راه‌اندازی شد...")
    logger.info(f"📥 کانال‌های مبدأ: {SOURCE_CHANNELS}")
    logger.info(f"📤 کانال مقصد: {DESTINATION_CHANNEL_ID}")
    logger.info(f"🔁 جایگزینی با: {REPLACEMENT_USERNAME}")
    logger.info("📋 قالب ثابت فوتر فعال شد")
    logger.info("⚠️ مدیریت طول متن فعال شد (حداکثر 1024 کاراکتر)")
    logger.info("🔄 پشتیبانی از چندین کانال سورس فعال شد")
    logger.info("🔍 در حال تست دسترسی به کانال‌ها...")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
