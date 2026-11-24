# src/utils/emoji_manager.py
"""
Quản lý & đồng bộ Custom Discord Emoji từ máy chủ nguồn (ưu tiên số 1: ID 1169588792064217159, kèm các server nguồn phụ).
- Tự động lấy toàn bộ emoji tĩnh (<:name:id>) và emoji động (<a:name:id>) từ các server nguồn mà bot tham gia.
- Đưa danh sách emoji phù hợp vào System Prompt để Neneka thả biểu cảm tự nhiên khi chat.
- Tự động chuyển đổi shortcode `:emoji_name:` do LLM viết thành định dạng chuẩn `<:emoji_name:id>` của Discord
  (bỏ qua các đoạn nằm trong khối code ```...```).
"""

import random
import re
import logging
from typing import Dict, List, Optional, Any
import discord

from src.config import settings

logger = logging.getLogger("Neneka.EmojiManager")


class EmojiManager:
    """Quản lý kho Custom Emoji từ server nguồn (1169588792064217159, ...) và server hiện tại."""

    def _collect_guild_emojis(self, guild: Optional[discord.Guild]) -> List[discord.Emoji]:
        if not guild or not getattr(guild, "emojis", None):
            return []
        return [e for e in guild.emojis if getattr(e, "available", True)]

    @staticmethod
    def format_discord_emoji(emoji: discord.Emoji) -> str:
        """Định dạng chuẩn Discord tag cho emoji tĩnh hoặc động."""
        prefix = "a" if getattr(emoji, "animated", False) else ""
        return f"<{prefix}:{emoji.name}:{emoji.id}>"

    def get_configured_guild_ids(self) -> List[int]:
        """Lấy danh sách ID các server nguồn emoji theo thứ tự ưu tiên."""
        if hasattr(settings, "emoji_source_guild_ids"):
            ids = settings.emoji_source_guild_ids
            if ids:
                return ids
        raw = str(getattr(settings, "EMOJI_SOURCE_GUILD_ID", "1169588792064217159")).strip()
        return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]

    def get_source_guilds(self, bot: Optional[discord.Client]) -> List[discord.Guild]:
        """Lấy danh sách các đối tượng Guild nguồn mà bot hiện đang tham gia (theo đúng thứ tự ưu tiên)."""
        if not bot:
            return []
        guilds: List[discord.Guild] = []
        for gid in self.get_configured_guild_ids():
            g = bot.get_guild(gid)
            if g is not None:
                guilds.append(g)
        return guilds

    def get_source_guild(self, bot: Optional[discord.Client]) -> Optional[discord.Guild]:
        """Trả về Guild nguồn ưu tiên cao nhất đang kết nối (tương thích ngược)."""
        guilds = self.get_source_guilds(bot)
        return guilds[0] if guilds else None

    def get_available_emoji_map(
        self,
        bot: Optional[discord.Client],
        current_guild_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Trả về dict ánh xạ {emoji_name_lower: '<:name:id>' hoặc '<a:name:id>'}.
        Ưu tiên cao nhất: Server đầu tiên trong EMOJI_SOURCE_GUILD_ID (1169588792064217159).
        """
        emoji_map: Dict[str, str] = {}
        if not bot:
            return emoji_map

        # 1. Nạp server hiện tại trước (ưu tiên thấp nhất)
        if current_guild_id and str(current_guild_id).isdigit():
            curr_guild = bot.get_guild(int(current_guild_id))
            for e in self._collect_guild_emojis(curr_guild):
                emoji_map[e.name.lower()] = self.format_discord_emoji(e)

        # 2. Nạp các server nguồn từ cuối lên đầu để server đầu tiên (1169588792064217159) có ưu tiên cao nhất
        source_guilds = self.get_source_guilds(bot)
        for g in reversed(source_guilds):
            for e in self._collect_guild_emojis(g):
                emoji_map[e.name.lower()] = self.format_discord_emoji(e)

        return emoji_map

    def build_emoji_prompt_guide(
        self,
        bot: Optional[discord.Client],
        current_guild_id: Optional[str] = None,
        is_coding: bool = False,
    ) -> str:
        """
        Tạo hướng dẫn sử dụng emoji tự nhiên cho System Prompt.
        """
        if is_coding:
            return (
                "\n\n### QUY TẮC EMOJI KHI VIẾT/ĐỌC CODE:\n"
                "- Chỉ dùng tối đa 1 emoji ở lời chào/nhận xét bên ngoài. TUYỆT ĐỐI KHÔNG chèn custom emoji vào bên trong khối ```code```."
            )

        source_guilds = self.get_source_guilds(bot)
        active_emojis: List[discord.Emoji] = []
        seen_ids = set()
        for g in source_guilds:
            for e in self._collect_guild_emojis(g):
                if e.id not in seen_ids:
                    seen_ids.add(e.id)
                    active_emojis.append(e)

        # Nếu chưa vào server nguồn nào thì lấy tạm emoji của server hiện tại
        if not active_emojis and bot and current_guild_id and str(current_guild_id).isdigit():
            active_emojis = self._collect_guild_emojis(bot.get_guild(int(current_guild_id)))

        if active_emojis:
            expressive_keywords = (
                "neneka", "smug", "laugh", "hehe", "smile", "cute", "love", "heart",
                "blush", "shy", "pat", "hug", "wink", "sip", "tea", "think", "hmm",
                "angry", "pout", "cry", "sob", "wow", "peek", "wave", "hi", "ok", "yay", "happy"
            )
            prioritized = [e for e in active_emojis if any(k in e.name.lower() for k in expressive_keywords)]
            others = [e for e in active_emojis if e not in prioritized]
            if len(others) > max(0, 40 - len(prioritized)):
                others = random.sample(others, max(0, 40 - len(prioritized)))
            selected = (prioritized + others)[:40]
            formatted_list = " ".join(self.format_discord_emoji(e) for e in selected)

            guild_label = ", ".join(g.name for g in source_guilds) if source_guilds else "Server Discord"
            return (
                f"\n\n### BIỂU CẢM & CUSTOM EMOJI TỪ SERVER ({guild_label}):\n"
                f"- Danh sách custom emoji có sẵn để dùng khi chat: {formatted_list}\n"
                f"- CÁCH DÙNG TỰ NHIÊN: Chèn 1–2 custom emoji phù hợp với tâm trạng câu nói (phải giữ nguyên chuỗi `<:tên:id>` hoặc `<a:tên:id>` như danh sách trên, hoặc dùng thêm emoji cơ bản ✨💜😄 khi hợp ngữ cảnh).\n"
                f"- Không spam quá nhiều emoji trong một câu và KHÔNG tự bịa ra tên `:emoji:` không có trong danh sách."
            )

        return (
            "\n\n### BIỂU CẢM & EMOJI KHI TRÒ CHUYỆN:\n"
            "- Chèn nhẹ nhàng 1–2 emoji tự nhiên hợp ngữ cảnh Discord (ví dụ: 😄, ✨, 💜, 😉, 🤔, 👀, ☕, 😭, 🔥) để câu chuyện sinh động, gần gũi như người thật đang nhắn tin. Không lạm dụng quá đà."
        )

    def resolve_emojis_in_reply(
        self,
        text: str,
        bot: Optional[discord.Client],
        current_guild_id: Optional[str] = None,
    ) -> str:
        """
        Hậu xử lý phản hồi:
        - Bảo toàn tuyệt đối nội dung bên trong khối ```code``` và `inline code`.
        - Tự động chuyển các `:emoji_name:` hợp lệ thành `<:emoji_name:id>` / `<a:emoji_name:id>` từ server 1169588792064217159.
        - Sửa các tag `<:name:sai_id>` về đúng ID thật của server nếu trùng tên.
        """
        if not text:
            return text

        emoji_map = self.get_available_emoji_map(bot, current_guild_id=current_guild_id)
        code_pattern = re.compile(r"(```[\s\S]*?```|`[^`\n]+`)")
        segments = code_pattern.split(text)

        def _replace_segment(seg: str) -> str:
            if not emoji_map:
                return seg

            def _fix_full_tag(m: re.Match) -> str:
                name = m.group(2)
                mapped = emoji_map.get(name.lower())
                return mapped if mapped else m.group(0)

            seg = re.sub(r"<(a?):([a-zA-Z0-9_]{2,32}):(\d+)>", _fix_full_tag, seg)

            def _replace_shortcode(m: re.Match) -> str:
                name = m.group(1)
                mapped = emoji_map.get(name.lower())
                if mapped:
                    return mapped
                for ename, etag in emoji_map.items():
                    if len(name) >= 3 and (ename.endswith(f"_{name.lower()}") or ename.startswith(f"{name.lower()}_")):
                        return etag
                if "_" in name:
                    return ""
                return m.group(0)

            seg = re.sub(r"(?<![<\w:/]):([a-zA-Z][a-zA-Z0-9_]{1,31}):(?!\d+>)", _replace_shortcode, seg)
            return seg

        processed = []
        for idx, seg in enumerate(segments):
            if idx % 2 == 1:
                processed.append(seg)
            else:
                processed.append(_replace_segment(seg))

        return "".join(processed)

    def get_status_info(self, bot: Optional[discord.Client]) -> Dict[str, Any]:
        """Trả về thông tin kết nối tới các máy chủ Emoji nguồn (ưu tiên 1169588792064217159)."""
        configured_ids = self.get_configured_guild_ids()
        primary_id = str(configured_ids[0]) if configured_ids else "1169588792064217159"
        invite_url = getattr(settings, "EMOJI_SOURCE_INVITE_URL", "https://discord.gg/BJTm5Zsjm")

        source_guilds = self.get_source_guilds(bot)
        connected_ids = {g.id for g in source_guilds}
        missing_ids = [str(gid) for gid in configured_ids if gid not in connected_ids]

        all_emojis: List[discord.Emoji] = []
        seen = set()
        for g in source_guilds:
            for e in self._collect_guild_emojis(g):
                if e.id not in seen:
                    seen.add(e.id)
                    all_emojis.append(e)

        static_count = sum(1 for e in all_emojis if not e.animated)
        anim_count = sum(1 for e in all_emojis if e.animated)

        bot_invite_url = None
        if bot and getattr(bot, "user", None):
            perms = discord.Permissions(
                read_messages=True,
                send_messages=True,
                external_emojis=True,
                use_external_emojis=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
            )
            bot_invite_url = discord.utils.oauth_url(bot.user.id, permissions=perms)

        return {
            "guild_id": primary_id,
            "configured_guild_ids": [str(x) for x in configured_ids],
            "missing_guild_ids": missing_ids,
            "server_invite": invite_url,
            "connected": len(source_guilds) > 0,
            "guild_name": ", ".join(f"{g.name} ({g.id})" for g in source_guilds) if source_guilds else None,
            "total_emojis": len(all_emojis),
            "static_count": static_count,
            "animated_count": anim_count,
            "sample_preview": " ".join(self.format_discord_emoji(e) for e in all_emojis[:24]),
            "bot_oauth_invite": bot_invite_url,
        }


emoji_manager = EmojiManager()
