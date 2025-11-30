import os
import logging
import sqlite3
import re
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# ==================== تنظیمات ====================
BOT_TOKEN = "8379314037:AAEpz2EuVtkynaFqCi16bCJvRlMRnTr8K7w"
SOURCE_CHANNEL_ID = -1003319450332
DESTINATION_CHANNEL_ID = -1002061481133

# فوتر ثابت (HTML)
FOOTER_TEMPLATE = """🌟 اپی‌مووی | خانه سینما

📱 <a href="https://dl.apmovie.net/APPS/Apmovie.apk">دانلود اپلیکیشن اندروید موبایل</a>

🖥 <a href="https://dl.apmovie.net/APPS/Apmovie-TV.apk">دانلود اپلیکیشن اندروید تی‌وی</a>

🔴 برای ورود به اپلیکیشن ها نیازی به VPN نیست گرچه باز بودن آن هیچ مشکلی ایجاد نمیکند.

───────────────
⚫️ <a href="https://t.me/apmovienet">@apmovienet</a> | اپی‌مووی فارسی
🟡 <a href="https://t.me/PakhshinoTV">@PakhshinoTV</a> | کانال دوم
🔵 <a href="https://t.me/apmovie_Support">@apmovie_Support</a> | پشتیبانی
───────────────

🎧 پشتیبانی فارسی:
در صورت نیاز به راهنمایی و پشتیبانی، از طریق کانال‌های بالا یا پشتیبانی اقدام کنید.

🙏 از حمایت ارزشمند شما سپاسگزاریم
🎥 با اپی‌مووی، دنیای سینما در دستان شماست."""

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

