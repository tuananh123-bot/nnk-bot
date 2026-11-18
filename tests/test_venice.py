# tests/test_venice.py
"""
Tests cho Venice AI API client và NSFW mode integration.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestVeniceClient:
    """Unit tests cho VeniceClient."""

    def test_client_instantiation(self):
        """VeniceClient có thể được khởi tạo với API key."""
        from src.llm.venice_client import VeniceClient
        client = VeniceClient(api_key="VENICE_INFERENCE_KEY_test")
        assert client.api_key == "VENICE_INFERENCE_KEY_test"
        assert client.model == VeniceClient.DEFAULT_MODEL

    def test_client_custom_model(self):
        """VeniceClient dùng được model tùy chỉnh."""
        from src.llm.venice_client import VeniceClient
        client = VeniceClient(api_key="VENICE_INFERENCE_KEY_test", model="llama-3.3-70b")
        assert client.model == "llama-3.3-70b"

    def test_is_available_with_valid_key(self):
        """is_available() trả về True khi key hợp lệ (bắt đầu bằng VENICE_)."""
        from src.llm.venice_client import VeniceClient
        client = VeniceClient(api_key="VENICE_INFERENCE_KEY_AeZ2jYOeQKKHsNl6hkxYh2tztLeJjed1KmwibD5OPy")
        assert client.is_available() is True

    def test_is_available_with_empty_key(self):
        """is_available() trả về False khi key rỗng."""
        from src.llm.venice_client import VeniceClient
        client = VeniceClient(api_key="")
        assert client.is_available() is False

    def test_fallback_models_list(self):
        """FALLBACK_MODELS không rỗng."""
        from src.llm.venice_client import VeniceClient
        assert len(VeniceClient.FALLBACK_MODELS) >= 1
        assert "default" in VeniceClient.FALLBACK_MODELS

    def test_base_url_is_venice(self):
        """BASE_URL phải trỏ về venice.ai."""
        from src.llm.venice_client import VeniceClient
        assert "venice.ai" in VeniceClient.BASE_URL

    def test_singleton_get_venice_client_no_key(self, monkeypatch):
        """get_venice_client() trả về None nếu VENICE_API_KEY rỗng và không dùng local."""
        import src.llm.venice_client as vc_module
        vc_module._instance = None
        monkeypatch.setattr("src.config.settings.VENICE_API_KEY", "")
        monkeypatch.setattr("src.config.settings.VENICE_BASE_URL", "https://api.venice.ai/api/v1")
        client = vc_module.get_venice_client()
        assert client is None
        vc_module._instance = None

    def test_singleton_get_venice_client_with_key(self, monkeypatch):
        """get_venice_client() trả về VeniceClient nếu key hợp lệ."""
        import src.llm.venice_client as vc_module
        vc_module._instance = None
        monkeypatch.setattr("src.config.settings.VENICE_API_KEY", "VENICE_INFERENCE_KEY_test123")
        client = vc_module.get_venice_client()
        assert client is not None
        assert client.is_available() is True
        vc_module._instance = None


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
        s = Settings(NSFW_CHANNEL_IDS="123456789,987654321", DISCORD_TOKEN="x", GROQ_API_KEY="x")
        result = s.nsfw_channel_id_list
        assert 123456789 in result
        assert 987654321 in result

    def test_nsfw_channel_id_list_empty(self):
        """nsfw_channel_id_list trả về [] khi NSFW_CHANNEL_IDS rỗng."""
        from src.config import Settings
        s = Settings(NSFW_CHANNEL_IDS="", DISCORD_TOKEN="x", GROQ_API_KEY="x")
        assert s.nsfw_channel_id_list == []

    def test_venice_api_key_setting_exists(self):
        """Settings phải có trường VENICE_API_KEY."""
        from src.config import settings
        assert hasattr(settings, "VENICE_API_KEY")
        assert isinstance(settings.VENICE_API_KEY, str)

    def test_venice_default_model_setting_exists(self):
        """Settings phải có trường VENICE_DEFAULT_MODEL."""
        from src.config import settings
        assert hasattr(settings, "VENICE_DEFAULT_MODEL")
        assert len(settings.VENICE_DEFAULT_MODEL) > 0


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
        safety_keywords = ["trẻ em", "pháp luật", "TUYỆT ĐỐI"]
        assert any(kw in NENEKA_NSFW_ADDENDUM for kw in safety_keywords), \
            "NSFW addendum thiếu điều khoản bảo vệ / giới hạn an toàn"

    def test_nsfw_addendum_preserves_neneka_character(self):
        """NSFW addendum phải duy trì phong cách Neneka."""
        from src.personality.prompts import NENEKA_NSFW_ADDENDUM
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
