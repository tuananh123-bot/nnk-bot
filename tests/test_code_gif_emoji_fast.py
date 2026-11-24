# tests/test_code_gif_emoji_fast.py
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image

from src.config import settings
from src.utils.media_extractor import (
    get_code_language_for_filename,
    extract_code_attachments,
    format_code_files_for_prompt,
    detect_coding_intent,
    parse_gif_slug_hint,
    extract_image_or_gif_from_message,
    split_discord_message_preserving_code,
)
from src.utils.emoji_manager import emoji_manager
from src.llm.vision_client import convert_gif_to_storyboard_png
from src.cogs.chat import ChatCog, sanitize_neneka_reply


class TestCodeReadingAndSplitting:
    def test_code_extension_detection(self):
        assert get_code_language_for_filename("bot.py") == "python"
        assert get_code_language_for_filename("App.tsx") == "tsx"
        assert get_code_language_for_filename("Dockerfile") == "dockerfile"
        assert get_code_language_for_filename("style.css") == "css"
        assert get_code_language_for_filename("photo.png", "image/png") is None

    @pytest.mark.asyncio
    async def test_extract_code_attachments(self):
        att = MagicMock()
        att.filename = "example.py"
        att.content_type = "text/x-python"
        att.size = 64
        att.read = AsyncMock(return_value=b"def add(a, b):\n    return a + b\n")

        msg = MagicMock()
        msg.attachments = [att]
        msg.reference = None

        files = await extract_code_attachments(msg)
        assert len(files) == 1
        assert files[0]["filename"] == "example.py"
        assert files[0]["language"] == "python"
        assert "def add(a, b):" in files[0]["content"]

        formatted = format_code_files_for_prompt(files)
        assert "```python" in formatted
        assert "example.py" in formatted

    def test_detect_coding_intent(self):
        assert detect_coding_intent("Viết code Python sắp xếp mảng nhanh giúp mình") is True
        assert detect_coding_intent("Xem giúp mình lỗi này:\n```js\nconst x = ;\n```") is True
        assert detect_coding_intent("Traceback (most recent call last):\nTypeError: NoneType") is True
        assert detect_coding_intent("", has_code_files=True) is True

        # Chat đời thường không bị nhận nhầm là code
        assert detect_coding_intent("Alo đang làm gì đó Neneka?") is False
        assert detect_coding_intent("Hôm nay trời mát ghê nhỉ") is False

    def test_split_discord_message_preserving_code_fences(self):
        long_code = "Here is the script:\n```python\n" + "\n".join(f"print({i})" for i in range(300)) + "\n```\nDone!"
        chunks = split_discord_message_preserving_code(long_code, limit=800)
        assert len(chunks) >= 3
        for c in chunks:
            assert len(c) <= 850
            # Mọi chunk mở ``` đều phải được đóng ``` hợp lệ (số lần xuất hiện ``` là chẵn)
            assert c.count("```") % 2 == 0


class TestGifExtractionAndStoryboard:
    def test_parse_tenor_and_giphy_slugs(self):
        assert parse_gif_slug_hint("https://tenor.com/view/anime-hug-sweet-pat-gif-25123456") == "anime hug sweet pat"
        assert parse_gif_slug_hint("https://giphy.com/gifs/anime-happy-dance-xT9IgG50Fb7Mi0prBC") == "anime happy dance"

    def test_animated_gif_to_storyboard_png(self):
        frames = [
            Image.new("RGB", (80, 80), color="red"),
            Image.new("RGB", (80, 80), color="green"),
            Image.new("RGB", (80, 80), color="blue"),
            Image.new("RGB", (80, 80), color="yellow"),
        ]
        buf = io.BytesIO()
        frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
        gif_bytes = buf.getvalue()

        png_strip = convert_gif_to_storyboard_png(gif_bytes)
        assert png_strip is not None
        with Image.open(io.BytesIO(png_strip)) as out_img:
            assert out_img.format == "PNG"
            # 3 khung hình 80px ghép ngang + khoảng cách
            assert out_img.size[0] > 200
            assert out_img.size[1] == 80

    @pytest.mark.asyncio
    async def test_extract_gif_attachment_and_tenor_embed(self):
        # 1. File .gif đính kèm
        gif_att = MagicMock()
        gif_att.filename = "neneka_wave.gif"
        gif_att.content_type = "image/gif"
        gif_att.read = AsyncMock(return_value=b"GIF89afakedata")

        msg1 = MagicMock()
        msg1.attachments = [gif_att]
        msg1.stickers = []
        msg1.embeds = []
        msg1.content = ""
        msg1.reference = None

        img_data, hint = await extract_image_or_gif_from_message(msg1)
        assert img_data == (b"GIF89afakedata", "image/gif")
        assert "GIF" in hint

        # 2. Link Tenor kèm Discord Embed thumbnail
        emb = MagicMock()
        emb.type = "gifv"
        emb.title = "Anime Smug"
        emb.url = "https://tenor.com/view/anime-smug-neneka-gif-998877"
        emb.image = None
        emb.thumbnail = MagicMock()
        emb.thumbnail.proxy_url = "https://images-ext-1.discordapp.net/external/test/neneka.gif"
        emb.thumbnail.url = None

        msg2 = MagicMock()
        msg2.attachments = []
        msg2.stickers = []
        msg2.embeds = [emb]
        msg2.content = "https://tenor.com/view/anime-smug-neneka-gif-998877"
        msg2.reference = None

        with patch("src.utils.media_extractor._download_media_bytes", new_callable=AsyncMock) as mock_dl:
            mock_dl.return_value = (b"GIF89atenordata", "image/gif")
            img_data2, hint2 = await extract_image_or_gif_from_message(msg2)
            assert img_data2 == (b"GIF89atenordata", "image/gif")
            assert "anime smug neneka" in hint2


