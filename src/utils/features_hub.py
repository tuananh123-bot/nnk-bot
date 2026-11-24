# src/utils/features_hub.py
"""
Trung Tâm Tính Năng Mới & Cẩm Nang Tương Tác Của Neneka Bot:
1. Cung cấp tri thức tự nhận thức (Self-Awareness) về toàn bộ tính năng hiện có để Neneka giới thiệu tự nhiên khi chat.
2. Hiển thị bảng "Tính Năng Mới Vừa Cập Nhật" (`/updates`, `!n updates`) kèm các nút bấm trải nghiệm tức thì.
3. Hiển thị bảng `/help` & `!n help` phân mục thông minh qua Dropdown Menu.
"""

import os
import re
from typing import Optional
import discord

from src.llm.model_status import build_model_status_embed
from src.utils.emoji_manager import emoji_manager

BOT_VERSION = "v3.6 — Metamorph Symphony & Smart Guard"

WHATS_NEW_PATTERNS = [
    r"\bcó\s+(?:gì|j)\s+mới\b",
    r"\bco\s+(?:gi|j)\s+moi\b",
    r"\b(?:gì|j)\s+mới\s+(?:không|ko|k|hông|hem|thế|vậy|nhỉ|đó|nào)\b",
    r"\b(?:tính|chức)\s+năng\s+(?:gì\s+|j\s+)?mới\b",
    r"\btinh\s+nang\s+(?:gi\s+|j\s+)?moi\b",
    r"\b(?:vừa|mới)\s+(?:được\s+|dc\s+)?(?:cập\s+nhật|update)\b",
    r"\b(?:vua|moi)\s+(?:duoc\s+|dc\s+)?(?:cap\s+nhat|update)\b",
    r"\b(?:cập\s+nhật|cap\s+nhat|update)\s+(?:gì|j|nào)?\s*mới\b",
    r"\b(?:cập\s+nhật|update)\s+(?:gì|j)\b",
    r"\blàm\s+(?:được|đc|dc)\s+(?:gì|j)\s+mới\b",
    r"\bbiết\s+làm\s+(?:gì|j)\s+mới\b",
    r"\bchangelog\b",
    r"\bwhat'?s\s+new\b",
]


def is_asking_whats_new(text: str) -> bool:
    """Nhận diện mọi cách hỏi tự nhiên & viết tắt ('có j mới', 'có gì mới ko', 'mới update j'...) về tính năng mới."""
    if not text:
        return False
    lower = text.lower().strip()
    return any(re.search(pat, lower) for pat in WHATS_NEW_PATTERNS)


def build_spoken_whats_new_reply(bot=None, current_guild_id: Optional[str] = None) -> str:
    """Lời nói trực tiếp tự nhiên của Neneka kể ra các tính năng mới vừa được cập nhật."""
    emoji_map = emoji_manager.get_available_emoji_map(bot, current_guild_id=current_guild_id)
    flair_emoji = next(iter(emoji_map.values()), "✨")
    return (
        f"Đợt này ta vừa được nâng cấp thêm kha khá phép thuật mới hay ho đấy {flair_emoji} Kể nhanh cho cậu nghe nhé:\n"
        "• 🎹 **Đàn Piano 48kHz & Tìm nhạc Piano toàn cầu:** Cậu có thể nhờ ta tạo âm tiết/gảy nốt nhạc (`/notes Đô Rê Mi Pha Sol`, cảm âm `1 2 3 5 6`) hoặc tìm bất kỳ bài nhạc tiếng Piano nào trên thế giới (`/piano <tên bài>`).\n"
        "• 💻 **Đọc file Code & Viết Code siêu tốc:** Cứ quăng thẳng file `.py`, `.js`, `.ts`, `.cpp`, `.json`... hoặc ảnh lỗi vào đây, ta đọc và viết/sửa code cho cậu ngay (`/code`).\n"
        "• 🎞️ **Đọc ảnh động GIF & Sticker:** Thả GIF Tenor/Giphy hay `.gif` là ta nhìn hiểu biểu cảm để tung hứng liền.\n"
        "• 😄 **Chat tự nhiên, nhanh hơn & thả Custom Emoji** từ server nguồn, kèm **Vẽ tranh Google Nano Banana 🍌** (`/imagine`) và **Khiên chống lặp câu**.\n\n"
        "Cậu xem chi tiết hoặc bấm nút nghe thử ngay ở bảng dưới này nhé! 👇"
    )

