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
FOOTER_TEMPLATE = """
🌟 اپی‌مووی | خانه سینما

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
🎥 با اپی‌مووی، دنیای سینما در دستان شماست.
"""

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# دیتابیس برای جلوگیری از تکرار
class DB:
    def __init__(self):
        path = 'processed.db' if not os.getenv('RAILWAY_ENVIRONMENT') else '/tmp/processed.db'
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute('CREATE TABLE IF NOT EXISTS done (id INTEGER PRIMARY KEY)')
        self.conn.commit()

    def seen(self, msg_id): 
        return self.conn.execute('SELECT 1 FROM done WHERE id=?', (msg_id,)).fetchone()

    def mark(self, msg_id):
        self.conn.execute('INSERT OR IGNORE INTO done (id) VALUES (?)', (msg_id,))
        self.conn.commit()

db = DB()

def clean_caption(text):
    """
    پاکسازی کپشن:
    1. حذف تمام @username ها
    2. حذف تمام لینک‌های HTML و Markdown (فقط تگ حذف شود، متن باقی بماند)
    3. حفظ 100% متن اصلی غیرلینک
    """
    if not text:
        return text
    
    # حذف تمام @username ها
    text = re.sub(r'@\w+', '', text)
    
    # حذف لینک‌های HTML (<a ...>...</a>) - فقط تگ حذف شود، متن داخلش باقی بماند
    text = re.sub(r'<a[^>]*>', '', text)  # حذف تگ شروع
    text = re.sub(r'</a>', '', text)       # حذف تگ پایان
    
    # حذف لینک‌های Markdown [متن](لینک) - فقط ساختار لینک حذف شود، متن باقی بماند
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # حذف فضاهای اضافی و خطوط خالی
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = text.strip()
    
    return text

async def send_media_with_caption(bot, chat_id, media_type, media_file_id, caption):
    """
    ارسال مدیا با کپشن - اگر کپشن طولانی باشد، آن را به بخش‌های مناسب تقسیم می‌کند
    """
    # حداکثر طول مجاز برای کپشن در تلگرام
    MAX_CAPTION_LENGTH = 1024
    
    if len(caption) <= MAX_CAPTION_LENGTH:
        # اگر کپشن کوتاه است، مستقیماً ارسال شود
        if media_type == 'photo':
            await bot.send_photo(
                chat_id=chat_id,
                photo=media_file_id,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
        elif media_type == 'video':
            await bot.send_video(
                chat_id=chat_id,
                video=media_file_id,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
        elif media_type == 'document':
            await bot.send_document(
                chat_id=chat_id,
                document=media_file_id,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
        elif media_type == 'animation':
            await bot.send_animation(
                chat_id=chat_id,
                animation=media_file_id,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
    else:
        # اگر کپشن طولانی است، ابتدا مدیا را بدون کپشن ارسال کرده
        # سپس کپشن کامل را در پیام جداگانه ارسال می‌کنیم
        if media_type == 'photo':
            message = await bot.send_photo(
                chat_id=chat_id,
                photo=media_file_id
            )
        elif media_type == 'video':
            message = await bot.send_video(
                chat_id=chat_id,
                video=media_file_id
            )
        elif media_type == 'document':
            message = await bot.send_document(
                chat_id=chat_id,
                document=media_file_id
            )
        elif media_type == 'animation':
            message = await bot.send_animation(
                chat_id=chat_id,
                animation=media_file_id
            )
        
        # ارسال کپشن کامل به عنوان پاسخ به مدیا
        await send_long_message(bot, chat_id, caption, message.message_id)

async def send_long_message(bot, chat_id, text, reply_to_message_id=None):
    """
    ارسال پیام طولانی با تقسیم به بخش‌های 4096 کاراکتری
    """
    if len(text) <= 4096:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_to_message_id=reply_to_message_id
        )
        return
    
    # تقسیم متن به بخش‌های 4096 کاراکتری
    parts = []
    current_part = ""
    
    for paragraph in text.split('\n\n'):
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
    
    # ارسال بخش‌ها
    first_message_id = None
    for i, part in enumerate(parts):
        message = await bot.send_message(
            chat_id=chat_id,
            text=part,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_to_message_id=first_message_id if i > 0 else reply_to_message_id
        )
        if i == 0:
            first_message_id = message.message_id

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # بررسی اینکه آیا پست از کانال است
    if not update.channel_post and not update.edited_channel_post:
        return
        
    msg = update.channel_post or update.edited_channel_post
    
    if not msg or msg.chat.id != SOURCE_CHANNEL_ID or db.seen(msg.message_id):
        return

    # دریافت کپشن کامل
    original_text = (msg.caption or msg.text or "").strip()
    
    # پاکسازی کپشن
    cleaned_text = clean_caption(original_text)
    
    # اضافه کردن فوتر
    final_text = f"{cleaned_text}\n\n{FOOTER_TEMPLATE}".strip()

    try:
        # اگر پست مدیا دارد
        if msg.photo:
            await send_media_with_caption(
                context.bot,
                DESTINATION_CHANNEL_ID,
                'photo',
                msg.photo[-1].file_id,
                final_text
            )
            
        elif msg.video:
            await send_media_with_caption(
                context.bot,
                DESTINATION_CHANNEL_ID,
                'video',
                msg.video.file_id,
                final_text
            )
            
        elif msg.document:
            await send_media_with_caption(
                context.bot,
                DESTINATION_CHANNEL_ID,
                'document',
                msg.document.file_id,
                final_text
            )
            
        elif msg.animation:
            await send_media_with_caption(
                context.bot,
                DESTINATION_CHANNEL_ID,
                'animation',
                msg.animation.file_id,
                final_text
            )
            
        else:
            # پست متنی ساده
            await send_long_message(
                context.bot, 
                DESTINATION_CHANNEL_ID, 
                final_text
            )

        db.mark(msg.message_id)
        logger.info(f"پست {msg.message_id} با موفقیت ارسال شد")

    except Exception as e:
        logger.error(f"خطا در ارسال پست {msg.message_id}: {str(e)}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # استفاده از فیلتر مناسب برای نسخه‌های جدید کتابخانه
    app.add_handler(MessageHandler(
        filters.Chat(chat_id=SOURCE_CHANNEL_ID) & (filters.UpdateType.CHANNEL_POSTS),
        handler
    ))
    
    logger.info("ربات فعال شد - منتظر پست‌های جدید...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