class TestServerCustomEmojiIntegration:
    def _make_mock_bot_with_emoji_guild(self):
        e1 = MagicMock()
        e1.name = "neneka_smug"
        e1.id = 111222333
        e1.animated = False
        e1.available = True

        e2 = MagicMock()
        e2.name = "neneka_dance"
        e2.id = 444555666
        e2.animated = True
        e2.available = True

        primary_gid = 1169588792064217159
        guild = MagicMock()
        guild.id = primary_gid
        guild.name = "Primary Emoji Server"
        guild.emojis = [e1, e2]

        bot = MagicMock()
        bot.get_guild = MagicMock(side_effect=lambda gid: guild if gid == primary_gid else None)
        bot.user = MagicMock()
        bot.user.id = 1234567890
        return bot

    def test_emoji_source_guild_config_and_prompt(self):
        assert 1169588792064217159 in settings.emoji_source_guild_ids
        assert settings.emoji_source_guild_ids[0] == 1169588792064217159
        bot = self._make_mock_bot_with_emoji_guild()

        guide = emoji_manager.build_emoji_prompt_guide(bot, is_coding=False)
        assert "<:neneka_smug:111222333>" in guide
        assert "<a:neneka_dance:444555666>" in guide

    def test_resolve_shortcodes_outside_code_blocks_only(self):
        bot = self._make_mock_bot_with_emoji_guild()
        raw_reply = (
            "Chuẩn rồi đấy cậu :neneka_smug: nhảy ăn mừng thôi :dance:\n"
            "```python\n"
            "emoji_str = ':neneka_smug:'\n"
            "```\n"
            "Và không hiển thị :fake_nonexistent_emoji: nhé!"
        )
        resolved = emoji_manager.resolve_emojis_in_reply(raw_reply, bot)
        assert "Chuẩn rồi đấy cậu <:neneka_smug:111222333>" in resolved
        assert "<a:neneka_dance:444555666>" in resolved
        # Bên trong khối ```python``` phải giữ nguyên tuyệt đối!
        assert "emoji_str = ':neneka_smug:'" in resolved
        # Emoji bịa đặt có gạch dưới bị dọn sạch
        assert ":fake_nonexistent_emoji:" not in resolved


class TestNaturalChatAndFastCodingRouting:
    def test_sanitize_preserves_short_natural_replies(self):
        short_natural = "Đang rảnh nè cậu 😄"
        assert sanitize_neneka_reply(short_natural) == short_natural

    @pytest.mark.asyncio
    async def test_coding_request_routes_to_fast_coding_engine(self):
        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=None)
        cog = ChatCog(bot)

        with patch("src.cogs.chat.fast_llm_client.generate_code_response", new_callable=AsyncMock) as mock_code_gen:
            mock_code_gen.return_value = "Đây là hàm tính tổng nhé:\n```python\ndef total(arr):\n    return sum(arr)\n```"

            reply = await cog._generate_neneka_reply(
                user_message="Viết code Python tính tổng danh sách số nguyên",
                discord_user_id="999",
                username="Coder",
                guild_id=None,
                channel_id="777",
            )
            mock_code_gen.assert_called_once()
            assert "def total(arr):" in reply
