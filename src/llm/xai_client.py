# src/llm/xai_client.py
"""
xAI Grok API Client cho Neneka Bot.
Hỗ trợ các model Grok (grok-2, grok-2-latest, grok-beta) từ xAI (https://x.ai / https://console.x.ai).
API tương thích hoàn toàn chuẩn OpenAI tại https://api.x.ai/v1.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger("neneka.xai")


class XAIClient:
    """Client gọi xAI Grok API (OpenAI-compatible)."""

    DEFAULT_MODEL = "grok-2-latest"
    FALLBACK_MODELS = [
        "grok-2-latest",
        "grok-2",
        "grok-beta",
    ]
    BASE_URL = "https://api.x.ai/v1"

    def __init__(self, api_key: str, model: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.base_url = base_url or self.BASE_URL
        self._client = None

    def _get_client(self):
        """Lazy-init OpenAI client trỏ vào xAI endpoint."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
            except ImportError:
                import openai as _oa
                _oa.api_key = self.api_key
                _oa.api_base = self.base_url
                self._client = "legacy"
        return self._client

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 1200,
        temperature: float = 0.8,
    ) -> str:
        """Gửi request chat completion tới xAI Grok."""
        use_model = model or self.model
        client = self._get_client()

        models_to_try = [use_model] + [m for m in self.FALLBACK_MODELS if m != use_model]

        last_error: Optional[Exception] = None
        for attempt_model in models_to_try:
            try:
                if client == "legacy":
                    return await self._chat_legacy(messages, attempt_model, max_tokens, temperature)

                response = await client.chat.completions.create(
                    model=attempt_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                content = response.choices[0].message.content or ""
                logger.info(f"xAI Grok [{attempt_model}] response OK ({len(content)} chars)")
                return content.strip()

            except Exception as e:
                logger.warning(f"xAI Grok [{attempt_model}] failed: {e}")
                last_error = e
                await asyncio.sleep(0.5)

        raise RuntimeError(f"xAI Grok: Tất cả model đều thất bại. Lỗi cuối: {last_error}")

    async def _chat_legacy(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Hỗ trợ openai < 1.x."""
        import openai as _oa
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _oa.ChatCompletion.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        return response["choices"][0]["message"]["content"].strip()

    def is_available(self) -> bool:
        """Kiểm tra xem API key có được cấu hình không."""
        return bool(self.api_key and (self.api_key.startswith("xai-") or len(self.api_key) > 20))


# --- Singleton helper ---
_instance: Optional[XAIClient] = None


def get_xai_client() -> Optional[XAIClient]:
    """Trả về singleton XAIClient nếu API key được cấu hình."""
    global _instance
    if _instance is None:
        try:
            from src.config import settings
            key = getattr(settings, "XAI_API_KEY", "")
            model = getattr(settings, "XAI_MODEL", None)
            base_url = getattr(settings, "XAI_BASE_URL", None)
            if key:
                _instance = XAIClient(api_key=key, model=model, base_url=base_url)
        except Exception as e:
            logger.warning(f"Không thể khởi tạo XAIClient: {e}")
    return _instance