# Đoạn tóm tắt gọn nhẹ đưa vào System Prompt để Neneka tự biết mình làm được những gì khi người dùng hỏi chuyện
NENEKA_BOT_CAPABILITIES_PROMPT = """【NHẬN THỨC VỀ CÁC TÍNH NĂNG HIỆN TẠI CỦA NENEKA TRÊN DISCORD】
Khi người dùng hỏi cậu có tính năng gì, vừa được cập nhật gì mới, hoặc làm được những gì, hãy giới thiệu tự nhiên, hào hứng và chính xác các khả năng thực tế sau của cậu:
1. 🎹 Âm Nhạc Đại Dương Cầm & Giọng Hát:
   - Tạo âm tiết / gảy nốt nhạc trên đàn Concert Grand Piano 48kHz (`/notes` hoặc `!n notes Đô Rê Mi Pha Sol`, hỗ trợ cả `C4 E4 G4`, cảm âm số `1 2 3 5 6` và hợp âm `Cmaj Am`).
   - Tìm kiếm và phát toàn bộ bài nhạc tiếng Piano trên thế giới (`/piano <tên bài>` hoặc `!n piano`).
   - Tự sáng tác & độc tấu Piano theo tâm trạng (`/piano_compose`, `!n compose`) + Nói & hát tiếng Nhật bằng giọng Fish Audio (`/speak`, `/sing`, `/sleep`).
2. 💻 Đọc & Viết Code Free Siêu Tốc:
   - Đọc trực tiếp file code đính kèm (`.py`, `.js`, `.ts`, `.html`, `.cpp`, `.json`...), đọc ảnh chụp lỗi code, debug và viết code sạch không bị cắt cụt (`/code`, `!n code`).
3. 🎞️ Đọc Ảnh Tĩnh & Ảnh Động GIF:
   - Nhìn và bình luận trực tiếp cả ảnh thường lẫn ảnh động GIF từ Tenor, Giphy, file `.gif` và Sticker (`/vision` hoặc gửi thẳng vào kênh chat).
4. 😄 Trò Chuyện Tự Nhiên & Kho Custom Emoji Server:
   - Phản hồi tốc độ cao, tính cách gần gũi tự nhiên, thả kèm custom emoji tĩnh & động từ server nguồn (`/emojis`), hỗ trợ tiếng Việt, tiếng Anh và tiếng Nhật.
5. 🎨 Vẽ Tranh AI & Hệ Thống Gắn Kết:
   - Vẽ tranh thường bằng Google Nano Banana 🍌 (`/imagine`, `!n draw`) và tranh 18+ bằng Uncensored AI / AI Horde.
   - Xem độ hảo cảm Bond của mình hoặc người khác (`/bond @user`), đổi trang phục (`/costume`), xóa ký ức 30p/1h (`/forget`), xem thời tiết & giờ Việt Nam (`/weather`, `/time`), bói quẻ (`/fortune`) và chơi Gương Ảo Ảnh (`/mirror`)."""


def build_updates_embed() -> discord.Embed:
    """Tạo Embed giới thiệu trọn bộ các tính năng mới vừa cập nhật cho bot."""
    embed = discord.Embed(
        title=f"✨ Nhật Ký Tính Năng Mới Vừa Cập Nhật ({BOT_VERSION})",
        description=(
            "Dưới đây là toàn bộ những nâng cấp ma thuật mới nhất vừa được trang bị cho **Neneka Bot**. "
            "Cậu có thể bấm các nút bên dưới để trải nghiệm ngay lập tức! 👇"
        ),
        color=0x9b59b6,
    )
    embed.add_field(
        name="🎹 1. Đại Dương Cầm 48kHz & Kho Nhạc Piano Toàn Cầu (MỚI!)",
        value=(
            "• **Tìm mọi bài nhạc Piano:** `/piano <tên bài>` hoặc `!n piano River Flows in You` *(kèm menu chọn 5 bản thu)*.\n"
            "• **Tạo âm tiết / Gảy nốt nhạc:** `/notes` hoặc `!n notes Đô Rê Mi Pha Sol La Si Đô5` *(hỗ trợ Đô-Rê-Mi, `C4 E4 G4`, cảm âm số `1 2 3 5 6`, hợp âm `Cmaj Am`)*.\n"
            "• **Độc tấu & Sáng tác AI:** `/piano_compose` hoặc `!n compose Canon in D` *(phát thẳng vào Voice Channel không cần FFmpeg)*."
        ),
        inline=False,
    )
    embed.add_field(
        name="💻 2. Đọc File Code & Viết Code Free Siêu Tốc (MỚI!)",
        value=(
            "• Gửi thẳng file `.py`, `.js`, `.ts`, `.tsx`, `.html`, `.css`, `.cpp`, `.json`, `.sql`... hoặc dùng `/code` / `!n code`.\n"
            "• Tự động chia đoạn thông minh khi code dài > 2000 ký tự mà không làm vỡ khối ` ```code``` `."
        ),
        inline=False,
    )
    embed.add_field(
        name="🎞️ 3. Đọc Ảnh Động GIF (Tenor / Giphy / Sticker) & Vision (MỚI!)",
        value=(
            "• Thả trực tiếp GIF từ thanh GIF Discord (Tenor/Giphy), file `.gif` hoặc Sticker — Neneka trích xuất khung hình chuyển động để bắt nhịp tung hứng ngay."
        ),
        inline=False,
    )
    embed.add_field(
        name="😄 4. Chat Tự Nhiên, Custom Emoji Server & Khiên Chống Lặp (MỚI!)",
        value=(
            "• Tự nhiên, linh hoạt như người thật nhắn tin Discord + tự động thả Custom Emoji từ server `1169588792064217159` (`/emojis`).\n"
            "• **Khiên Anti-Loop & Self-Heal:** Chặn triệt để lỗi lặp câu / tự mâu thuẫn và tối ưu tốc độ phản hồi nhanh hơn 50%."
        ),
        inline=False,
    )
    embed.add_field(
        name="🎨 5. Vẽ Tranh Nano Banana 🍌, Đa Ngôn Ngữ & Quản Lý Ký Ức",
        value=(
            "• Vẽ tranh thường bằng **Google Nano Banana** (`/imagine`, `!n draw`) & 18+ bằng **Uncensored AI**.\n"
            "• Xem Bond người khác (`!n bond @user`), quên tin nhắn 30p/1h (`!n forget 30m`), chat tiếng Anh/Nhật/Việt tự động."
        ),
        inline=False,
    )
    embed.set_footer(text="Gõ /help hoặc !n help để mở cẩm nang phân loại toàn bộ lệnh • Seven Crowns AI")
    return embed


