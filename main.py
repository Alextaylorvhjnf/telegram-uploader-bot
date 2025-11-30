import os
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

# ==================== تنظیمات از Environment Variables ====================
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
SOURCE_CHANNEL = int(os.getenv('SOURCE_CHANNEL', 0))
DESTINATION_CHANNEL = int(os.getenv('DESTINATION_CHANNEL', 0))
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

# ==================== جایگزینی‌های مورد نظر ====================
REPLACEMENTS = {
    '@neterplay': '@apmovienet',
    '@neterplay_Site': '@apmovienet',
    '@Oxy_Address': '@apmovienet',
    'neterplay.com': 'apmovienet.com',  # اگر دامنه هم می‌خوای عوض کنی
    '⚫️ @neterplay': '⚫️ @apmovienet',
    '🔴 @neterplay': '🔴 @apmovienet', 
    '🟡 @neterplay_Site': '🟡 @apmovienet',
    '🟢 @Oxy_Address': '🟢 @apmovienet',
    'Neterplay': 'AP Movie',
    'neterplay': 'apmovienet'
}

# ==================== تنظیمات لاگ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== کلاینت تلگرام ====================
client = TelegramClient('railway_bot', API_ID, API_HASH)

def replace_content(text):
    """جایگزینی محتوا بر اساس دیکشنری REPLACEMENTS"""
    if not text:
        return text
    
    original_text = text
    for old_text, new_text in REPLACEMENTS.items():
        text = text.replace(old_text, new_text)
    
    # لاگ تغییرات
    if text != original_text:
        logger.info("✅ متن با موفقیت ویرایش شد")
        logger.info(f"📝 تغییرات: {len(REPLACEMENTS)} جایگزینی انجام شد")
    
    return text

async def send_notification(message):
    """ارسال نوتیفیکیشن به ادمین"""
    try:
        await client.send_message(
            ADMIN_ID,
            f"🤖 ربات فعال شد!\n\n{message}"
        )
    except Exception as e:
        logger.error(f"خطا در ارسال نوتیفیکیشن: {e}")

async def process_and_forward(message):
    """پردازش و ارسال پیام"""
    try:
        logger.info(f"📨 پیام جدید دریافت شد: {message.id}")
        
        # پردازش متن و کپشن
        new_text = None
        new_caption = None
        
        if message.text:
            new_text = replace_content(message.text)
        
        if message.message:
            new_caption = replace_content(message.message)
        
        # اگر پیام فقط متن باشد
        if not message.media and (new_text or new_caption):
            content_to_send = new_text if new_text else new_caption
            await client.send_message(DESTINATION_CHANNEL, content_to_send)
            logger.info("✅ پیام متنی ارسال شد")
        
        # اگر پیام دارای مدیا باشد
        elif message.media:
            if isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
                # ارسال مدیا با کپشن جدید
                await client.send_file(
                    DESTINATION_CHANNEL,
                    message.media,
                    caption=new_caption
                )
                logger.info("✅ مدیا با کپشن ویرایش شده ارسال شد")
            else:
                # برای انواع دیگر مدیا
                await client.send_message(
                    DESTINATION_CHANNEL,
                    new_text if new_text else "پیام جدید",
                    file=message.media
                )
                logger.info("✅ پیام با مدیا ارسال شد")
        
        # ارسال تأیید به ادمین
        try:
            await client.send_message(
                ADMIN_ID,
                f"✅ پست جدید با موفقیت پردازش و ارسال شد!\n\nآیدی پست: {message.id}"
            )
        except:
            pass
            
        logger.info("✅ پیام با موفقیت پردازش و ارسال شد")
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش پیام: {e}")
        try:
            await client.send_message(
                ADMIN_ID, 
                f"❌ خطا در پردازش پیام: {str(e)[:200]}..."
            )
        except:
            pass

@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def handler(event):
    """هندلر پیام‌های جدید"""
    await process_and_forward(event.message)

async def main():
    """تابع اصلی"""
    try:
        await client.start(bot_token=BOT_TOKEN)
        
        # چک کردن اتصال
        me = await client.get_me()
        logger.info(f"🤖 ربات با نام @{me.username} راه‌اندازی شد")
        
        # چک کردن دسترسی به کانال‌ها
        try:
            source_entity = await client.get_entity(SOURCE_CHANNEL)
            dest_entity = await client.get_entity(DESTINATION_CHANNEL)
            logger.info(f"✅ اتصال به کانال‌ها تأیید شد")
            logger.info(f"📥 کانال مبدأ: {source_entity.title}")
            logger.info(f"📤 کانال مقصد: {dest_entity.title}")
        except Exception as e:
            logger.error(f"❌ خطا در اتصال به کانال‌ها: {e}")
            await client.send_message(ADMIN_ID, f"❌ خطا در اتصال به کانال‌ها: {e}")
            return
        
        # ارسال نوتیفیکیشن شروع به کار
        await send_notification(
            "ربات اتوماسیون محتوا فعال شد! 🎬\n\n"
            "📋 کارهایی که انجام می‌دهد:\n"
            "• مانیتورینگ اتوماتیک کانال مبدأ\n"
            "• جایگزینی آیدی‌ها با @apmovienet\n"
            "• ارسال خودکار به کانال مقصد\n"
            "• ارسال نوتیفیکیشن به شما\n\n"
            "🟢 ربات آماده کار است!"
        )
        
        logger.info("🟢 ربات آماده کار است و در حال مانیتورینگ...")
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"❌ خطای جدی در ربات: {e}")
        try:
            await client.send_message(ADMIN_ID, f"❌ ربات متوقف شد: {e}")
        except:
            pass

if __name__ == '__main__':
    # چک کردن وجود تمام متغیرهای محیطی
    required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN', 'SOURCE_CHANNEL', 'DESTINATION_CHANNEL', 'ADMIN_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ متغیرهای محیطی زیر تنظیم نشده‌اند: {missing_vars}")
        exit(1)
    
    # راه‌اندازی ربات
    logger.info("🚀 در حال راه‌اندازی ربات...")
    client.loop.run_until_complete(main())
