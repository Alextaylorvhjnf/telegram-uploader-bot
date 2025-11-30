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
    """پردازش کامل محتوا و اضافه کردن فوتر ثابت - نسخه ساده شده"""
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
    
    # محاسبه فضای مورد نیاز برای فوتر
    footer_length = len(FOOTER_TEMPLATE)
    space_needed = footer_length + 5  # 5 برای فاصله و خطوط جدید
    
    logger.info(f"📊 طول فوتر: {footer_length} کاراکتر")
    logger.info(f"📊 فضای مورد نیاز: {space_needed} کاراکتر")
    logger.info(f"📊 طول محتوای اصلی: {len(main_content)} کاراکتر")
    logger.info(f"📊 طول کل پیش‌بینی شده: {len(main_content) + space_needed} کاراکتر")
    
    # اگر کل محتوا از حد مجاز کمتر است، بدون تغییر برگردان
    if len(main_content) + space_needed <= max_allowed:
        final_content = f"{main_content}\n\n{FOOTER_TEMPLATE}"
        logger.info(f"✅ محتوای کامل قابل ارسال است (طول نهایی: {len(final_content)} کاراکتر)")
        return final_content
    
    # اگر محتوا نیاز به کوتاه کردن دارد
    available_space = max_allowed - space_needed
    logger.warning(f"⚠️ نیاز به کوتاه کردن: {len(main_content)} → {available_space} کاراکتر")
    
    if available_space < 50:  # اگر فضای خیلی کمی داریم
        logger.error("❌ فضای کافی برای محتوای اصلی وجود ندارد")
        return FOOTER_TEMPLATE
    
    # کوتاه کردن هوشمند - حفظ خطوط مهم
    lines = main_content.split('\n')
    preserved_lines = []
    current_length = 0
    
    # اولویت‌بندی خطوط مهم
    important_keywords = [
        '🎥دانلود فیلم', '🎥دانلود سریال', '🏅امتیاز', '📝 #', '🎙 #', 
        '🔥با هنرنمایی', '📤 کیفیت', '🔹ژانر', '⏰مدت زمان', 
        '👔کارگردان', '🌟ستارگان', '🌍محصول کشور', '🎞خلاصه داستان',
        'خلاصه داستان:', 'دانلود فیلم', 'دانلود سریال'
    ]
    
    for line in lines:
        line_length = len(line) + 1  # +1 برای کاراکتر newline
        
        # اگر خط مهم است یا فضای کافی داریم، اضافه کن
        if any(keyword in line for keyword in important_keywords) or (current_length + line_length <= available_space):
            preserved_lines.append(line)
            current_length += line_length
        else:
            # اگر خط جدید باعث превы شدن حد شود، بررسی کن
            if current_length + line_length > available_space:
                # اگر خط مهمی است، سعی کن آن را اضافه کنی
                if any(keyword in line for keyword in ['🎞خلاصه داستان', 'خلاصه داستان:']):
                    # برای خلاصه داستان، خطوط بعدی را نیز در نظر بگیر
                    summary_index = lines.index(line)
                    summary_lines = [line]
                    summary_length = line_length
                    
                    # خطوط بعدی خلاصه داستان را اضافه کن
                    for next_line in lines[summary_index + 1:]:
                        next_line_length = len(next_line) + 1
                        if summary_length + next_line_length <= available_space - current_length:
                            summary_lines.append(next_line)
                            summary_length += next_line_length
                        else:
                            break
                    
                    preserved_lines.extend(summary_lines)
                    current_length += summary_length
                    break
                else:
                    break
    
    # اگر هیچ خطی حفظ نشد، کل محتوا را به صورت ساده کوتاه کن
    if not preserved_lines:
        preserved_content = main_content[:available_space - 10] + "..."
    else:
        preserved_content = '\n'.join(preserved_lines)
        
        # اگر هنوز فضای خالی داریم، می‌توانیم خطوط بیشتری اضافه کنیم
        if current_length < available_space - 50:
            remaining_space = available_space - current_length
            # سعی کن خطوط باقیمانده را اضافه کنی
            for line in lines[len(preserved_lines):]:
                line_length = len(line) + 1
                if current_length + line_length <= available_space:
                    preserved_lines.append(line)
                    current_length += line_length
                else:
                    break
            preserved_content = '\n'.join(preserved_lines)
    
    # مطمئن شو که محتوا از حد مجاز تجاوز نمی‌کند
    if len(preserved_content) > available_space:
        preserved_content = preserved_content[:available_space - 3] + "..."
    
    final_content = f"{preserved_content}\n\n{FOOTER_TEMPLATE}"
    
    # بررسی نهایی
    if len(final_content) > max_allowed:
        logger.error(f"❌ خطا در پردازش: طول نهایی {len(final_content)} از {max_allowed} بیشتر است")
        # آخرین راه حل: کوتاه کردن مستقیم
        overflow = len(final_content) - max_allowed
        preserved_content = preserved_content[:len(preserved_content) - overflow - 3] + "..."
        final_content = f"{preserved_content}\n\n{FOOTER_TEMPLATE}"
    
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
        
        # لاگ محتوای اصلی برای دیباگ
        original_content = ""
        if message.text:
            original_content = message.text
            logger.info(f"📝 متن اصلی ({len(original_content)} کاراکتر):")
            logger.info(f"📋 محتوای اصلی:\n{original_content}")
        elif message.caption:
            original_content = message.caption
            logger.info(f"📝 کپشن اصلی ({len(original_content)} کاراکتر):")
            logger.info(f"📋 محتوای اصلی:\n{original_content}")
        
        processed_text = None
        is_caption = False
        
        if message.text:
            processed_text = process_content(message.text, is_caption=False)
            logger.info("📝 پردازش متن پیام انجام شد")
        elif message.caption:
            processed_text = process_content(message.caption, is_caption=True)
            is_caption = True
            logger.info("📝 پردازش کپشن مدیا انجام شد")
        
        if not processed_text:
            processed_text = FOOTER_TEMPLATE
        
        # لاگ تفصیلی
        logger.info(f"📊 خلاصه پردازش:")
        logger.info(f"   طول اصلی: {len(original_content)}")
        logger.info(f"   طول نهایی: {len(processed_text)}")
        logger.info(f"   نوع: {'کپشن' if is_caption else 'متن'}")

        # ارسال به کانال مقصد با فرمت HTML
        try:
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
                if processed_text and processed_text != FOOTER_TEMPLATE:
                    await context.bot.send_message(
                        chat_id=DESTINATION_CHANNEL_ID,
                        text=processed_text,
                        parse_mode=ParseMode.HTML
                    )
                    logger.info("✅ متن پردازش شده با لینک‌های HTML ارسال شد")
            
            db.mark_message_processed(message.message_id)
            logger.info(f"🎉 پیام {message.message_id} با موفقیت پردازش و ارسال شد")
            
        except Exception as send_error:
            logger.error(f"❌ خطا در ارسال پیام: {send_error}")
            raise send_error
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش پیام: {str(e)}", exc_info=True)
        
        # تلاش برای ارسال نسخه بسیار ساده
        try:
            logger.info("🔄 تلاش برای ارسال نسخه پشتیبان...")
            
            simple_content = ""
            if message.text:
                simple_content = message.text
            elif message.caption:
                simple_content = message.caption
            
            # فقط جایگزینی یوزرنیم و کوتاه کردن بسیار ساده
            simple_content = replace_usernames(simple_content)
            
            # برای کپشن‌ها محدودیت 1024 کاراکتر
            max_length = 1000 if (message.caption or message.photo or message.video) else 4000
            
            if len(simple_content) > max_length:
                # حفظ 80% ابتدای متن که شامل اطلاعات مهم است
                keep_length = int(max_length * 0.8)
                simple_content = simple_content[:keep_length] + "\n\n..."
            
            final_simple = f"{simple_content}\n\n{FOOTER_TEMPLATE}"
            
            # اگر باز هم طولانی است، فقط بخش کوچکی را نگه دار
            if len(final_simple) > max_length:
                final_simple = f"{simple_content[:300]}...\n\n{FOOTER_TEMPLATE}"
            
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
            logger.info("✅ پست با نسخه پشتیبان ارسال شد")
            
        except Exception as fallback_error:
            logger.error(f"❌ خطا در ارسال پشتیبان: {fallback_error}")
    
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
    logger.info("⚠️ مدیریت هوشمند طول متن فعال شد")
    logger.info("🎯 الگوریتم جدید: حفظ کامل اطلاعات مهم + کوتاه کردن فقط در صورت ضرورت")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        close_loop=False
    )

if __name__ == '__main__':
    main()
