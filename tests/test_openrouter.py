# tests/test_openrouter.py
"""
Tests cho OpenRouter API client và NSFW mode integration.
"""
import os
import sys
import asyncio
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestOpenRouterClient:
    """Unit tests cho OpenRouterClient."""

    def test_client_instantiation(self):
        """OpenRouterClient có thể được khởi tạo với API key."""
        from src.llm.openrouter_client import OpenRouterClient
        client = OpenRouterClient(api_key="sk-or-test-key")
        assert client.api_key == "sk-or-test-key"
        assert client.model == OpenRouterClient.DEFAULT_MODEL

    def test_client_custom_model(self):
        """OpenRouterClient dùng được model tùy chỉnh."""
        from src.llm.openrouter_client import OpenRouterClient
        client = OpenRouterClient(api_key="sk-or-test", model="mistralai/mistral-nemo")
        assert client.model == "mistralai/mistral-nemo"

    def test_is_available_with_valid_key(self):
        """is_available() trả về True khi key hợp lệ (bắt đầu bằng sk-or-)."""
        from src.llm.openrouter_client import OpenRouterClient
        client = OpenRouterClient(api_key="sk-or-v1-abc123test")
        assert client.is_available() is True

    def test_is_available_with_empty_key(self):
        """is_available() trả về False khi key rỗng."""
        from src.llm.openrouter_client import OpenRouterClient
        client = OpenRouterClient(api_key="")
        assert client.is_available() is False

    def test_is_available_with_wrong_prefix(self):
        """is_available() trả về False nếu key không bắt đầu bằng sk-or-."""
        from src.llm.openrouter_client import OpenRouterClient
        client = OpenRouterClient(api_key="gsk_something_groq")
        assert client.is_available() is False

    def test_fallback_models_list(self):
        """FALLBACK_MODELS không rỗng và chứa ít nhất 1 model miễn phí."""
        from src.llm.openrouter_client import OpenRouterClient
        assert len(OpenRouterClient.FALLBACK_MODELS) >= 1
        # Phải có ít nhất 1 model :free để dự phòng
        free_models = [m for m in OpenRouterClient.FALLBACK_MODELS if ":free" in m]
        assert len(free_models) >= 1, "Cần ít nhất 1 model :free trong FALLBACK_MODELS"

    def test_base_url_is_openrouter(self):
        """BASE_URL phải trỏ về openrouter.ai."""
        from src.llm.openrouter_client import OpenRouterClient
        assert "openrouter.ai" in OpenRouterClient.BASE_URL

    def test_singleton_get_openrouter_client_no_key(self, monkeypatch):
        """get_openrouter_client() trả về None nếu OPENROUTER_API_KEY rỗng và không dùng local."""
        import src.llm.openrouter_client as orc_module
        # Reset singleton
        orc_module._instance = None
        monkeypatch.setattr("src.config.settings.OPENROUTER_API_KEY", "")
        monkeypatch.setattr("src.config.settings.OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        client = orc_module.get_openrouter_client()
        assert client is None
        orc_module._instance = None  # cleanup

    def test_singleton_get_openrouter_client_with_key(self, monkeypatch):
        """get_openrouter_client() trả về OpenRouterClient nếu key hợp lệ."""
        import src.llm.openrouter_client as orc_module
        orc_module._instance = None
        monkeypatch.setattr("src.config.settings.OPENROUTER_API_KEY", "sk-or-v1-testkey123")
        client = orc_module.get_openrouter_client()
        assert client is not None
        assert client.is_available() is True
        orc_module._instance = None  # cleanup


class TestNSFWConfig:
    """Tests cho cấu hình NSFW mode."""

    def test_nsfw_enabled_setting_exists(self):
        """Settings phải có trường NSFW_ENABLED."""
        from src.config import settings
        assert hasattr(settings, "NSFW_ENABLED")
        assert isinstance(settings.NSFW_ENABLED, bool)

    def test_nsfw_channel_ids_setting_exists(self):
        """Settings phải có trường NSFW_CHANNEL_IDS."""
        from src.config import settings
        assert hasattr(settings, "NSFW_CHANNEL_IDS")

    def test_nsfw_channel_id_list_property(self):
        """nsfw_channel_id_list parses comma-separated IDs thành list[int]."""
        from src.config import Settings
        # Tạo Settings giả với NSFW_CHANNEL_IDS cụ thể
        s = Settings(NSFW_CHANNEL_IDS="123456789,987654321", DISCORD_TOKEN="x", GROQ_API_KEY="x")
        result = s.nsfw_channel_id_list
        assert 123456789 in result
        assert 987654321 in result

    def test_nsfw_channel_id_list_empty(self):
        """nsfw_channel_id_list trả về [] khi NSFW_CHANNEL_IDS rỗng."""
        from src.config import Settings
        s = Settings(NSFW_CHANNEL_IDS="", DISCORD_TOKEN="x", GROQ_API_KEY="x")
        assert s.nsfw_channel_id_list == []

    def test_openrouter_api_key_setting_exists(self):
        """Settings phải có trường OPENROUTER_API_KEY."""
        from src.config import settings
        assert hasattr(settings, "OPENROUTER_API_KEY")
        assert isinstance(settings.OPENROUTER_API_KEY, str)

    def test_openrouter_default_model_setting_exists(self):
        """Settings phải có trường OPENROUTER_DEFAULT_MODEL."""
        from src.config import settings
        assert hasattr(settings, "OPENROUTER_DEFAULT_MODEL")
        assert len(settings.OPENROUTER_DEFAULT_MODEL) > 0


class TestNSFWPrompt:
    """Tests cho NSFW system prompt addendum."""

    def test_nsfw_addendum_exists(self):
        """NENEKA_NSFW_ADDENDUM phải được định nghĩa trong prompts.py."""
        from src.personality.prompts import NENEKA_NSFW_ADDENDUM
        assert isinstance(NENEKA_NSFW_ADDENDUM, str)
        assert len(NENEKA_NSFW_ADDENDUM) > 50

    def test_nsfw_addendum_has_safety_clause(self):
        """NSFW addendum phải có điều khoản bảo vệ trẻ em / an toàn."""
        from src.personality.prompts import NENEKA_NSFW_ADDENDUM
        # Kiểm tra có nhắc đến giới hạn an toàn
        safety_keywords = ["trẻ em", "pháp luật", "TUYỆT ĐỐI"]
        assert any(kw in NENEKA_NSFW_ADDENDUM for kw in safety_keywords), \
            "NSFW addendum thiếu điều khoản bảo vệ / giới hạn an toàn"

    def test_nsfw_addendum_preserves_neneka_character(self):
        """NSFW addendum phải duy trì phong cách Neneka."""
        from src.personality.prompts import NENEKA_NSFW_ADDENDUM
        # Phải đề cập đến việc giữ phong cách Neneka
        style_keywords = ["Neneka", "Thất Vương", "tao nhã", "phong cách"]
        assert any(kw in NENEKA_NSFW_ADDENDUM for kw in style_keywords)

    def test_get_system_prompt_with_nsfw(self):
        """get_system_prompt(is_nsfw=True) phải chứa NSFW addendum."""
        from src.personality.engine import PersonalityEngine
        from src.personality.prompts import NENEKA_NSFW_ADDENDUM
        engine = PersonalityEngine()
        prompt = engine.get_system_prompt(is_nsfw=True)
        assert NENEKA_NSFW_ADDENDUM in prompt

    def test_get_system_prompt_without_nsfw(self):
        """get_system_prompt(is_nsfw=False) KHÔNG chứa NSFW addendum."""
        from src.personality.engine import PersonalityEngine
        from src.personality.prompts import NENEKA_NSFW_ADDENDUM
        engine = PersonalityEngine()
        prompt = engine.get_system_prompt(is_nsfw=False)
        assert NENEKA_NSFW_ADDENDUM not in prompt

    def test_get_system_prompt_default_no_nsfw(self):
        """get_system_prompt() mặc định (is_nsfw không truyền) không có NSFW."""
        from src.personality.engine import PersonalityEngine
        from src.personality.prompts import NENEKA_NSFW_ADDENDUM
        engine = PersonalityEngine()
        prompt = engine.get_system_prompt()
        assert NENEKA_NSFW_ADDENDUM not in prompt


class TestNSFWRuntimeChannels:
    """Tests cho runtime NSFW channel set trong chat.py."""

    def test_nsfw_runtime_channels_is_set(self):
        """_nsfw_runtime_channels phải là một set có thể import được."""
        from src.cogs.chat import _nsfw_runtime_channels
        assert isinstance(_nsfw_runtime_channels, set)

    def test_nsfw_runtime_channels_add_remove(self):
        """Có thể thêm và xóa channel ID trong _nsfw_runtime_channels."""
        from src.cogs.chat import _nsfw_runtime_channels
        test_id = 999999999999
        _nsfw_runtime_channels.add(test_id)
        assert test_id in _nsfw_runtime_channels
        _nsfw_runtime_channels.discard(test_id)
        assert test_id not in _nsfw_runtime_channels
