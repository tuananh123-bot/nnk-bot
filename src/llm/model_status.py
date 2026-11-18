# src/llm/model_status.py
"""
Quản lý và báo cáo thông tin các mô hình AI (Bot Thường & Bot NSFW) đang chạy trong hệ thống Neneka.
"""

from typing import Dict, Any, Optional
import discord

from src.config import settings
from src.llm.venice_client import get_venice_client, get_uncensored_ai_client
from src.llm.gemini_image_client import gemini_image_client
from src.llm.uncensored_image_client import uncensored_image_client
from src.llm.horde_client import horde_client


def get_active_models_info() -> Dict[str, Any]:
    """
    Thu thập thông tin chi tiết về các mô hình Bot Thường và Bot NSFW đang hoạt động.
    """
    # 1. Bot Thường (Normal LLM)
    has_groq = bool(settings.GROQ_API_KEY and len(settings.GROQ_API_KEY) > 10)
    normal_model = settings.GROQ_MODEL
    normal_fallbacks = settings.GROQ_FALLBACK_MODELS

    # 2. Bot NSFW (Uncensored LLM)
    v_client = get_venice_client()
    has_notrack = bool(v_client and v_client.is_available())
    notrack_model = getattr(settings, "NOTRACK_DEFAULT_MODEL", "notrack-uncensored")

    uai_client = get_uncensored_ai_client()
    has_uncensored = bool(uai_client and uai_client.is_available())
    uncensored_model = getattr(settings, "UNCENSORED_CHAT_MODEL", "deepseek-v4-1-flash-uncensored")

    has_horde = horde_client.is_available()

    # 3. Image Gen Models
    has_gemini = gemini_image_client.is_available()
    gemini_img_model = getattr(settings, "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    uai_img_model = getattr(settings, "UNCENSORED_IMAGE_MODEL", "seedream-v5")

    return {
        "normal_bot": {
            "name": "Groq LPU Acceleration",
            "provider": "Groq Cloud",
            "active_model": normal_model,
            "fallback_models": normal_fallbacks,
            "status": "🟢 Đang chạy" if has_groq else "🔴 Chưa kích hoạt",
            "is_available": has_groq,
        },
        "nsfw_bot": {
            "primary": {
                "name": "NoTrack AI",
                "model": notrack_model,
                "base_url": getattr(settings, "NOTRACK_BASE_URL", "https://api.notrack.ai/v1"),
                "status": "🟢 Đang chạy (Ưu tiên 1)" if has_notrack else "🔴 Không khả dụng",
                "is_available": has_notrack,
            },
            "secondary": {
                "name": "Uncensored AI",
                "model": uncensored_model,
                "base_url": getattr(settings, "UNCENSORED_BASE_URL", "https://api.uncensored.com/api/v1"),
                "status": "🟡 Sẵn sàng (Dự phòng 2)" if has_uncensored else "🔴 Không khả dụng",
                "is_available": has_uncensored,
            },
            "tertiary": {
                "name": "AI Horde Distributed",
                "model": "Horde Text Models",
                "status": "🟢 Sẵn sàng (Dự phòng 3)" if has_horde else "⚪ Không cấu hình",
                "is_available": has_horde,
            },
        },
        "image_bot": {
            "normal": {
                "name": "Google Nano Banana 🍌",
                "model": gemini_img_model,
                "status": "🟢 Đang chạy" if has_gemini else "🔴 Chưa kích hoạt",
            },
            "nsfw": {
                "name": "Uncensored AI Image",
                "model": uai_img_model,
                "status": "🟢 Đang chạy" if has_uncensored else "🔴 Chưa kích hoạt",
            },
        },
    }


def build_model_status_embed(is_channel_nsfw: bool = False) -> discord.Embed:
    """
    Tạo Embed Discord trực quan hiển thị trạng thái các mô hình đang chạy.
    """
    info = get_active_models_info()
    nb = info["normal_bot"]
    ns = info["nsfw_bot"]
    img = info["image_bot"]

    channel_mode_badge = "🔞 Kênh NSFW (Đang Bật)" if is_channel_nsfw else "🕊️ Kênh Thông Thường (Safe)"

    embed = discord.Embed(
        title="👑 Trung Tâm Điều Phối Mô Hình AI • Thất Vương Neneka",
        description=(
            f"*Hiện diện tại không gian ma thuật: **{channel_mode_badge}***\n\n"
            "> **Quy chế điều phối khi bật NSFW:**\n"
            "> - 💬 **Lời thoại thông thường:** **Bot Thường** (`" + nb["active_model"] + "`) chạy trước.\n"
            "> - 🔞 **Lời thoại 18+ / Gợi cảm:** **Bot NSFW** (`" + ns["primary"]["model"] + "`) tự động kích hoạt.\n"
            "> - 🛡️ **Bảo vệ mạch thoại:** Nếu Bot Thường gặp lỗi hoặc từ chối an toàn, hệ thống tự động chuyển tiếp sang Bot NSFW ngay lập tức."
        ),
        color=0xe74c3c if is_channel_nsfw else 0x9b59b6,
    )

    # 1. Field Bot Thường
    fallback_str = ", ".join([f"`{m}`" for m in nb["fallback_models"][:2]])
    embed.add_field(
        name="🤖 1. BOT THƯỜNG (Hội Thoại Đời Thường)",
        value=(
            f"• **Nhà cung cấp:** {nb['provider']} ({nb['status']})\n"
            f"• **Model chính:** `{nb['active_model']}`\n"
            f"• **Dự phòng:** {fallback_str}"
        ),
        inline=False,
    )

    # 2. Field Bot NSFW
    p1 = ns["primary"]
    p2 = ns["secondary"]
    p3 = ns["tertiary"]
    embed.add_field(
        name="🔞 2. BOT NSFW (Trưởng Thành / 18+ Uncensored)",
        value=(
            f"• **Ưu tiên 1:** {p1['name']} (`{p1['model']}`) — {p1['status']}\n"
            f"• **Dự phòng 2:** {p2['name']} (`{p2['model']}`) — {p2['status']}\n"
            f"• **Dự phòng 3:** {p3['name']} — {p3['status']}"
        ),
        inline=False,
    )

    # 3. Field Bot Tạo Ảnh
    embed.add_field(
        name="🎨 3. BOT VẼ TRANH & TẠO ẢNH (Image Generation)",
        value=(
            f"• **Tranh thông thường:** {img['normal']['name']} (`{img['normal']['model']}`)\n"
            f"• **Tranh 18+ / Sexy:** {img['nsfw']['name']} (`{img['nsfw']['model']}`) / AI Horde"
        ),
        inline=False,
    )

    embed.set_footer(
        text="Seven Crowns Dual-Engine Dispatcher • Princess Connect! Re:Dive"
    )
    return embed
