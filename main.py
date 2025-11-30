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
    """پردازش کامل محتوا و اضافه کردن فوتر ثابت - نسخه بسیار ساده"""
    if not original_text:
        return FOOTER_TEMPLATE
    
    logger.info(f"🔍 شروع پردازش محتوا (طول اصلی: {len(original_text)} کاراکتر)")
    
    # پاک کردن فوترهای قدیمی
    main_content = clean_old_footer(original_text)
    logger.info(f"📝 پس از پاک کردن فوتر قدیمی: {len(main_content)} کاراکتر")
    
    # جایگزینی یوزرنیم‌ها
    main_content = replace_usernames(main_content)
    
    # فرار کردن کاراکترهای HTML در محتوای اصلی
    main_content = escape_html(main_content)
    
    # محدودیت‌های تلگرام
    max_allowed = 1024 if is_caption else 4096
    logger.info(f"📏 محدودیت مجاز: {max_allowed} کاراکتر (کپشن: {is_caption})")
    
    # طول فوتر
    footer_length = len(FOOTER_TEMPLATE)
    space_needed = footer_length + 5  # 5 برای فاصله و خطوط جدید
    
    logger.info(f"📊 طول فوتر: {footer_length} کاراکتر")
    logger.info(f"📊 فضای مورد نیاز: {space_needed} کاراکتر")
    logger.info(f"📊 طول محتوای اصلی: {len(main_content)} کاراکتر")
    
    # محاسبه طول کل
    total_length = len(main_content) + space_needed
    logger.info(f"📊 طول کل پیش‌بینی شده: {total_length} کاراکتر")
    
    # اگر کل محتوا از حد مجاز کمتر است، بدون تغییر برگردان
    if total_length <= max_allowed:
        final_content = f"{main_content}\n\n{FOOTER_TEMPLATE}"
        logger.info(f"✅ محتوای کامل قابل ارسال است (طول نهایی: {len(final_content)} کاراکتر)")
        return final_content
    
    # اگر نیاز به کوتاه کردن داریم
    available_space = max_allowed - space_needed
    logger.warning(f"⚠️ نیاز به کوتاه کردن: {len(main_content)} → {available_space} کاراکتر")
    
    if available_space < 100:  # حداقل فضای مورد نیاز برای محتوا
        logger.error("❌ فضای کافی برای محتوای اصلی وجود ندارد")
        # حتی الامکان خلاصه‌ای از محتوا را حفظ کن
        if len(main_content) > 200:
            # حفظ 200 کاراکتر اول که شامل مهمترین اطلاعات است
            short_content = main_content[:200] + "..."
            final_content = f"{short_content}\n\n{FOOTER_TEMPLATE}"
            return final_content
        else:
            return FOOTER_TEMPLATE
    
    # کوتاه کردن بسیار ساده - حفظ 95% از محتوای اصلی
    preserve_ratio = 0.95
    target_length = int(available_space * preserve_ratio)
    
    if len(main_content) > target_length:
        # کوتاه کردن از انتهای متن، اما مطمئن شو که خلاصه داستان حفظ شود
        summary_keywords = ['🎞خلاصه داستان', 'خلاصه داستان:', '🎬خلاصه فیلم', '📺خلاصه سریال']
        has_summary = any(keyword in main_content for keyword in summary_keywords)
        
        if has_summary:
            # اگر خلاصه داستان وجود دارد، آن را کامل حفظ کن
            for keyword in summary_keywords:
                if keyword in main_content:
                    summary_start = main_content.find(keyword)
                    # بخش قبل از خلاصه
                    before_summary = main_content[:summary_start]
                    # بخش خلاصه
                    summary_section = main_content[summary_start:]
                    
                    # فضای موجود برای بخش قبل از خلاصه
                    space_for_before = target_length - len(summary_section) - 50  # 50 برای حاشیه امن
                    
                    if space_for_before > 100:
                        # کوتاه کردن بخش قبل از خلاصه
                        before_summary_short = before_summary[:space_for_before] + "..."
                        main_content = before_summary_short + summary_section
                    else:
                        # اگر فضای کافی نیست، فقط خلاصه را نگه دار
                        main_content = summary_section[:target_length - 3] + "..."
                    break
        else:
            # اگر خلاصه داستان نیست، ساده کوتاه کن
            main_content = main_content[:target_length - 3] + "..."
    
    final_content = f"{main_content}\n\n{FOOTER_TEMPLATE}"
    
    # بررسی نهایی
    if len(final_content) > max_allowed:
        logger.warning(f"📏 طول نهایی {len(final_content)} از {max_allowed} بیشتر است، کوتاه کردن نهایی")
        # کوتاه کردن مستقیم
        overflow = len(final_content) - max_allowed
        main_content = main_content[:len(main_content) - overflow - 3] + "..."
        final_content = f"{main_content}\n\n{FOOTER_TEMPLATE}"
    
    logger.info(f"🎉 پردازش کامل شد (طول نهایی: {len(final_content)}/{max_allowed} کاراکتر)")
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
        
        # لاگ محتوای اصلی
        original_content = ""
        if message.text:
            original_content = message.text
        elif message.caption:
            original_content = message.caption
        
        logger.info(f"📝 محتوای اصلی ({len(original_content)} کاراکتر):")
        logger.info("─" * 50)
        logger.info(original_content)
        logger.info("─" * 50)
        
        processed_text = None
        is_caption = False
        
        if message.text:
            processed_text = process_content(message.text, is_caption=False)
        elif message.caption:
            processed_text = process_content(message.caption, is_caption=True)
            is_caption = True
        
        if not processed_text:
            processed_text = FOOTER_TEMPLATE
        
        logger.info(f"📝 محتوای پردازش شده ({len(processed_text)} کاراکتر):")
        logger.info("─" * 50)
        logger.info(processed_text)
        logger.info("─" * 50)

        # ارسال به کانال مقصد
        try:
            if message.text and not message.media:
                await context.bot.send_message(
                    chat_id=DESTINATION_CHANNEL_ID,
                    text=processed_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False
                )
                logger.info("✅ پیام متنی ارسال شد")
            
            elif message.photo:
                await context.bot.send_photo(
                    chat_id=DESTINATION_CHANNEL_ID,
                    photo=message.photo[-1].file_id,
                    caption=processed_text,
                    parse_mode=ParseMode.HTML
                )
                logger.info("✅ عکس با کپشن ارسال شد")
            
            elif message.video:
                await context.bot.send_video(
                    chat_id=DESTINATION_CHANNEL_ID,
                    video=message.video.file_id,
                    caption=processed_text,
                    parse_mode=ParseMode.HTML
                )
                logger.info("✅ ویدیو با کپشن ارسال شد")
            
            elif message.document:
                await context.bot.send_document(
                    chat_id=DESTINATION_CHANNEL_ID,
                    document=message.document.file_id,
                    caption=processed_text,
                    parse_mode=ParseMode.HTML
                )
                logger.info("✅ فایل با کپشن ارسال شد")
            
            else:
                if processed_text and processed_text != FOOTER_TEMPLATE:
                    await context.bot.send_message(
                        chat_id=DESTINATION_CHANNEL_ID,
                        text=processed_text,
                        parse_mode=ParseMode.HTML
                    )
                    logger.info("✅ متن پردازش شده ارسال شد")
            
            db.mark_message_processed(message.message_id)
            logger.info(f"🎉 پیام {message.message_id} با موفقیت پردازش و ارسال شد")
            
        except Exception as send_error:
            logger.error(f"❌ خطا در ارسال پیام: {send_error}")
            
            # ارسال نسخه بسیار ساده به عنوان fallback
            try:
                logger.info("🔄 تلاش برای ارسال نسخه ساده...")
                simple_content = original_content[:800] + "..." if len(original_content) > 800 else original_content
                simple_content = replace_usernames(simple_content)
                simple_content = escape_html(simple_content)
                
                final_simple = f"{simple_content}\n\n{FOOTER_TEMPLATE}"
                
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
                
                db.mark_message_processed(message.message_id)
                logger.info("✅ پست با نسخه ساده ارسال شد")
                
            except Exception as fallback_error:
                logger.error(f"❌ خطا در ارسال پشتیبان: {fallback_error}")
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش پیام: {str(e)}", exc_info=True)
    
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
    logger.info("💡 الگوریتم ساده: حفظ 95% محتوای اصلی + کوتاه کردن فقط در صورت ضرورت")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        close_loop=False
    )

if __name__ == '__main__':
    main()
