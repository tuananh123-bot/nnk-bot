# tests/test_xai.py
"""
Unit tests cho xAI Grok API client.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestXAIClient:
    """Kiểm tra khởi tạo và các hàm tiện ích của XAIClient."""

    def test_client_instantiation(self):
        from src.llm.xai_client import XAIClient
        client = XAIClient(api_key="xai-testkey123")
        assert client.api_key == "xai-testkey123"
        assert client.model == XAIClient.DEFAULT_MODEL
        assert client.base_url == "https://api.x.ai/v1"

    def test_client_custom_model(self):
        from src.llm.xai_client import XAIClient
        client = XAIClient(api_key="xai-test", model="grok-beta")
        assert client.model == "grok-beta"

    def test_is_available_with_valid_key(self):
        from src.llm.xai_client import XAIClient
        client = XAIClient(api_key="xai-1234567890abcdef1234567890abcdef")
        assert client.is_available() is True

    def test_is_available_with_empty_key(self):
        from src.llm.xai_client import XAIClient
        client = XAIClient(api_key="")
        assert client.is_available() is False

    def test_fallback_models_contain_grok(self):
        from src.llm.xai_client import XAIClient
        assert "grok-2-latest" in XAIClient.FALLBACK_MODELS
        assert "grok-beta" in XAIClient.FALLBACK_MODELS

    def test_singleton_get_xai_client_no_key(self, monkeypatch):
        import src.llm.xai_client as xai_module
        xai_module._instance = None
        monkeypatch.setattr("src.config.settings.XAI_API_KEY", "")
        client = xai_module.get_xai_client()
        assert client is None
        xai_module._instance = None

    def test_singleton_get_xai_client_with_key(self, monkeypatch):
        import src.llm.xai_client as xai_module
        xai_module._instance = None
        monkeypatch.setattr("src.config.settings.XAI_API_KEY", "xai-abcdef1234567890abcdef123456")
        client = xai_module.get_xai_client()
        assert client is not None
        assert client.is_available() is True
        xai_module._instance = None
