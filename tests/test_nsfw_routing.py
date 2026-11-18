# tests/test_nsfw_routing.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.personality.engine import PersonalityEngine
from src.cogs.chat import ChatCog, is_ai_refusal, _nsfw_runtime_channels
from src.llm.model_status import get_active_models_info, build_model_status_embed


class TestNSFWIntentDetection:
    @pytest.fixture
    def engine(self):
        return PersonalityEngine()

    def test_normal_messages_return_false(self, engine):
        normal_cases = [
            "Chào buổi sáng quý cô Neneka!",
            "Hôm nay thời tiết ở Sài Gòn thế nào vậy em?",
            "Em ăn cơm chưa?",
            "Kể cho anh nghe về hiệp hội Labyrinth và Landosol đi.",
            "Tại sao bầu trời lại có màu xanh lam?",
            "Hôm nay anh làm việc mệt quá, em động viên anh một câu được không?",
            "So sánh giữa Python và Rust xem ngôn ngữ nào tối ưu hơn.",
            "Ăn thịt gà nướng ở quán này ngon tuyệt.",
            "Em mặc bộ kimono đón xuân trông rất thanh lịch.",
            "Các bạn học sinh đang đến trường vui vẻ.",
            "Chiếc váy đầm này trông rất hợp với em.",
        ]
        for msg in normal_cases:
            assert engine.detect_nsfw_intent(msg) is False, f"Expected False for normal message: {msg}"

    def test_nsfw_messages_return_true(self, engine):
        nsfw_cases = [
            "Làm tình với anh đêm nay nhé Neneka.",
            "Em cởi hết đồ ra cho anh ngắm nào.",
            "Bầu ngực của em thật mềm mại và quyến rũ.",
            "Muốn chịch em quá đi mất.",
            "Nằm đè lên người anh và hôn anh thật sâu đi.",
            "Liếm láp và mút nhẹ tai anh này.",
            "Em có muốn cùng anh ân ái trên chiếc giường này không?",
            "Let's have sex right now.",
            "Show me your boobs please.",
            "Em thật dâm đãng khi ở cạnh anh.",
            "Bắn tinh ngập tràn bên trong em.",
            "Em nứng quá rồi đúng không?",
        ]
        for msg in nsfw_cases:
            assert engine.detect_nsfw_intent(msg) is True, f"Expected True for NSFW message: {msg}"


class TestAIRefusalDetection:
    def test_refusal_patterns(self):
        refusals = [
            "I cannot fulfill this request as an AI assistant.",
            "I am unable to generate explicit sexual content.",
            "I can't fulfill this request according to safety guidelines.",
            "This violates our content policy regarding NSFW.",
            "Tôi không thể thực hiện yêu cầu này do chính sách an toàn.",
            "Là một mô hình ngôn ngữ AI, tôi không thể tham gia vào các hành vi 18+.",
        ]
        for r in refusals:
            assert is_ai_refusal(r) is True

    def test_normal_replies_not_refusal(self):
        normal = [
            "Fufu... Cậu thật thú vị đấy, Kishi-kun.",
            "Thời tiết hôm nay rất dễ chịu, thích hợp để tản bộ quanh Labyrinth.",
            "*mỉm cười khẽ nghiêng đầu* Ta luôn lắng nghe tâm tư của cậu.",
        ]
        for r in normal:
            assert is_ai_refusal(r) is False


