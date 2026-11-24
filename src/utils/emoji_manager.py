# src/utils/emoji_manager.py
"""
Quản lý & đồng bộ Custom Discord Emoji từ máy chủ nguồn (mặc định ID: 413766882277982228 - https://discord.gg/BJTm5Zsjm).
- Tự động lấy toàn bộ emoji tĩnh (<:name:id>) và emoji động (<a:name:id>) từ server nguồn mà bot tham gia.
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
    """Quản lý kho Custom Emoji từ server nguồn (413766882277982228) và server hiện tại."""

    def _collect_guild_emojis(self, guild: Optional[discord.Guild]) -> List[discord.Emoji]:
        if not guild or not getattr(guild, "emojis", None):
            return []
        return [e for e in guild.emojis if getattr(e, "available", True)]

    @staticmethod
    def format_discord_emoji(emoji: discord.Emoji) -> str:
        """Định dạng chuẩn Discord tag cho emoji tĩnh hoặc động."""
        prefix = "a" if getattr(emoji, "animated", False) else ""
        return f"<{prefix}:{emoji.name}:{emoji.id}>"

    def get_source_guild(self, bot: Optional[discord.Client]) -> Optional[discord.Guild]:
        """Lấy đối tượng Guild nguồn emoji (ID: 413766882277982228)."""
        if not bot:
            return None
        raw_id = str(getattr(settings, "EMOJI_SOURCE_GUILD_ID", "413766882277982228")).strip()
        if not raw_id.isdigit():
            return None
        return bot.get_guild(int(raw_id))

    def get_available_emoji_map(
        self,
        bot: Optional[discord.Client],
        current_guild_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Trả về dict ánh xạ {emoji_name_lower: '<:name:id>' hoặc '<a:name:id>'}.
        Ưu tiên số 1: Emoji từ server nguồn 413766882277982228 (https://discord.gg/BJTm5Zsjm).
        Ưu tiên số 2: Emoji từ server hiện tại đang chat (nếu khác server nguồn).
        """
        emoji_map: Dict[str, str] = {}
        if not bot:
            return emoji_map

        # Nạp server hiện tại trước để server nguồn (413766882277982228) ghi đè ưu tiên cao nhất
        if current_guild_id and str(current_guild_id).isdigit():
            curr_guild = bot.get_guild(int(current_guild_id))
            for e in self._collect_guild_emojis(curr_guild):
                emoji_map[e.name.lower()] = self.format_discord_emoji(e)

        # Nạp server nguồn 413766882277982228 (ưu tiên chính)
        source_guild = self.get_source_guild(bot)
        for e in self._collect_guild_emojis(source_guild):
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

        source_guild = self.get_source_guild(bot)
        source_emojis = self._collect_guild_emojis(source_guild)

        # Nếu chưa vào server nguồn thì lấy tạm emoji của server hiện tại (nếu có)
        active_emojis = list(source_emojis)
        if not active_emojis and bot and current_guild_id and str(current_guild_id).isdigit():
            active_emojis = self._collect_guild_emojis(bot.get_guild(int(current_guild_id)))

        if active_emojis:
            # Ưu tiên các emoji biểu cảm gương mặt / cảm xúc phổ biến + lấy mẫu đa dạng (tối đa 36 emoji để tiết kiệm token)
            expressive_keywords = (
                "neneka", "smug", "laugh", "hehe", "smile", "cute", "love", "heart",
                "blush", "shy", "pat", "hug", "wink", "sip", "tea", "think", "hmm",
                "angry", "pout", "cry", "sob", "wow", "peek", "wave", "hi", "ok", "yay", "happy"
            )
            prioritized = [e for e in active_emojis if any(k in e.name.lower() for k in expressive_keywords)]
            others = [e for e in active_emojis if e not in prioritized]
            if len(others) > max(0, 36 - len(prioritized)):
                others = random.sample(others, max(0, 36 - len(prioritized)))
            selected = (prioritized + others)[:36]
            formatted_list = " ".join(self.format_discord_emoji(e) for e in selected)

            guild_label = source_guild.name if source_guild else "Server Discord"
            return (
                f"\n\n### BIỂU CẢM & CUSTOM EMOJI TỪ SERVER ({guild_label}):\n"
                f"- Danh sách custom emoji có sẵn để dùng khi chat: {formatted_list}\n"
                f"- CÁCH DÙNG TỰ NHIÊN: Chèn 1–2 custom emoji phù hợp với tâm trạng câu nói (phải giữ nguyên chuỗi `<:tên:id>` hoặc `<a:tên:id>` như danh sách trên, hoặc dùng thêm emoji cơ bản ✨💜😄 khi hợp ngữ cảnh).\n"
                f"- Không spam quá nhiều emoji trong một câu và KHÔNG tự bịa ra tên `:emoji:` không có trong danh sách."
            )

        # Fallback khi bot chưa được mời vào server emoji nguồn và đang ở DM / server không có custom emoji
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
        - Tự động chuyển các `:emoji_name:` hợp lệ thành `<:emoji_name:id>` / `<a:emoji_name:id>` từ server 413766882277982228.
        - Sửa các tag `<:name:sai_id>` về đúng ID thật của server nếu trùng tên.
        """
        if not text:
            return text

        emoji_map = self.get_available_emoji_map(bot, current_guild_id=current_guild_id)

        # Tách các đoạn code block ```...``` và inline code `...` để không bao giờ đụng vào code
        code_pattern = re.compile(r"(```[\s\S]*?```|`[^`\n]+`)")
        segments = code_pattern.split(text)

        def _replace_segment(seg: str) -> str:
            if not emoji_map:
                return seg

            # 1. Sửa các tag <:name:id> hoặc <a:name:id> nếu LLM nhớ đúng tên nhưng viết sai ID
            def _fix_full_tag(m: re.Match) -> str:
                anim, name, eid = m.group(1), m.group(2), m.group(3)
                mapped = emoji_map.get(name.lower())
                if mapped:
                    return mapped
                return m.group(0)

            seg = re.sub(r"<(a?):([a-zA-Z0-9_]{2,32}):(\d+)>", _fix_full_tag, seg)

            # 2. Chuyển đổi shortcode trần :name: (không nằm trong <...:id> và không phải URL/giờ như 10:30:00)
            def _replace_shortcode(m: re.Match) -> str:
                name = m.group(1)
                mapped = emoji_map.get(name.lower())
                if mapped:
                    return mapped
                # Nếu không khớp chính xác, thử tìm khớp một phần (ví dụ :smug: -> <:neneka_smug:123>)
                for ename, etag in emoji_map.items():
                    if len(name) >= 3 and (ename.endswith(f"_{name.lower()}") or ename.startswith(f"{name.lower()}_")):
                        return etag
                # Giữ nguyên hoặc xóa nếu rõ ràng là custom emoji bịa đặt có dấu gạch dưới
                if "_" in name:
                    return ""
                return m.group(0)

            seg = re.sub(r"(?<![<\w:/]):([a-zA-Z][a-zA-Z0-9_]{1,31}):(?!\d+>)", _replace_shortcode, seg)
            return seg

        processed = []
        for idx, seg in enumerate(segments):
            # Các phần tử lẻ (idx % 2 == 1) là khối code được tách bởi group ngoặc tròn
            if idx % 2 == 1:
                processed.append(seg)
            else:
                processed.append(_replace_segment(seg))

        return "".join(processed)

    def get_status_info(self, bot: Optional[discord.Client]) -> Dict[str, Any]:
        """Trả về thông tin kết nối tới máy chủ Emoji nguồn (413766882277982228)."""
        guild_id_str = str(getattr(settings, "EMOJI_SOURCE_GUILD_ID", "413766882277982228")).strip()
        invite_url = getattr(settings, "EMOJI_SOURCE_INVITE_URL", "https://discord.gg/BJTm5Zsjm")
        source_guild = self.get_source_guild(bot)
        emojis = self._collect_guild_emojis(source_guild)

        static_count = sum(1 for e in emojis if not e.animated)
        anim_count = sum(1 for e in emojis if e.animated)

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
            "guild_id": guild_id_str,
            "server_invite": invite_url,
            "connected": source_guild is not None,
            "guild_name": source_guild.name if source_guild else None,
            "total_emojis": len(emojis),
            "static_count": static_count,
            "animated_count": anim_count,
            "sample_preview": " ".join(self.format_discord_emoji(e) for e in emojis[:20]),
            "bot_oauth_invite": bot_invite_url,
        }


emoji_manager = EmojiManager()
