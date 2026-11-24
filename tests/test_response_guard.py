# tests/test_response_guard.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.response_guard import (
    strip_thinking_blocks,
    has_degenerative_loop_or_contradiction,
    salvage_non_looping_text,
)
from src.memory.engine import MemoryEngine
from src.cogs.chat import ChatCog, sanitize_neneka_reply


EXACT_SCREENSHOT_BUG_TEXT = """Với ta, việc cậu cố gắng suy nghĩ đến mức phải lắc đầu đã là một chiến thắng rồi.

Đáp án chính là SIGHT... không, sai rồi. Đó là SHINE? Không, từ ấy chỉ có 5 chữ cái, bắt đầu bằng S và kết thúc bằng T...

À, chính xác là SHUTTLE? Không, ta đang đùa đấy.

Thực ra, từ mà ta đang nghĩ đến là SHUT... không, đó chỉ có 4 chữ cái.

Hãy để ta nói cho cậu biết: từ ấy là SHIRT? Không, đó là đồ mặc.

Ta thừa nhận, câu đố này của ta hơi... phức tạp hơn dự kiến.

Đáp án đúng là SHIT? Không, ta không nói tục.

Hãy để ta giải thích một cách thanh nhã hơn: Từ ấy là SHUT.

Không, ta đang tự mâu thuẫn.

Hãy để ta làm lại.

Từ ấy là SHUT.

Không, ta đang đùa.

Đáp án đúng là SHUT.

Thôi được rồi, ta thừa nhận ta đã làm khó cậu quá mức.

Hãy để ta tiết lộ: Từ ấy là SHUT."""


class TestResponseGuardAndAntiLoop:
    def test_strip_thinking_blocks(self):
        raw = "<think>\nIs it SIGHT? No. Is it SHIRT? Let me think.\n</think>\nĐáp án chính xác là **SMART** nhé cậu 😄"
        assert strip_thinking_blocks(raw) == "Đáp án chính xác là **SMART** nhé cậu 😄"

        unclosed = "<think>Thinking forever without closing..."
        assert strip_thinking_blocks(unclosed) == ""

    def test_detects_exact_screenshot_loop_and_contradiction(self):
        assert has_degenerative_loop_or_contradiction(EXACT_SCREENSHOT_BUG_TEXT) is True
        # Đảm bảo bộ nhớ ngắn hạn từ chối lưu trữ đoạn văn bị lỗi này
        assert MemoryEngine.is_valid_dialogue_turn("Đáp án là gì thế?", EXACT_SCREENSHOT_BUG_TEXT) is False

    def test_salvage_cleans_contradictions_and_duplicates(self):
        cleaned = sanitize_neneka_reply(EXACT_SCREENSHOT_BUG_TEXT)
        assert "ta đang tự mâu thuẫn" not in cleaned.lower()
        assert "hãy để ta làm lại" not in cleaned.lower()
        assert "không, sai rồi" not in cleaned.lower()
        # Không lặp lại "Từ ấy là SHUT" nhiều lần
        assert cleaned.upper().count("SHUT") <= 1

    def test_normal_and_code_replies_pass_untouched(self):
        normal_reply = "Đáp án của câu đố 5 chữ cái bắt đầu bằng S, kết thúc bằng T chính là **SMART** (thông minh) đấy cậu nhóc 😄"
        assert has_degenerative_loop_or_contradiction(normal_reply) is False
        assert MemoryEngine.is_valid_dialogue_turn("Giải đố đi", normal_reply) is True

        code_reply = "Đây là ví dụ vòng lặp nhé:\n```python\nfor i in range(12):\n    print('Từ ấy là SHUT')\n```"
        assert has_degenerative_loop_or_contradiction(code_reply) is False

    @pytest.mark.asyncio
    async def test_chat_cog_self_heals_when_primary_llm_loops(self):
        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=None)
        cog = ChatCog(bot)

        clean_healed_answer = "Với ta, việc cậu chịu suy nghĩ đã đáng khen rồi. Đáp án đúng của câu đố ấy là **SIGHT** (tầm nhìn) nhé ✨"

        with patch("src.cogs.chat.groq_client.chat_completion", new_callable=AsyncMock) as mock_groq, \
             patch("src.cogs.chat.fast_llm_client.chat_gemini_fast", new_callable=AsyncMock) as mock_gemini_heal:
            mock_groq.return_value = EXACT_SCREENSHOT_BUG_TEXT
            mock_gemini_heal.return_value = clean_healed_answer

            reply = await cog._generate_neneka_reply(
                user_message="Thôi chịu thua đó, đáp án là gì?",
                discord_user_id="888",
                username="TuanAnh",
                guild_id=None,
                channel_id="999",
            )

            mock_gemini_heal.assert_called_once()
            assert "SIGHT" in reply
            assert "ta đang tự mâu thuẫn" not in reply.lower()
