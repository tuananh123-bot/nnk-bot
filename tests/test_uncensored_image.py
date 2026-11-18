# tests/test_uncensored_image.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.llm.uncensored_image_client import UncensoredImageClient

class TestUncensoredImageClient:
    def test_client_instantiation(self):
        client = UncensoredImageClient(
            api_key="uai_sk_live_test123",
            base_url="https://api.uncensored.com/api/v1",
            default_model="seedream-v5"
        )
        assert client.api_key == "uai_sk_live_test123"
        assert client.base_url == "https://api.uncensored.com/api/v1"
        assert client.default_model == "seedream-v5"

    def test_is_available(self):
        valid_client = UncensoredImageClient(api_key="uai_sk_live_test")
        assert valid_client.is_available() is True

        empty_client = UncensoredImageClient(api_key="")
        assert empty_client.is_available() is False

        invalid_client = UncensoredImageClient(api_key="sk-not-uai")
        assert invalid_client.is_available() is False

    def test_headers_structure(self):
        client = UncensoredImageClient(api_key="uai_sk_live_abc")
        headers = client._headers()
        assert headers["X-api-key"] == "uai_sk_live_abc"
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_generate_image_direct_url_mock(self):
        client = UncensoredImageClient(api_key="uai_sk_live_test")
        dummy_session = MagicMock()

        mock_post_data = {
            "url": "https://api.uncensored.com/images/seedream_output_123.png",
            "model": "seedream-v5"
        }

        with patch.object(client, "_post_generate", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_post_data

            result = await client.generate_image(
                prompt="Neneka standing on the balcony",
                session=dummy_session
            )

        assert result["img_url"] == "https://api.uncensored.com/images/seedream_output_123.png"
        assert result["model"] == "seedream-v5"
        assert result["provider"] == "uncensored.com"
        assert result["prompt"] == "Neneka standing on the balcony"

    @pytest.mark.asyncio
    async def test_generate_image_status_url_polling_mock(self):
        client = UncensoredImageClient(api_key="uai_sk_live_test")
        dummy_session = MagicMock()

        mock_post_data = {
            "status_url": "https://api.uncensored.com/api/v1/status/job_999"
        }
        mock_poll_data = {
            "status": "completed",
            "url": "https://api.uncensored.com/images/polled_output.jpg"
        }

        with patch.object(client, "_post_generate", new_callable=AsyncMock) as mock_post, \
             patch.object(client, "_poll_status", new_callable=AsyncMock) as mock_poll:
            mock_post.return_value = mock_post_data
            mock_poll.return_value = mock_poll_data

            result = await client.generate_image(
                prompt="Cyberpunk Landosol",
                session=dummy_session
            )

        assert result["img_url"] == "https://api.uncensored.com/images/polled_output.jpg"
        assert result["model"] == "seedream-v5"

    @pytest.mark.asyncio
    async def test_generate_image_402_insufficient_credits(self):
        client = UncensoredImageClient(api_key="uai_sk_live_test")
        dummy_session = MagicMock()

        with patch.object(client, "_post_generate", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = RuntimeError("Tài khoản Uncensored AI không đủ credit (402 Insufficient credits).")

            with pytest.raises(RuntimeError) as exc_info:
                await client.generate_image(prompt="test", session=dummy_session)

            assert "credit" in str(exc_info.value).lower()