def build_help_embed(category: str = "all") -> discord.Embed:
    """Xây dựng Embed hướng dẫn lệnh theo từng chuyên mục."""
    cat = (category or "all").lower()

    if cat == "new":
        return build_updates_embed()

    embed = discord.Embed(
        title="📖 Cẩm Nang Lệnh & Tính Năng • Thất Vương Neneka",
        description="Chọn chuyên mục ở menu bên dưới để xem chi tiết từng nhóm tính năng, hoặc trò chuyện tự nhiên trực tiếp với ta nhé ✨",
        color=0x9b59b6,
    )

    if cat in ("all", "music"):
        embed.add_field(
            name="🎹 Âm Nhạc Piano, Giọng Nói & Phòng Thoại",
            value=(
                "• `/piano <bài>` | `!n piano <bài>` — Tìm & phát mọi bản nhạc tiếng Piano thế giới\n"
                "• `/notes <nốt>` | `!n notes <nốt>` — Tạo âm tiết / gảy nốt Piano 48kHz (`Đô Rê Mi`, `1 2 3 5`, `Cmaj`)\n"
                "• `/piano_compose <chủ đề>` | `!n compose` — Sáng tác / độc tấu dương cầm AI\n"
                "• `/sing [chủ đề]` | `!n sing` — Neneka hát tiếng Nhật (Fish Audio)\n"
                "• `/speak <câu>` | `!n speak` — Chuyển văn bản thành giọng nói tiếng Nhật\n"
                "• `/sleep` | `/quote` | `/radio` | `!n join` & `!n leave` — Ru ngủ, thoại gốc & Voice Channel"
            ),
            inline=False,
        )

    if cat in ("all", "code_media"):
        embed.add_field(
            name="💻 Đọc/Viết Code, Đọc GIF & Vẽ Tranh AI",
            value=(
                "• `/code <yêu cầu> [file]` | `!n code` — Viết code, sửa bug & đọc file code đính kèm\n"
                "• `/vision <ảnh>` | `!n vision` *(hoặc thả thẳng ảnh / GIF Tenor / Giphy)* — Đọc ảnh & GIF\n"
                "• `/imagine <mô tả>` | `/draw` | `!n draw` — Vẽ tranh AI (Google Nano Banana 🍌 / Uncensored AI / Horde)\n"
                "• `/emojis` | `!n emojis` — Kiểm tra kho Custom Emoji từ server `1169588792064217159`"
            ),
            inline=False,
        )

    if cat in ("all", "character"):
        embed.add_field(
            name="💜 Nhân Vật, Hảo Cảm Bond & Giải Trí",
            value=(
                "• `/bond [@user]` | `!n bond [@user]` — Xem điểm gắn kết của bạn hoặc người khác\n"
                "• `/costume [tên]` | `!n costume` — Đổi trang phục (`original`, `new_year`, `alpha`, `summer`)\n"
                "• `/fortune` (`!n fortune`) | `/mirror` (`!n mirror`) — Gieo quẻ hàng ngày & Game Gương Ảo Ảnh\n"
                "• `/weather [tỉnh]` | `/location <tỉnh>` | `/time` — Thời tiết & giờ thực tế Việt Nam\n"
                "• `/nickname` (`!n nickname`) | `/neneka` | `/story` — Đặt biệt danh & hồ sơ Canon"
            ),
            inline=False,
        )

    if cat in ("all", "system"):
        embed.add_field(
            name="⚙️ Ký Ức, Mô Hình AI & Quản Trị",
            value=(
                "• `/updates` | `!n updates` — Xem các tính năng mới vừa cập nhật\n"
                "• `/model` | `!n model` — Xem Bot Thường, Bot Code & Bot NSFW nào đang chạy\n"
                "• `/forget [30m/1h/all]` | `!n forget` | `/memory` — Xóa tin nhắn gần đây & quản lý ký ức\n"
                "• `/nsfw <enable/disable/status>` | `/lust` (`!n lust`) — Chế độ 18+ & chỉ số cảm xúc\n"
                "• `/autochat` | `/autonomous` | `/admin` | `/reload` — Quản trị kênh & nạp nóng bản cập nhật"
            ),
            inline=False,
        )

    embed.set_footer(text=f"Neneka Autonomous AI ({BOT_VERSION}) • Hỗ trợ cả Slash (/) và Prefix (!n)")
    return embed


class HelpCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Tổng Hợp Tất Cả Lệnh", value="all", emoji="🌟", description="Xem toàn bộ các nhóm lệnh chính"),
            discord.SelectOption(label="Tính Năng Mới Vừa Cập Nhật", value="new", emoji="✨", description="Xem nhật ký các nâng cấp mới nhất"),
            discord.SelectOption(label="Âm Nhạc Piano & Giọng Hát", value="music", emoji="🎹", description="Tạo âm tiết, tìm nhạc Piano, hát & Voice"),
            discord.SelectOption(label="Đọc/Viết Code, GIF & Vẽ Tranh", value="code_media", emoji="💻", description="Code, đọc GIF/Ảnh & vẽ Nano Banana"),
            discord.SelectOption(label="Hảo Cảm Bond & Giải Trí", value="character", emoji="💜", description="Bond, trang phục, bói quẻ, thời tiết"),
            discord.SelectOption(label="Ký Ức, Model & Quản Trị", value="system", emoji="⚙️", description="Forget, trạng thái Model, NSFW & Reload"),
        ]
        super().__init__(placeholder="📂 Chọn chuyên mục tính năng cần xem...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        chosen = self.values[0]
        await interaction.response.edit_message(embed=build_help_embed(chosen), view=self.view)


class HelpCategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(HelpCategorySelect())


class UpdatesInteractiveView(discord.ui.View):
    """Các nút bấm trải nghiệm nhanh ngay dưới bảng Tính Năng Mới."""

    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @discord.ui.button(label="Nghe Thử Đàn Piano", style=discord.ButtonStyle.primary, emoji="🎹")
    async def btn_try_piano(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        voice_cog = self.bot.get_cog("VoiceCog") if self.bot else None
        if not voice_cog:
            await interaction.followup.send("❌ Module âm nhạc hiện chưa sẵn sàng.", ephemeral=True)
            return
        from src.voice.piano_engine import compose_and_render_piano_melody
        from src.cogs.voice import build_piano_synth_embed
        wav_path, meta = await compose_and_render_piano_melody("River Flows in You", prefer_lyria=False)
        embed = build_piano_synth_embed(meta, subtitle="Bản dạo đầu mẫu trên đàn Concert Grand Piano 48kHz 🎹✨")
        if os.path.exists(wav_path):
            await interaction.followup.send(embed=embed, file=discord.File(wav_path, filename="neneka_demo_piano.wav"))
        else:
            await interaction.followup.send(embed=embed)

    @discord.ui.button(label="Kho Emoji Server", style=discord.ButtonStyle.secondary, emoji="😄")
    async def btn_check_emojis(self, interaction: discord.Interaction, button: discord.ui.Button):
        chat_cog = self.bot.get_cog("ChatCog") if self.bot else None
        if chat_cog and hasattr(chat_cog, "_build_emoji_status_embed"):
            await interaction.response.send_message(embed=chat_cog._build_emoji_status_embed(), ephemeral=True)
        else:
            info = emoji_manager.get_status_info(self.bot)
            await interaction.response.send_message(f"Emoji Server `{info['guild_id']}`: `{info['total_emojis']}` emojis.", ephemeral=True)

    @discord.ui.button(label="Model Đang Chạy", style=discord.ButtonStyle.secondary, emoji="🤖")
    async def btn_check_models(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=build_model_status_embed(is_channel_nsfw=False), ephemeral=True)

    @discord.ui.button(label="Mở Cẩm Nang Lệnh", style=discord.ButtonStyle.success, emoji="📖")
    async def btn_open_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=build_help_embed("all"), view=HelpCategoryView(), ephemeral=True)
