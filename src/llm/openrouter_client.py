# src/llm/openrouter_client.py
"""
OpenRouter API Client cho Neneka Bot.
Hỗ trợ nhiều model ngôn ngữ qua API OpenAI-compatible của OpenRouter.
Dùng cho chế độ NSFW và các model đặc biệt không có trên Groq.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger("neneka.openrouter")


class OpenRouterClient:
    """Client gọi OpenRouter API (OpenAI-compatible)."""

    # Model mặc định - Uncensored / roleplay NSFW (không bị từ chối cảnh người lớn)
    DEFAULT_MODEL = "sao10k/l3.3-euryale-70b"
    # Danh sách fallback - đều là model uncensored / NSFW-friendly
    FALLBACK_MODELS = [
        "sao10k/l3.3-euryale-70b",
        "eva-unit-01/eva-llama-3.33-70b",
        "anthracite-org/magnum-v4-72b",
        "mistralai/mistral-nemo:free",
    ]
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, model: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.base_url = base_url or self.BASE_URL
        self._client = None  # lazy init

    def _get_client(self):
        """Lazy-init openai client trỏ vào OpenRouter hoặc Local LLM."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI  # openai >= 1.x
                self._client = AsyncOpenAI(
                    api_key=self.api_key or "not-needed",
                    base_url=self.base_url,
                )
            except ImportError:
                # Fallback: openai < 1.x (v0.28)
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
        temperature: float = 0.9,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Gửi request chat completion tới OpenRouter.

        Args:
            messages: Danh sách message theo chuẩn OpenAI [{role, content}].
            model: Ghi đè model cho request này.
            max_tokens: Giới hạn tokens phản hồi.
            temperature: Độ sáng tạo (0.0-1.0).
            extra_headers: Header bổ sung (ví dụ HTTP-Referer, X-Title).

        Returns:
            Nội dung phản hồi dạng str.
        """
        use_model = model or self.model
        client = self._get_client()

        headers = {
            "HTTP-Referer": "https://github.com/tuananh123-bot/nnk-bot",
            "X-Title": "Neneka Discord Bot",
        }
        if extra_headers:
            headers.update(extra_headers)

        # Thử lần lượt model chính; nếu dùng local LLM thì chỉ dùng đúng model chỉ định
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
                content = response.choices[0].message.content or ""
                logger.info(f"OpenRouter [{attempt_model}] response OK ({len(content)} chars)")
                return content.strip()

            except Exception as e:
                logger.warning(f"OpenRouter [{attempt_model}] failed: {e}")
                last_error = e
                await asyncio.sleep(0.5)

        raise RuntimeError(
            f"OpenRouter: Tất cả model đều thất bại. Lỗi cuối: {last_error}"
        )

    async def _chat_legacy(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Hỗ trợ openai < 1.x (v0.x API)."""
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
        """Kiểm tra xem API key có được cấu hình hoặc có local base_url không."""
        if "localhost" in self.base_url or "127.0.0.1" in self.base_url:
            return True
        return bool(self.api_key and (self.api_key.startswith("sk-or-") or self.api_key.startswith("sk-")))


# --- Singleton helper ---
_instance: Optional[OpenRouterClient] = None


def get_openrouter_client() -> Optional[OpenRouterClient]:
    """
    Trả về singleton OpenRouterClient nếu API key hoặc Local base_url được cấu hình.
    Trả về None nếu chưa có key/local url.
    """
    global _instance
    if _instance is None:
        try:
            from src.config import settings
            key = getattr(settings, "OPENROUTER_API_KEY", "")
            model = getattr(settings, "OPENROUTER_DEFAULT_MODEL", None)
            base_url = getattr(settings, "OPENROUTER_BASE_URL", None)
            is_local = bool(base_url and ("localhost" in base_url or "127.0.0.1" in base_url))
            if key or is_local:
                _instance = OpenRouterClient(api_key=key or "not-needed", model=model, base_url=base_url)
        except Exception as e:
            logger.warning(f"Không thể khởi tạo OpenRouterClient: {e}")
    return _instance
