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
REPLACEMENT_USERNAME = "@apmovienet"

# فوتر ثابت (HTML مجاز)
FOOTER_TEMPLATE = """📅 تاریخ پخش: 2025/01/25
🌐 وبسایت و اپلیکیشن: Apmovie.net
───────────────
🌟 اپی‌مووی | خانه سینما
<a href="https://dl.apmovie.net/APPS/Apmovie.apk">📱 دانلود اپلیکیشن اندروید موبایل</a>
<a href="https://dl.apmovie.net/APPS/Apmovie-TV.apk">🖥 دانلود اپلیکیشن اندروید تی‌وی</a>
🔴 برای ورود به اپلیکیشن ها نیازی به VPN نیست
───────────────
<a href="https://t.me/apmovienet">⚫️ @apmovienet</a> | اپی‌مووی فارسی
<a href="https://t.me/PakhshinoTV">🟡 @PakhshinoTV</a> | کانال دوم
<a href="https://t.me/apmovie_Support">🔵 @apmovie_Support</a> | پشتیبانی
───────────────
🎧 پشتیبانی فارسی در کانال‌های بالا
🙏 ممنون از همراهی شما 🌹
🎥 با اپی‌مووی، دنیای سینما در دستان شماست."""

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# دیتابیس ساده برای جلوگیری از تکرار
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

# جایگزینی تمام @username ها با @apmovienet
def replace_all_tags(text):
    if not text:
        return text
    return re.sub(r'@\w+', REPLACEMENT_USERNAME, text)

# ارسال متن بلند بدون محدودیت (تقسیم خودکار به 4096)
async def send_long_caption(bot, chat_id, text):
    max_len = 4090
    parts = []
    while len(text) > max_len:
        cut = text.rfind('\n\n', 0, max_len)
        if cut == -1:
            cut = text.rfind(' ', 0, max_len)
        if cut == -1:
            cut = max_len
        parts.append(text[:cut])
        text = text[cut:].strip()
    parts.append(text)

    first = True
    for part in parts:
        if first:
            first = False
            return part  # اولین بخش برای کپشن اصلی
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=part,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or msg.chat.id != SOURCE_CHANNEL_ID or db.seen(msg.message_id):
        return

    original_text = (msg.caption or msg.text or "").strip()
    new_text = replace_all_tags(original_text)
    final_text = f"{new_text}\n\n{FOOTER_TEMPLATE}".strip()

    try:
        if msg.photo:
            caption = await send_long_caption(context.bot, DESTINATION_CHANNEL_ID, final_text)
            await context.bot.send_photo(
                chat_id=DESTINATION_CHANNEL_ID,
                photo=msg.photo[-1].file_id,
                caption=caption or final_text[:1000],
                parse_mode=ParseMode.HTML
            )

        elif msg.video:
            caption = await send_long_caption(context.bot, DESTINATION_CHANNEL_ID, final_text)
            await context.bot.send_video(
                chat_id=DESTINATION_CHANNEL_ID,
                video=msg.video.file_id,
                caption=caption or final_text[:1000],
                parse_mode=ParseMode.HTML
            )

        elif msg.document:
            caption = await send_long_caption(context.bot, DESTINATION_CHANNEL_ID, final_text)
            await context.bot.send_document(
                chat_id=DESTINATION_CHANNEL_ID,
                document=msg.document.file_id,
                caption=caption or final_text[:1000],
                parse_mode=ParseMode.HTML
            )

        elif msg.animation:
            caption = await send_long_caption(context.bot, DESTINATION_CHANNEL_ID, final_text)
            await context.bot.send_animation(
                chat_id=DESTINATION_CHANNEL_ID,
                animation=msg.animation.file_id,
                caption=caption or final_text[:1000],
                parse_mode=ParseMode.HTML
            )

        else:
            await send_long_caption(context.bot, DESTINATION_CHANNEL_ID, final_text)

        db.mark(msg.message_id)
        logger.info(f"ارسال شد → {msg.message_id}")

    except Exception as e:
        logger.error(f"خطا در ارسال {msg.message_id}: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.CHANNEL_POST, handler))
    
    logger.info("ربات فعال شد | همه تگ‌ها → @apmovienet | بدون محدودیت کپشن")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