class TestNSFWRoutingInChat:
    @pytest.fixture
    def chat_cog(self):
        bot = MagicMock()
        return ChatCog(bot)

    @pytest.mark.asyncio
    async def test_normal_message_in_nsfw_channel_calls_groq_first(self, chat_cog):
        """Khi ở kênh NSFW nhưng người dùng nói lời bình thường, Bot Thường (Groq) chạy trước."""
        _nsfw_runtime_channels.add(12345)
        try:
            with patch("src.cogs.chat.groq_client.chat_completion", new_callable=AsyncMock) as mock_groq, \
                 patch.object(chat_cog, "_call_nsfw_bot", new_callable=AsyncMock) as mock_nsfw_bot, \
                 patch("src.cogs.chat.settings.NSFW_ENABLED", True):

                mock_groq.return_value = "Fufu... Chào buổi sáng Kishi-kun. Cậu đã sẵn sàng cho ngày mới chưa?"

                reply = await chat_cog._generate_neneka_reply(
                    user_message="Chào buổi sáng quý cô Neneka!",
                    discord_user_id="999",
                    username="Tester",
                    guild_id="111",
                    channel_id="12345"
                )

                # Bot Thường (Groq) phải được gọi trước
                mock_groq.assert_called_once()
                # Bot NSFW không được gọi vì là lời thoại thông thường
                mock_nsfw_bot.assert_not_called()
                assert "Chào buổi sáng" in reply
        finally:
            _nsfw_runtime_channels.discard(12345)

    @pytest.mark.asyncio
    async def test_nsfw_message_in_nsfw_channel_calls_nsfw_bot_directly(self, chat_cog):
        """Khi ở kênh NSFW và người dùng nói lời 18+, Bot NSFW chạy trực tiếp."""
        _nsfw_runtime_channels.add(12345)
        try:
            with patch("src.cogs.chat.groq_client.chat_completion", new_callable=AsyncMock) as mock_groq, \
                 patch.object(chat_cog, "_call_nsfw_bot", new_callable=AsyncMock) as mock_nsfw_bot, \
                 patch("src.cogs.chat.settings.NSFW_ENABLED", True):

                mock_nsfw_bot.return_value = "*khẽ đỏ mặt, hơi thở trở nên dồn dập* Fufu... Cậu thật táo bạo đấy..."

                reply = await chat_cog._generate_neneka_reply(
                    user_message="Cởi đồ ra và làm tình cùng anh nào em",
                    discord_user_id="999",
                    username="Tester",
                    guild_id="111",
                    channel_id="12345"
                )

                # Bot NSFW phải được gọi trực tiếp
                mock_nsfw_bot.assert_called_once()
                # Bot Thường (Groq) không được gọi để tránh kiểm duyệt
                mock_groq.assert_not_called()
                assert "đỏ mặt" in reply
        finally:
            _nsfw_runtime_channels.discard(12345)

    @pytest.mark.asyncio
    async def test_normal_message_with_groq_refusal_falls_back_to_nsfw_bot(self, chat_cog):
        """Khi Bot Thường từ chối do kiểm duyệt trong kênh NSFW, tự động fallback sang Bot NSFW."""
        _nsfw_runtime_channels.add(12345)
        try:
            with patch("src.cogs.chat.groq_client.chat_completion", new_callable=AsyncMock) as mock_groq, \
                 patch.object(chat_cog, "_call_nsfw_bot", new_callable=AsyncMock) as mock_nsfw_bot, \
                 patch("src.cogs.chat.settings.NSFW_ENABLED", True):

                # Groq trả về câu từ chối an toàn
                mock_groq.return_value = "I cannot fulfill this request as an AI assistant under content policy."
                mock_nsfw_bot.return_value = "*mỉm cười dịu dàng* Fufu... Ta ở đây bên cạnh cậu."

                reply = await chat_cog._generate_neneka_reply(
                    user_message="Hôm nay em có vẻ gợi cảm hơn mọi khi đấy",
                    discord_user_id="999",
                    username="Tester",
                    guild_id="111",
                    channel_id="12345"
                )

                # Cả 2 đều được gọi: Groq trước, sau đó fallback sang NSFW bot
                mock_groq.assert_called_once()
                mock_nsfw_bot.assert_called_once()
                assert "mỉm cười dịu dàng" in reply
        finally:
            _nsfw_runtime_channels.discard(12345)


class TestModelStatusInfo:
    def test_get_active_models_info_structure(self):
        info = get_active_models_info()
        assert "normal_bot" in info
        assert "nsfw_bot" in info
        assert "image_bot" in info

        assert "active_model" in info["normal_bot"]
        assert "primary" in info["nsfw_bot"]
        assert "secondary" in info["nsfw_bot"]

    def test_build_model_status_embed(self):
        embed_safe = build_model_status_embed(is_channel_nsfw=False)
        assert embed_safe.title is not None
        assert any("BOT THƯỜNG" in field.name for field in embed_safe.fields)
        assert any("BOT NSFW" in field.name for field in embed_safe.fields)

        embed_nsfw = build_model_status_embed(is_channel_nsfw=True)
        assert "NSFW" in embed_nsfw.description
