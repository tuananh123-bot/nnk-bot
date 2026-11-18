# tests/test_gemini_image.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.llm.gemini_image_client import GeminiImageClient
from src.cogs.image_gen import ImageGenCog


class TestGeminiImageClient:
    def test_client_instantiation(self):
        client = GeminiImageClient(api_key="AIzaSyTest1234567890", model="gemini-2.5-flash-image")
        assert client.api_key == "AIzaSyTest1234567890"
        assert client.model == "gemini-2.5-flash-image"

    def test_is_available(self):
        valid_client = GeminiImageClient(api_key="AIzaSyTest1234567890")
        assert valid_client.is_available() is True

        empty_client = GeminiImageClient(api_key="")
        assert empty_client.is_available() is False

        short_client = GeminiImageClient(api_key="short")
        assert short_client.is_available() is False

    @pytest.mark.asyncio
    async def test_generate_image_success(self):
        client = GeminiImageClient(api_key="AIzaSyTest1234567890", model="gemini-2.5-flash-image")
        fake_bytes = b"\x89PNG\r\n\x1a\nfakeimagedata"

        with patch.object(client, "_sync_generate", return_value=fake_bytes) as mock_sync:
            result = await client.generate_image(
                prompt="Neneka reading book in laboratory",
                orientation="landscape",
            )

            mock_sync.assert_called_once_with("gemini-2.5-flash-image", "Neneka reading book in laboratory", "16:9")
            assert result["image_bytes"] == fake_bytes
            assert "Google Nano Banana" in result["model"]
            assert result["orientation"] == "landscape"
            assert result["provider"] == "Google Gemini (Nano Banana 🍌)"

    @pytest.mark.asyncio
    async def test_aspect_ratio_mappings(self):
        client = GeminiImageClient(api_key="AIzaSyTest1234567890")
        fake_bytes = b"fake"

        with patch.object(client, "_sync_generate", return_value=fake_bytes) as mock_sync:
            # Square -> 1:1
            await client.generate_image(prompt="test", orientation="square")
            assert mock_sync.call_args[0][2] == "1:1"

            # Portrait -> 9:16
            await client.generate_image(prompt="test", orientation="portrait")
            assert mock_sync.call_args[0][2] == "9:16"

            # Landscape -> 16:9
            await client.generate_image(prompt="test", orientation="landscape")
            assert mock_sync.call_args[0][2] == "16:9"

    @pytest.mark.asyncio
    async def test_generate_image_model_fallback(self):
        client = GeminiImageClient(api_key="AIzaSyTest1234567890", model="gemini-2.5-flash-image")
        fake_bytes = b"image_from_fallback"

        call_count = 0

        def fake_sync(model_name, prompt, ratio):
            nonlocal call_count
            call_count += 1
            if model_name == "gemini-2.5-flash-image":
                raise RuntimeError("Model 404 not found")
            return fake_bytes

        with patch.object(client, "_sync_generate", side_effect=fake_sync):
            result = await client.generate_image(prompt="test fallback")
            assert call_count >= 2
            assert result["image_bytes"] == fake_bytes

    @pytest.mark.asyncio
    async def test_generate_image_resource_exhausted_stops(self):
        client = GeminiImageClient(api_key="AIzaSyTest1234567890", model="gemini-2.5-flash-image")

        with patch.object(
            client,
            "_sync_generate",
            side_effect=RuntimeError("ResourceExhausted: GenerateRequestsPerDayPerProjectPerModel-FreeTier limit exceeded"),
        ) as mock_sync:
            with pytest.raises(RuntimeError) as exc_info:
                await client.generate_image(prompt="test quota")

            assert "ResourceExhausted" in str(exc_info.value)
            # Should have stopped after first model, not spammed remaining models
            assert mock_sync.call_count == 1


class TestImageGenCogRouting:
    @pytest.mark.asyncio
    async def test_normal_channel_routes_to_gemini(self):
        bot = MagicMock()
        cog = ImageGenCog(bot)
        cog._is_channel_nsfw = MagicMock(return_value=False)

        mock_author = MagicMock()
        mock_author.mention = "@Kishi-kun"
        mock_channel = MagicMock()
        mock_target = MagicMock()
        mock_target.send = AsyncMock()

        fake_img_bytes = b"pngdata"

        with patch("src.cogs.image_gen.gemini_image_client.is_available", return_value=True), \
             patch("src.cogs.image_gen.gemini_image_client.generate_image", new_callable=AsyncMock) as mock_gemini, \
             patch("src.cogs.image_gen.uncensored_image_client.is_available", return_value=True), \
             patch("src.cogs.image_gen.horde_client.is_available", return_value=True):

            mock_gemini.return_value = {
                "image_bytes": fake_img_bytes,
                "model": "Google Nano Banana (gemini-2.5-flash-image)",
                "provider": "Google Gemini (Nano Banana 🍌)",
                "prompt": "garden",
                "orientation": "portrait",
            }

            await cog._process_image_generation(
                reply_target=mock_target,
                author=mock_author,
                channel=mock_channel,
                prompt="garden",
                orientation="portrait",
                style="anime",
                provider="auto",
            )

            # Gemini Nano Banana must be called for normal pictures
            mock_gemini.assert_called_once()
            assert mock_target.send.called
            call_kwargs = mock_target.send.call_args[1]
            assert "embed" in call_kwargs
            assert "file" in call_kwargs

    @pytest.mark.asyncio
    async def test_nsfw_channel_routes_to_uncensored(self):
        bot = MagicMock()
        cog = ImageGenCog(bot)
        cog._is_channel_nsfw = MagicMock(return_value=True)

        mock_author = MagicMock()
        mock_author.mention = "@Kishi-kun"
        mock_channel = MagicMock()
        mock_target = MagicMock()
        mock_target.send = AsyncMock()

        with patch("src.cogs.image_gen.gemini_image_client.is_available", return_value=True), \
             patch("src.cogs.image_gen.gemini_image_client.generate_image", new_callable=AsyncMock) as mock_gemini, \
             patch("src.cogs.image_gen.uncensored_image_client.is_available", return_value=True), \
             patch("src.cogs.image_gen.uncensored_image_client.generate_image", new_callable=AsyncMock) as mock_uncensored, \
             patch("src.cogs.image_gen.horde_client.is_available", return_value=True):

            mock_uncensored.return_value = {
                "img_url": "https://api.uncensored.com/images/18plus.png",
                "model": "seedream-v5",
                "provider": "uncensored.com",
            }

            await cog._process_image_generation(
                reply_target=mock_target,
                author=mock_author,
                channel=mock_channel,
                prompt="spicy art",
                orientation="portrait",
                style="anime",
                provider="auto",
            )

            # In NSFW channel, Gemini should NOT be called; Uncensored AI should be called
            mock_gemini.assert_not_called()
            mock_uncensored.assert_called_once()
            assert mock_target.send.called
            call_kwargs = mock_target.send.call_args[1]
            assert "embed" in call_kwargs
            assert "file" not in call_kwargs  # URL based, no file attachment needed
