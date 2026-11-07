# main.py — Entry point dùng cho Docker, Pella.app và chạy cục bộ
import os
import sys
import asyncio
import logging

# Đảm bảo thư mục gốc nằm trong sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Cấu hình logging chuyên nghiệp
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Neneka.Main")

from src.config import settings
from src.bot import bot, start_bot

async def main():
    logger.info("Khởi động Neneka Autonomous Discord AI (Princess Connect! Re:Dive)...")
    if not settings.DISCORD_TOKEN:
        logger.error("Không tìm thấy DISCORD_TOKEN trong biến môi trường hoặc file .env!")
        return

    try:
        await start_bot()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Nhận tín hiệu dừng bot, đang tiến hành dọn dẹp kết nối...")
    finally:
        if not bot.is_closed():
            await bot.close()
        logger.info("Bot đã tắt an toàn.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