def clean_caption_completely(text: str) -> str:
    """
    پاکسازی کامل کپشن:
    - حذف تمام @username ها
    - حذف تمام لینک‌های HTML و Markdown
    - حذف تمام URL ها
    - حذف تمام تگ‌ها و مشخصات کانال
    - فقط متن اصلی فیلم و توضیحاتش باقی بماند
    """
    if not text:
        return ""
    
    # حذف تمام @username ها
    text = re.sub(r'@\w+', '', text)
    
    # حذف تمام لینک‌های HTML (<a ...>...</a>) - فقط تگ حذف شود، متن داخلش باقی بماند
    text = re.sub(r'<a[^>]*>', '', text)
    text = re.sub(r'</a>', '', text)
    
    # حذف تمام لینک‌های Markdown [متن](لینک) - فقط ساختار لینک حذف شود، متن باقی بماند
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # حذف URL های مستقیم
    text = re.sub(r'https?://\S+', '', text)
    
    # حذف هشتگ‌ها
    text = re.sub(r'#\w+', '', text)
    
    # حذف متن‌های تبلیغاتی و مشخصات کانال
    patterns_to_remove = [
        r'کانال.*فیلم',
        r'Channel.*Movie',
        r'Download.*Film',
        r'فیلم.*سینمایی',
        r'Movie.*Channel',
        r'Join.*Channel',
        r'عضویت.*کانال',
        r'Telegram.*Channel',
        r'کانال.*تلگرام',
        r'اشتراک.*کانال',
        r'Subscribe.*Channel',
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # تمیز کردن فضاهای اضافی و خطوط خالی
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        # حذف خطوط خالی و خطوطی که فقط شامل کاراکترهای خاص هستند
        if line and not re.match(r'^[_\-\=\.\*~]+$', line):
            cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # حذف خطوط خالی متوالی
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = text.strip()
    
    return text

def process_content(original_text: str) -> str:
    """پردازش کامل محتوا و اضافه کردن فوتر ثابت"""
    if not original_text:
        return FOOTER_TEMPLATE
    
    # پاکسازی کامل کپشن - فقط مشخصات فیلم باقی بماند
    main_content = clean_caption_completely(original_text)
    
    # اگر بعد از پاکسازی چیزی نماند، از متن اصلی استفاده کن (اما بدون تگ‌ها)
    if not main_content.strip():
        # حداقل پاکسازی برای حذف تگ‌ها
        main_content = re.sub(r'@\w+', '', original_text)
        main_content = re.sub(r'<a[^>]*>', '', main_content)
        main_content = re.sub(r'</a>', '', main_content)
        main_content = re.sub(r'https?://\S+', '', main_content)
        main_content = main_content.strip()
    
    # ترکیب محتوای اصلی با فوتر
    if main_content.strip():
        final_content = f"{main_content}\n\n{FOOTER_TEMPLATE}"
    else:
        final_content = FOOTER_TEMPLATE
    
    logger.info(f"✅ محتوا پردازش شد (طول: {len(final_content)} کاراکتر)")
    return final_content

async def send_with_proper_caption(context, message, processed_text):
    """ارسال پیام با مدیریت صحیح کپشن"""
    try:
        # اگر کپشن کوتاه است (کمتر از 1024 کاراکتر)، مستقیماً ارسال کن
        if len(processed_text) <= 1024:
            if message.photo:
                await context.bot.send_photo(
                    chat_id=DESTINATION_CHANNEL_ID,
                    photo=message.photo[-1].file_id,
                    caption=processed_text,
                    parse_mode=ParseMode.HTML
                )
            elif message.video:
                await context.bot.send_video(
                    chat_id=DESTINATION_CHANNEL_ID,
                    video=message.video.file_id,
                    caption=processed_text,
                    parse_mode=ParseMode.HTML
                )
            elif message.document:
                await context.bot.send_document(
                    chat_id=DESTINATION_CHANNEL_ID,
                    document=message.document.file_id,
                    caption=processed_text,
                    parse_mode=ParseMode.HTML
                )
            elif message.animation:
                await context.bot.send_animation(
                    chat_id=DESTINATION_CHANNEL_ID,
                    animation=message.animation.file_id,
                    caption=processed_text,
                    parse_mode=ParseMode.HTML
                )
            else:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=processed_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
        else:
            # اگر کپشن طولانی است، ابتدا مدیا را بدون کپشن ارسال کن
            if message.photo:
                media_message = await context.bot.send_photo(
                    chat_id=DESTINATION_CHANNEL_ID,
                    photo=message.photo[-1].file_id
                )
            elif message.video:
                media_message = await context.bot.send_video(
                    chat_id=DESTINATION_CHANNEL_ID,
                    video=message.video.file_id
                )
            elif message.document:
                media_message = await context.bot.send_document(
                    chat_id=DESTINATION_CHANNEL_ID,
                    document=message.document.file_id
                )
            elif message.animation:
                media_message = await context.bot.send_animation(
                    chat_id=DESTINATION_CHANNEL_ID,
                    animation=message.animation.file_id
                )
            else:
                media_message = None
            
            # سپس کپشن کامل را به عنوان پیام جداگانه ارسال کن
            if media_message:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=processed_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_to_message_id=media_message.message_id
                )
            else:
                # برای پیام‌های متنی طولانی
                if len(processed_text) <= 4096:
                    await context.bot.send_message(
                        chat_id=DESTINATION_CHANNEL_ID,
                        text=processed_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                else:
                    # تقسیم پیام طولانی
                    parts = []
                    current_part = ""
                    
                    for paragraph in processed_text.split('\n\n'):
                        if len(current_part) + len(paragraph) + 2 <= 4096:
                            if current_part:
                                current_part += '\n\n' + paragraph
                            else:
                                current_part = paragraph
                        else:
                            if current_part:
                                parts.append(current_part)
                            current_part = paragraph
                    
                    if current_part:
                        parts.append(current_part)
                    
                    first_message = None
                    for i, part in enumerate(parts):
                        if i == 0:
                            first_message = await context.bot.send_message(
                                chat_id=DESTINATION_CHANNEL_ID,
                                text=part,
                                parse_mode=ParseMode.HTML,
                                disable_web_page_preview=True
                            )
                        else:
                            await context.bot.send_message(
                                chat_id=DESTINATION_CHANNEL_ID,
                                text=part,
                                parse_mode=ParseMode.HTML,
                                disable_web_page_preview=True,
                                reply_to_message_id=first_message.message_id
                            )
        
        return True
        
    except Exception as e:
        logger.error(f"خطا در ارسال پیام: {str(e)}")
        return False

async def process_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش پست‌های کانال سورس"""
    if not update.channel_post:
        return
    
    message = update.channel_post
    
    if message.chat.id != SOURCE_CHANNEL_ID:
        return
    
    db = Database()
    
    try:
        if db.is_message_processed(message.message_id):
            logger.info(f"پیام {message.message_id} قبلاً پردازش شده")
            return
        
        logger.info(f"دریافت پیام جدید: {message.message_id}")
        
        # دریافت متن اصلی
        original_text = (message.caption or message.text or "").strip()
        
        # پردازش محتوا
        processed_text = process_content(original_text)
        
        # ارسال پیام
        success = await send_with_proper_caption(context, message, processed_text)
        
        if success:
            db.mark_message_processed(message.message_id)
            logger.info(f"🎉 پیام {message.message_id} با موفقیت پردازش و ارسال شد")
        else:
            logger.error(f"❌ خطا در ارسال پیام {message.message_id}")
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش پیام: {e}")
        
        # تلاش برای ارسال ساده‌تر در صورت خطا
        try:
            if message.photo:
                await context.bot.send_photo(
                    chat_id=DESTINATION_CHANNEL_ID,
                    photo=message.photo[-1].file_id,
                    caption=FOOTER_TEMPLATE,
                    parse_mode=ParseMode.HTML
                )
            elif message.video:
                await context.bot.send_video(
                    chat_id=DESTINATION_CHANNEL_ID,
                    video=message.video.file_id,
                    caption=FOOTER_TEMPLATE,
                    parse_mode=ParseMode.HTML
                )
            else:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=FOOTER_TEMPLATE,
                    parse_mode=ParseMode.HTML
                )
            
            db.mark_message_processed(message.message_id)
            logger.info("✅ پست با متن ساده‌تر ارسال شد")
            
        except Exception as fallback_error:
            logger.error(f"❌ خطا در ارسال جایگزین: {fallback_error}")
    
    finally:
        db.close()

def main():
    """تابع اصلی"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # استفاده از فیلتر مناسب
    application.add_handler(MessageHandler(
        filters.Chat(chat_id=SOURCE_CHANNEL_ID) & (filters.UpdateType.CHANNEL_POSTS),
        process_channel_post
    ))
    
    logger.info("🤖 ربات راه‌اندازی شد...")
    logger.info(f"📥 کانال مبدأ: {SOURCE_CHANNEL_ID}")
    logger.info(f"📤 کانال مقصد: {DESTINATION_CHANNEL_ID}")
    logger.info("🔄 پاکسازی کامل کپشن‌ها فعال شد")
    logger.info("📋 فوتر ثابت با لینک‌های HTML فعال شد")
    logger.info("🎯 فقط مشخصات فیلم + فوتر اپی‌مووی نمایش داده می‌شود")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
