# src/bot.py
import logging
import discord
from discord.ext import commands

from src.config import settings
from src.database.connection import db_manager
from src.cache.redis_client import cache

logger = logging.getLogger("Neneka.Bot")

def get_prefix(bot, message):
    """Hỗ trợ cả mention và các prefix '!n ', '!n', 'n! ', 'n!'"""
    return commands.when_mentioned_or(*settings.COMMAND_PREFIXES)(bot, message)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix=get_prefix,
    intents=intents,
    help_command=None
)

COGS = [
    "src.cogs.character",
    "src.cogs.bond",
    "src.cogs.memory",
    "src.cogs.voice",
    "src.cogs.admin",
    "src.cogs.chat"
]

@bot.event
async def setup_hook():
    """Khởi tạo Database, Redis Cache, nạp các Cogs và đồng bộ Slash Commands"""
    logger.info("Đang khởi tạo Database & Cache...")
    await db_manager.initialize()
    await cache.initialize()

    logger.info("Đang nạp các Cogs...")
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            logger.info(f"  • Đã nạp Cog: {cog}")
        except Exception as e:
            logger.error(f"  ❌ Lỗi khi nạp Cog {cog}: {e}")

    logger.info("Đang đồng bộ cây lệnh Slash Commands với Discord...")
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ Đã đồng bộ thành công {len(synced)} Slash Commands toàn cục!")
    except Exception as e:
        logger.error(f"❌ Lỗi khi đồng bộ Slash Commands: {e}")

@bot.event
async def on_ready():
    logger.info("=" * 60)
    logger.info(f"👑 NENEKA AUTONOMOUS DISCORD AI ĐÃ SẴN SÀNG: {bot.user} (ID: {bot.user.id})")
    logger.info(f"🔮 Chế độ hoạt động: {settings.AUTONOMOUS_MODE}")
    logger.info(f"📻 Kênh tự động phản hồi: {settings.auto_reply_channel_ids}")
    logger.info("=" * 60)
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="các biến số ma thuật | /chat"
        )
    )

async def start_bot():
    if not settings.DISCORD_TOKEN:
        raise RuntimeError("Chưa tìm thấy DISCORD_TOKEN trong cấu hình!")
    await bot.start(settings.DISCORD_TOKEN)
