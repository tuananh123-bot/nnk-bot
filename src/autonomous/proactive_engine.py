# src/autonomous/proactive_engine.py
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set, Tuple

from src.config import settings
from src.cache.redis_client import cache

logger = logging.getLogger("Neneka.Autonomous")

class ProactiveEngine:
    """
    Hệ thống Tương tác Chủ động & Phòng Chống Spam (Autonomous Behavior Engine)
    - Quản lý 3 chế độ: MENTION (A), AUTO_CHAT (B), AUTONOMOUS (C)
    - Kiểm soát Cooldown theo kênh và theo người dùng
    - Bộ lọc chống spam, chống phản hồi lặp lại
    - Ra quyết định thông minh: Nên nói hay giữ im lặng dựa trên bối cảnh & cảm xúc
    """
    def __init__(self):
        self.mode = settings.AUTONOMOUS_MODE
        self.allowed_channels: Set[int] = set(settings.auto_reply_channel_ids)
        self.channel_cooldown = settings.CHANNEL_COOLDOWN_SECONDS
        self.user_cooldown = settings.USER_COOLDOWN_SECONDS
        self.proactive_min_interval = settings.PROACTIVE_MIN_INTERVAL_SECONDS
        self._last_responses: Dict[int, str] = {}  # channel_id -> last_response_text

    def set_mode(self, new_mode: str) -> bool:
        norm = new_mode.upper().strip()
        if norm in ["MENTION", "AUTO_CHAT", "AUTONOMOUS"]:
            self.mode = norm
            return True
        return False

    def add_allowed_channel(self, channel_id: int):
        self.allowed_channels.add(int(channel_id))

    def remove_allowed_channel(self, channel_id: int):
        self.allowed_channels.discard(int(channel_id))

    async def check_rate_limit(self, channel_id: int, user_id: int) -> Tuple[bool, str]:
        """Kiểm tra giới hạn tốc độ và cooldown của User và Channel"""
        now = time.time()

        # 1. User Cooldown
        user_key = f"cooldown:user:{user_id}"
        last_user = await cache.get(user_key)
        if last_user and (now - float(last_user)) < self.user_cooldown:
            return False, "User cooldown active"

        # 2. Channel Cooldown
        channel_key = f"cooldown:channel:{channel_id}"
        last_channel = await cache.get(channel_key)
        if last_channel and (now - float(last_channel)) < self.channel_cooldown:
            return False, "Channel cooldown active"

        # Cập nhật thời điểm
        await cache.set(user_key, str(now), ex=self.user_cooldown * 2)
        await cache.set(channel_key, str(now), ex=self.channel_cooldown * 2)
        return True, "OK"

    def should_reply(
        self,
        is_bot: bool,
        is_dm: bool,
        is_mentioned: bool,
        is_reply_to_bot: bool,
        channel_id: int,
        content: str
    ) -> Tuple[bool, str]:
        """
        Quyết định xem Neneka có nên phản hồi tin nhắn này hay không dựa trên Mode hoạt động
        """
        # Tuyệt đối không trả lời bot khác
        if is_bot:
            return False, "Tin nhắn từ bot khác"

        # Tuyệt đối không trả lời nếu nội dung rỗng
        if not content or not content.strip():
            return False, "Nội dung rỗng"

        # Trong tin nhắn trực tiếp (DM)
        if is_dm:
            return True, "DM trực tiếp"

        # Nếu được Mention hoặc Reply trực tiếp -> Luôn trả lời (áp dụng cho cả 3 mode)
        if is_mentioned or is_reply_to_bot:
            return True, "Được mention hoặc reply trực tiếp"

        # MODE A: Mention Mode -> Chỉ phản hồi khi được gọi tên
        if self.mode == "MENTION":
            return False, "Mode A: Chỉ phản hồi khi có mention"

        # MODE B & MODE C: Auto Chat & Autonomous
        if self.mode in ["AUTO_CHAT", "AUTONOMOUS"]:
            # Chỉ tự động phản hồi trong các kênh được quản trị viên cấp phép
            if channel_id in self.allowed_channels:
                return True, "Kênh nằm trong danh sách Auto Chat được cấp phép"

        return False, "Không thỏa mãn điều kiện kích hoạt"

    def should_proactively_speak(
        self,
        channel_id: int,
        idle_duration_seconds: float,
        last_message_content: str
    ) -> Tuple[bool, str]:
        """
        Quyết định hành vi chủ động của Neneka (Chỉ có trong MODE C: Autonomous)
        Không bao giờ gửi tin nhắn spam vô nghĩa.
        """
        if self.mode != "AUTONOMOUS":
            return False, "Không ở chế độ Autonomous Mode"

        if channel_id not in self.allowed_channels:
            return False, "Kênh không thuộc danh sách cho phép chủ động"

        # Không chủ động nếu kênh chưa yên tĩnh đủ lâu
        if idle_duration_seconds < self.proactive_min_interval:
            return False, "Khoảng thời gian chờ chưa đủ"

        # Neneka chỉ mở lời khi nhận thấy thời điểm thích hợp (ví dụ đêm muộn hoặc trưa vắng)
        now = datetime.now()
        if now.hour in [23, 0, 1, 2]:
            return True, "Chủ động nhắc nhở nghỉ ngơi vào đêm muộn"
        elif now.hour in [11, 12, 13]:
            return True, "Chủ động hỏi han bữa trưa"

        return False, "Chưa phải thời điểm thích hợp"

    def record_last_response(self, channel_id: int, response_text: str):
        self._last_responses[channel_id] = response_text

    def is_duplicate_response(self, channel_id: int, new_response: str) -> bool:
        """Ngăn chặn Neneka nói lại nguyên văn câu nói vừa rồi"""
        last = self._last_responses.get(channel_id, "")
        return last.strip().lower() == new_response.strip().lower()

proactive_engine = ProactiveEngine()

