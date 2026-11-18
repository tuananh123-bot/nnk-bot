# src/llm/venice_client.py
"""
Venice AI Client cho Neneka Bot (https://venice.ai/).
Hỗ trợ các mô hình riêng tư, không kiểm duyệt (Uncensored / Zero-Log / TEE Privacy)
thông qua API tương thích chuẩn OpenAI.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger("Neneka.Venice")


class VeniceClient:
    """Client gọi Venice AI API (OpenAI-compatible)."""

    DEFAULT_MODEL = "default"
    FALLBACK_MODELS = [
        "default",
        "llama-3.3-70b",
        "e2ee-deepseek-v4-1-flash-1017-abliterated",
        "venice-uncensored-role-play",
    ]
    BASE_URL = "https://api.venice.ai/api/v1"

    def __init__(self, api_key: str, model: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.base_url = base_url or self.BASE_URL
        self._client = None

    def _get_client(self):
        """Lazy-init AsyncOpenAI client trỏ vào Venice AI hoặc Local LLM."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self.api_key or "not-needed",
                    base_url=self.base_url,
                )
            except ImportError:
                import openai as _oa
                _oa.api_key = self.api_key or "not-needed"
                _oa.api_base = self.base_url
                self._client = "legacy"
        return self._client

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 800,
        temperature: float = 0.85,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Gửi yêu cầu chat completion tới Venice AI.
        """
        use_model = model or self.model
        client = self._get_client()

        headers = {}
        if extra_headers:
            headers.update(extra_headers)

        is_local = "localhost" in self.base_url or "127.0.0.1" in self.base_url
        models_to_try = [use_model] if is_local else [use_model] + [m for m in self.FALLBACK_MODELS if m != use_model]

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
                    extra_headers=headers,
                )
                msg = response.choices[0].message
                content = msg.content or ""
                if not content.strip() and hasattr(msg, "reasoning_content") and msg.reasoning_content:
                    content = msg.reasoning_content
                logger.info(f"Venice AI / Local [{attempt_model}] response OK ({len(content)} chars)")
                return content.strip()

            except Exception as e:
                logger.warning(f"Venice AI [{attempt_model}] failed: {e}")
                last_error = e
                await asyncio.sleep(0.5)

        raise RuntimeError(
            f"Venice AI: Tất cả model đều thất bại. Lỗi cuối: {last_error}"
        )

    async def _chat_legacy(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
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
        """Kiểm tra API key Venice hoặc local base_url."""
        if "localhost" in self.base_url or "127.0.0.1" in self.base_url:
            return True
        return bool(self.api_key and (
            self.api_key.startswith("VENICE_") or
            self.api_key.startswith("sk-") or
            len(self.api_key) > 20
        ))


# --- Singleton helper ---
_instance: Optional[VeniceClient] = None


def get_venice_client() -> Optional[VeniceClient]:
    """
    Trả về singleton VeniceClient nếu API key hoặc Local base_url được cấu hình.
    """
    global _instance
    if _instance is None:
        try:
            from src.config import settings
            key = getattr(settings, "VENICE_API_KEY", "")
            model = getattr(settings, "VENICE_DEFAULT_MODEL", None)
            base_url = getattr(settings, "VENICE_BASE_URL", None)
            is_local = bool(base_url and ("localhost" in base_url or "127.0.0.1" in base_url))
            if key or is_local:
                _instance = VeniceClient(api_key=key or "not-needed", model=model, base_url=base_url)
        except Exception as e:
            logger.warning(f"Không thể khởi tạo VeniceClient: {e}")
    return _instance
