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

def extract_and_preserve_all_info(content: str) -> str:
    """استخراج و حفظ تمام اطلاعات مهم - نسخه ساده‌شده"""
    if not content:
        return content
    
    # ابتدا محتوای اصلی را برگردان (بدون هیچ فیلتری)
    # فقط فوترهای قدیمی پاک شده‌اند
    return content

def smart_truncate_with_priority(content: str, max_length: int, is_caption: bool = False) -> str:
    """کوتاه کردن هوشمند متن با اولویت حفظ تمام اطلاعات مهم"""
    if len(content) <= max_length:
        return content
    
    logger.warning(f"متن از {max_length} کاراکتر بیشتر است، در حال کوتاه کردن...")
    
    # اگر متن خیلی طولانی است، از انتها کوتاه کن اما اولویت با حفظ ابتدای متن است
    # چون اطلاعات مهم در ابتدای متن هستند
    if len(content) > max_length:
        # حفظ 90% ابتدای متن و کوتاه کردن از انتها
        preserve_length = int(max_length * 0.9)
        if preserve_length > 100:
            preserved_content = content[:preserve_length]
            # اضافه کردن نشانه کوتاه‌شدن
            return preserved_content + "..."
        else:
            return content[:max_length - 3] + "..."
    
    return content

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
    
    # اگر کپشن است، محتوای اصلی را با اولویت حفظ اطلاعات مهم کوتاه کن
    max_allowed = 1024 if is_caption else 4096
    
    # محاسبه فضای قابل استفاده برای محتوای اصلی
    available_space = max_allowed - len(FOOTER_TEMPLATE) - 10  # 10 برای فاصله و خطوط جدید
    
    if available_space < 100:  # اگر فضای کافی برای محتوای اصلی نیست
        logger.warning("فضای کافی برای محتوای اصلی نیست، فقط فوتر ارسال می‌شود")
        return FOOTER_TEMPLATE
    
    # اگر محتوای اصلی از فضای قابل استفاده بیشتر است، کوتاه کن
    if len(main_content) > available_space:
        logger.info(f"کوتاه کردن محتوا از {len(main_content)} به {available_space} کاراکتر")
        main_content = smart_truncate_with_priority(main_content, available_space, is_caption)
    
    # ترکیب محتوای اصلی با فوتر جدید
    final_content = f"{main_content}\n\n{FOOTER_TEMPLATE}"
    
    # بررسی نهایی طول
    if len(final_content) > max_allowed:
        logger.warning(f"متن نهایی هنوز از {max_allowed} کاراکتر بیشتر است، کوتاه کردن نهایی...")
        # محاسبه مجدد فضای قابل استفاده
        available_space = max_allowed - len(FOOTER_TEMPLATE) - 10
        if available_space > 100:
            main_content = smart_truncate_with_priority(main_content, available_space, is_caption)
            final_content = f"{main_content}\n\n{FOOTER_TEMPLATE}"
        else:
            final_content = FOOTER_TEMPLATE
    
    logger.info(f"✅ محتوا پردازش شد (طول: {len(final_content)} کاراکتر - حداکثر مجاز: {max_allowed})")
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
        
        # لاگ محتوای اصلی برای دیباگ
        original_content = ""
        if message.text:
            original_content = message.text
            logger.info(f"📝 متن اصلی ({len(original_content)} کاراکتر): {original_content[:300]}...")
        elif message.caption:
            original_content = message.caption
            logger.info(f"📝 کپشن اصلی ({len(original_content)} کاراکتر): {original_content[:300]}...")
        
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
        send_result = None
        if message.text and not message.media:
            send_result = await context.bot.send_message(
                chat_id=DESTINATION_CHANNEL_ID,
                text=processed_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False
            )
            logger.info("✅ پیام متنی با لینک‌های HTML ارسال شد")
        
        elif message.photo:
            send_result = await context.bot.send_photo(
                chat_id=DESTINATION_CHANNEL_ID,
                photo=message.photo[-1].file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML
            )
            logger.info("✅ عکس با کپشن و لینک‌های HTML ارسال شد")
        
        elif message.video:
            send_result = await context.bot.send_video(
                chat_id=DESTINATION_CHANNEL_ID,
                video=message.video.file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML
            )
            logger.info("✅ ویدیو با کپشن و لینک‌های HTML ارسال شد")
        
        elif message.document:
            send_result = await context.bot.send_document(
                chat_id=DESTINATION_CHANNEL_ID,
                document=message.document.file_id,
                caption=processed_text,
                parse_mode=ParseMode.HTML
            )
            logger.info("✅ فایل با کپشن و لینک‌های HTML ارسال شد")
        
        else:
            if processed_text:
                send_result = await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=processed_text,
                    parse_mode=ParseMode.HTML
                )
                logger.info("✅ متن پردازش شده با لینک‌های HTML ارسال شد")
        
        # اگر ارسال موفق بود، پیام را علامت‌گذاری کن
        if send_result:
            db.mark_message_processed(message.message_id)
            logger.info(f"🎉 پیام {message.message_id} با موفقیت پردازش و ارسال شد")
        else:
            logger.error(f"❌ ارسال پیام {message.message_id} ناموفق بود")
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش پیام: {e}")
        
        # تلاش برای ارسال بسیار ساده در صورت خطا
        try:
            logger.info("🔄 تلاش برای ارسال نسخه ساده...")
            
            # استفاده از محتوای اصلی بدون پردازش پیچیده
            simple_content = ""
            if message.text:
                simple_content = message.text
            elif message.caption:
                simple_content = message.caption
            
            # فقط جایگزینی یوزرنیم‌ها
            simple_content = replace_usernames(simple_content)
            
            # اگر محتوا خیلی طولانی است، کوتاه کردن ساده
            max_simple_length = 900 if (message.caption or message.photo or message.video) else 4000
            if len(simple_content) > max_simple_length:
                simple_content = simple_content[:max_simple_length - 100] + "\n\n...\n\n📥 ادامه مطلب در کانال اصلی"
            
            # ترکیب با فوتر
            final_simple = f"{simple_content}\n\n{FOOTER_TEMPLATE}"
            
            # اگر هنوز طولانی است، فقط فوتر را بفرست
            if len(final_simple) > max_simple_length:
                final_simple = FOOTER_TEMPLATE
            
            if message.photo:
                await context.bot.send_photo(
                    chat_id=DESTINATION_CHANNEL_ID,
                    photo=message.photo[-1].file_id,
                    caption=final_simple,
                    parse_mode=ParseMode.HTML
                )
            elif message.video:
                await context.bot.send_video(
                    chat_id=DESTINATION_CHANNEL_ID,
                    video=message.video.file_id,
                    caption=final_simple,
                    parse_mode=ParseMode.HTML
                )
            elif message.document:
                await context.bot.send_document(
                    chat_id=DESTINATION_CHANNEL_ID,
                    document=message.document.file_id,
                    caption=final_simple,
                    parse_mode=ParseMode.HTML
                )
            else:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=final_simple,
                    parse_mode=ParseMode.HTML
                )
            logger.info("✅ پست با متن ساده ارسال شد")
            db.mark_message_processed(message.message_id)
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
    logger.info("⚠️ مدیریت طول متن فعال شد (کپشن: 1024 کاراکتر، متن: 4096 کاراکتر)")
    logger.info("🔗 لینک‌های قابل کلیک فعال شدند")
    logger.info("💡 حالت ساده: تمام توضیحات اصلی حفظ می‌شوند")
    logger.info("🎯 الگوریتم جدید: اولویت با حفظ کامل محتوای اصلی")
    
    # راه‌اندازی با تنظیمات بهینه برای جلوگیری از Conflict
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        close_loop=False
    )

if __name__ == '__main__':
    main()
