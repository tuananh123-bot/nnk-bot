# tests/test_horde.py
"""
Unit tests cho AI Horde client (Image Generation & Text Generation).
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.llm.horde_client import AIHordeClient


class TestAIHordeClient:
    """Test bộ điều khiển AI Horde."""

    def test_client_init_and_availability(self):
        client_valid = AIHordeClient(api_key="zmqKecnOWHn7yrXB1F300w")
        assert client_valid.is_available() is True
        assert client_valid.api_key == "zmqKecnOWHn7yrXB1F300w"

        client_anon = AIHordeClient(api_key="0000000000")
        assert client_anon.is_available() is False

        client_empty = AIHordeClient(api_key="")
        assert client_empty.is_available() is False

    def test_headers_structure(self):
        client = AIHordeClient(api_key="test_key_123")
        headers = client._headers()
        assert headers["apikey"] == "test_key_123"
        assert "Client-Agent" in headers
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_generate_image_mock_flow(self):
        client = AIHordeClient(api_key="test_key_123")
        dummy_session = MagicMock()

        mock_post_data = {"id": "req_image_001"}
        mock_get_data = {
            "done": True,
            "generations": [
                {
                    "img": "https://cdn.aihorde.net/sample_image.webp",
                    "seed": "123456",
                    "model": "WAI-ANI-NSFW-PONYXL"
                }
            ]
        }

        with patch.object(client, "_post", new_callable=AsyncMock) as mock_post, \
             patch.object(client, "_get", new_callable=AsyncMock) as mock_get:

            mock_post.return_value = mock_post_data
            mock_get.return_value = mock_get_data

            result = await client.generate_image(
                "neneka on the beach",
                width=512,
                height=768,
                session=dummy_session,
                poll_interval=0.001
            )

        assert result["img_url"] == "https://cdn.aihorde.net/sample_image.webp"
        assert result["model"] == "WAI-ANI-NSFW-PONYXL"
        assert result["seed"] == "123456"
        assert result["id"] == "req_image_001"
        assert "utsushimi neneka" in result["prompt"]

    @pytest.mark.asyncio
    async def test_generate_text_mock_flow(self):
        client = AIHordeClient(api_key="test_key_123")
        dummy_session = MagicMock()

        mock_post_data = {"id": "req_text_001"}
        mock_get_data = {
            "done": True,
            "generations": [
                {
                    "text": "Fufu... Ta đã hiểu ý cậu rồi đấy."
                }
            ]
        }

        with patch.object(client, "_post", new_callable=AsyncMock) as mock_post, \
             patch.object(client, "_get", new_callable=AsyncMock) as mock_get:

            mock_post.return_value = mock_post_data
            mock_get.return_value = mock_get_data

            text = await client.generate_text("Chào Neneka", session=dummy_session, poll_interval=0.001)

        assert text == "Fufu... Ta đã hiểu ý cậu rồi đấy."

    @pytest.mark.asyncio
    async def test_chat_formatting(self):
        client = AIHordeClient(api_key="test_key_123")

        with patch.object(client, "generate_text", new_callable=AsyncMock) as mock_gen_text:
            mock_gen_text.return_value = "Câu trả lời từ Horde."
            messages = [
                {"role": "system", "content": "You are Neneka."},
                {"role": "user", "content": "Em khỏe không?"}
            ]
            ans = await client.chat(messages)

            assert ans == "Câu trả lời từ Horde."
            mock_gen_text.assert_called_once()
            call_prompt = mock_gen_text.call_args[0][0]
            assert "[Instruction: You are Neneka.]" in call_prompt
            assert "User: Em khỏe không?" in call_prompt
            assert "Neneka:" in call_prompt
