import os
import logging
import sqlite3
import re
import asyncio
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
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== دیتابیس پیشرفته ====================
class AdvancedDB:
    def __init__(self):
        db_path = '/tmp/apmovie_bot.db' if 'RAILWAY_ENVIRONMENT' in os.environ else 'apmovie_bot.db'
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()
    
    def _init_db(self):
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS processed_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER UNIQUE,
                    source_channel_id INTEGER,
                    processed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    content_hash TEXT
                )
            ''')
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS channel_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT UNIQUE,
                    detected_count INTEGER DEFAULT 0,
                    last_detected DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
    
    def is_processed(self, message_id: int) -> bool:
        cursor = self.conn.execute(
            'SELECT 1 FROM processed_posts WHERE message_id = ? AND source_channel_id = ?',
            (message_id, SOURCE_CHANNEL_ID)
        )
        return cursor.fetchone() is not None
    
    def mark_processed(self, message_id: int, content_hash: str = None):
        try:
            self.conn.execute(
                'INSERT INTO processed_posts (message_id, source_channel_id, content_hash) VALUES (?, ?, ?)',
                (message_id, SOURCE_CHANNEL_ID, content_hash)
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass
    
    def update_pattern_stats(self, pattern: str):
        try:
            self.conn.execute('''
                INSERT INTO channel_patterns (pattern, detected_count) 
                VALUES (?, 1)
                ON CONFLICT(pattern) DO UPDATE SET 
                detected_count = detected_count + 1,
                last_detected = CURRENT_TIMESTAMP
            ''', (pattern,))
            self.conn.commit()
        except Exception as e:
            logger.error(f"خطا در آپدیت آمار پترن: {e}")

# ==================== سیستم پاکسازی هوشمند ====================
class SmartCaptionCleaner:
    def __init__(self):
        self.db = AdvancedDB()
        self._init_patterns()
    
    def _init_patterns(self):
        # الگوهای شناسایی و حذف نام کانال‌ها و تبلیغات
        self.channel_patterns = [
            # الگوهای عمومی کانال‌های فیلم
            r'@?\b(اکسی|axi|aximoovie|aximoovi|aximovie)\b',
            r'@?\b(فیلمبازان|film[bz]azan|filmbazan)\b',
            r'@?\b(فیلم|film|movie|سینما|cinema)\s*[\.\-_]*(خانه|home|کانال|channel|باشگاه|club)\b',
            r'@?\b(دانلود|download|دیدن|watch)\s*فیلم\b',
            r'@?\b(کانال|channel)\s*(فیلم|movie)\b',
            r'@?\b(عضویت|subscribe)\s*(در|in)\s*کانال\b',
            r'@?\b(فیلم|movie)\s*(رایگان|free)\b',
            
            # الگوهای عمومی تبلیغات
            r'@\w+',  # تمام یوزرنیم‌ها
            r'https?://\S+',  # تمام لینک‌ها
            r'#\w+',  # تمام هشتگ‌ها
            
            # الگوهای HTML و Markdown
            r'<a\b[^>]*>', r'</a>',
            r'\[.*?\]\(.*?\)',
            
            # الگوهای متنی تبلیغاتی
            r'برای\s+دانلود\s+بیشتر',
            r'به\s+کانال\s+ما\s+بپیوندید',
            r'لینک\s+کانال\s+در\s+بیو',
            r'telegram\.me/\w+',
            r't\.me/\w+',
            r'joinchat/\w+',
        ]
        
        # الگوهای حفظ اطلاعات فیلم
        self.movie_info_patterns = [
            r'عنوان:?\s*(.+)',
            r'نام\s*فیلم:?\s*(.+)',
            r'کارگردان:?\s*(.+)',
            r'بازیگران:?\s*(.+)',
            r'ژانر:?\s*(.+)',
            r'سال\s*تولید:?\s*(\d{4})',
            r'محصول\s*کشور:?\s*(.+)',
            r'امتیاز:?\s*(.+)',
            r'کیفیت:?\s*(.+)',
            r'زبان:?\s*(.+)',
            r'زیرنویس:?\s*(.+)',
            r'خلاصه\s*داستان:?\s*(.+)',
            r'مدت\s*زمان:?\s*(.+)',
            r'سایز:?\s*(.+)',
        ]
    
    def intelligent_clean(self, text: str) -> str:
        """پاکسازی هوشمند کپشن با حفظ اطلاعات فیلم"""
        if not text or not text.strip():
            return ""
        
        original_text = text
        logger.info(f"شروع پاکسازی متن با طول {len(text)} کاراکتر")
        
        # مرحله 1: حذف الگوهای شناخته شده
        for pattern in self.channel_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.UNICODE)
            if matches:
                text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.UNICODE)
                for match in matches:
                    if isinstance(match, str) and len(match.strip()) > 2:
                        self.db.update_pattern_stats(match.strip())
                        logger.info(f"حذف شد: {match.strip()}")
        
        # مرحله 2: استخراج و حفظ اطلاعات فیلم
        movie_info = self._extract_movie_info(original_text)
        
        # مرحله 3: پاکسازی نهایی
        text = self._final_cleanup(text)
        
        # مرحله 4: اگر اطلاعات فیلم استخراج شد، از آن استفاده کن
        if movie_info and len(movie_info) > 50:
            final_text = movie_info
            logger.info("استفاده از اطلاعات استخراج شده فیلم")
        else:
            final_text = text
            logger.info("استفاده از متن پاکسازی شده")
        
        # مرحله 5: اگر متن خیلی کوتاه شد، از متن اصلی با حداقل پاکسازی استفاده کن
        if len(final_text.strip()) < 50 and len(original_text) > 100:
            logger.warning("متن پس از پاکسازی خیلی کوتاه شد، استفاده از پاکسازی حداقلی")
            final_text = self._minimal_clean(original_text)
        
        logger.info(f"پاکسازی کامل شد. طول نهایی: {len(final_text)} کاراکتر")
        return final_text.strip()
    
    def _extract_movie_info(self, text: str) -> str:
        """استخراج هوشمند اطلاعات فیلم"""
        info_lines = []
        
        for pattern in self.movie_info_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.UNICODE)
            for match in matches:
                if match and len(match.strip()) > 2:
                    line = f"• {match.strip()}"
                    if line not in info_lines:
                        info_lines.append(line)
        
        # استخراج پاراگراف‌های طولانی (احتمالاً خلاصه داستان)
        paragraphs = re.split(r'\n\s*\n', text)
        for para in paragraphs:
            para = para.strip()
            if (len(para) > 100 and 
                not re.search(r'@|http|#|کانال|فیلم|دانلود', para, re.IGNORECASE) and
                len(re.findall(r'\w+', para)) > 15):
                info_lines.append(f"📖 خلاصه داستان:\n{para}")
                break
        
        return '\n'.join(info_lines) if info_lines else ""
    
    def _final_cleanup(self, text: str) -> str:
        """پاکسازی نهایی متن"""
        # حذف خطوط خالی و تکراری
        lines = text.split('\n')
        unique_lines = []
        seen_lines = set()
        
        for line in lines:
            clean_line = line.strip()
            if (clean_line and 
                len(clean_line) > 3 and 
                clean_line not in seen_lines and
                not re.match(r'^[_\-\=\.\*~]+$', clean_line)):
                unique_lines.append(clean_line)
                seen_lines.add(clean_line)
        
        # حذف فضاهای اضافی
        text = '\n'.join(unique_lines)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        return text.strip()
    
    def _minimal_clean(self, text: str) -> str:
        """پاکسازی حداقلی برای مواردی که پاکسازی اصلی خیلی تهاجمی بوده"""
        # فقط حذف لینک‌ها و یوزرنیم‌های واضح
        text = re.sub(r'@\w+', '', text)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'#\w+', '', text)
        text = re.sub(r'<a\b[^>]*>|</a>', '', text)
        text = re.sub(r'\[.*?\]\(.*?\)', '', text)
        
        # حذف خطوط تبلیغاتی مشخص
        lines = text.split('\n')
        clean_lines = []
        
        for line in lines:
            line = line.strip()
            if (line and 
                not re.search(r'کانال|فیلم|دانلود|عضویت|لینک', line, re.IGNORECASE) and
                len(line) > 5):
                clean_lines.append(line)
        
        return '\n'.join(clean_lines)

# ==================== سیستم ارسال هوشمند ====================
class SmartPostSender:
    def __init__(self):
        self.cleaner = SmartCaptionCleaner()
    
    async def send_media_with_caption(self, context, message, original_caption: str):
        """ارسال هوشمند مدیا با کپشن"""
        # پاکسازی کپشن
        clean_caption = self.cleaner.intelligent_clean(original_caption)
        
        # اضافه کردن فوتر
        if clean_caption:
            final_text = f"{clean_caption}\n\n{FOOTER_TEMPLATE}"
        else:
            final_text = FOOTER_TEMPLATE
        
        try:
            # اگر کپشن کوتاه است، مستقیماً ارسال کن
            if len(final_text) <= 1024:
                if message.photo:
                    await context.bot.send_photo(
                        chat_id=DESTINATION_CHANNEL_ID,
                        photo=message.photo[-1].file_id,
                        caption=final_text,
                        parse_mode=ParseMode.HTML,
                        read_timeout=30,
                        write_timeout=30
                    )
                elif message.video:
                    await context.bot.send_video(
                        chat_id=DESTINATION_CHANNEL_ID,
                        video=message.video.file_id,
                        caption=final_text,
                        parse_mode=ParseMode.HTML,
                        read_timeout=30,
                        write_timeout=30
                    )
                elif message.document:
                    await context.bot.send_document(
                        chat_id=DESTINATION_CHANNEL_ID,
                        document=message.document.file_id,
                        caption=final_text,
                        parse_mode=ParseMode.HTML,
                        read_timeout=30,
                        write_timeout=30
                    )
                else:
                    await context.bot.send_message(
                        chat_id=DESTINATION_CHANNEL_ID,
                        text=final_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                
                logger.info("✅ مدیا با کپشن ارسال شد")
                return True
                
            else:
                # اگر کپشن طولانی است، اول مدیا سپس کپشن
                if message.photo:
                    media_msg = await context.bot.send_photo(
                        chat_id=DESTINATION_CHANNEL_ID,
                        photo=message.photo[-1].file_id,
                        read_timeout=30,
                        write_timeout=30
                    )
                elif message.video:
                    media_msg = await context.bot.send_video(
                        chat_id=DESTINATION_CHANNEL_ID,
                        video=message.video.file_id,
                        read_timeout=30,
                        write_timeout=30
                    )
                elif message.document:
                    media_msg = await context.bot.send_document(
                        chat_id=DESTINATION_CHANNEL_ID,
                        document=message.document.file_id,
                        read_timeout=30,
                        write_timeout=30
                    )
                else:
                    media_msg = None
                
                # ارسال کپشن به عنوان پاسخ
                if media_msg:
                    await context.bot.send_message(
                        chat_id=DESTINATION_CHANNEL_ID,
                        text=final_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                        reply_to_message_id=media_msg.message_id,
                        read_timeout=30,
                        write_timeout=30
                    )
                    logger.info("✅ مدیا و کپشن جداگانه ارسال شد")
                    return True
                    
        except Exception as e:
            logger.error(f"❌ خطا در ارسال: {str(e)}")
            return False
        
        return False

# ==================== هندلر اصلی ====================
smart_sender = SmartPostSender()
db = AdvancedDB()

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر هوشمند پست‌های کانال"""
    if not update.channel_post:
        return
    
    msg = update.channel_post
    
    # بررسی کانال مبدأ
    if msg.chat.id != SOURCE_CHANNEL_ID:
        return
    
    # بررسی تکراری نبودن
    if db.is_processed(msg.message_id):
        logger.info(f"⏭️ پست {msg.message_id} قبلاً پردازش شده")
        return
    
    logger.info(f"🔄 پردازش پست جدید: {msg.message_id}")
    
    try:
        # دریافت کپشن اصلی
        original_caption = (msg.caption or msg.text or "").strip()
        logger.info(f"📝 کپشن اصلی ({len(original_caption)} کاراکتر): {original_caption[:100]}...")
        
        # ارسال پست
        success = await smart_sender.send_media_with_caption(context, msg, original_caption)
        
        if success:
            db.mark_processed(msg.message_id)
            logger.info(f"✅ پست {msg.message_id} با موفقیت ارسال شد")
        else:
            logger.error(f"❌ خطا در ارسال پست {msg.message_id}")
            
    except Exception as e:
        logger.error(f"🔥 خطای جدی در پردازش پست {msg.message_id}: {str(e)}")

# ==================== راه‌اندازی ====================
def main():
    """تابع اصلی راه‌اندازی ربات"""
    # ایجاد اپلیکیشن
    app = Application.builder().token(BOT_TOKEN).build()
    
    # افزودن هندلر
    app.add_handler(MessageHandler(
        filters.Chat(chat_id=SOURCE_CHANNEL_ID) & filters.UpdateType.CHANNEL_POSTS,
        channel_post_handler
    ))
    
    # اطلاعات راه‌اندازی
    logger.info("🎬 ربات اپی‌مووی راه‌اندازی شد")
    logger.info("🧠 سیستم پاکسازی هوشمند فعال")
    logger.info("📥 کانال مبدأ: %s", SOURCE_CHANNEL_ID)
    logger.info("📤 کانال مقصد: %s", DESTINATION_CHANNEL_ID)
    logger.info("🔄 منتظر پست‌های جدید...")
    
    # راه‌اندازی ربات
    try:
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            poll_interval=1,
            timeout=30
        )
    except Exception as e:
        logger.error(f"🚨 خطای کلی در اجرای ربات: {e}")
        # راه‌اندازی مجدد پس از 10 ثانیه
        import time
        time.sleep(10)
        main()

if __name__ == '__main__':
    main()
