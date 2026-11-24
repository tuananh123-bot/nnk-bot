# discord_bot.py — Unified Entry Point (chuyển tiếp trực tiếp sang kiến trúc đa Cog hiện đại tại main.py / src.bot)
"""
Tệp tương thích ngược: Đảm bảo dù khởi chạy bằng `python main.py` hay `python discord_bot.py`
thì bot đều nạp đầy đủ 100% các tính năng mới nhất (Piano 48kHz, Đọc/Viết Code, Đọc GIF,
Custom Emoji Server, Google Nano Banana, NSFW Dual-Dispatcher & Khiên Chống Lặp).
"""

import asyncio
from main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
