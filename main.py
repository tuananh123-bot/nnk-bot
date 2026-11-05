# main.py — Entry point dùng cho pella.app và các host Python
import os
import sys

# Đảm bảo thư mục hiện tại nằm trong sys.path để import được các module cùng thư mục
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Chạy Discord Bot
from discord_bot import bot

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError(
        "Không tìm thấy DISCORD_TOKEN!\n"
        "Hãy thêm biến môi trường DISCORD_TOKEN trong trang cài đặt của pella.app."
    )

bot.run(DISCORD_TOKEN)

