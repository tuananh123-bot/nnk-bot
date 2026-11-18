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

    # Model mặc định – hỗ trợ nội dung mature, vẫn thông minh & sáng tạo
    DEFAULT_MODEL = "nousresearch/hermes-3-llama-3.1-405b:nitro"
    # Danh sách fallback nếu model mặc định bận / không khả dụng
    FALLBACK_MODELS = [
        "nousresearch/hermes-3-llama-3.1-405b:nitro",
        "mistralai/mistral-nemo",
        "meta-llama/llama-3.1-8b-instruct:free",
    ]
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self._client = None  # lazy init

    def _get_client(self):
        """Lazy-init openai client trỏ vào OpenRouter."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI  # openai >= 1.x
                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.BASE_URL,
                )
            except ImportError:
                # Fallback: openai < 1.x (v0.28)
                import openai as _oa
                _oa.api_key = self.api_key
                _oa.api_base = self.BASE_URL
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

        # Thử lần lượt model chính rồi fallback
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
        """Kiểm tra xem API key có được cấu hình không."""
        return bool(self.api_key and self.api_key.startswith("sk-or-"))


# --- Singleton helper ---
_instance: Optional[OpenRouterClient] = None


def get_openrouter_client() -> Optional[OpenRouterClient]:
    """
    Trả về singleton OpenRouterClient nếu API key được cấu hình.
    Trả về None nếu chưa có key.
    """
    global _instance
    if _instance is None:
        try:
            from src.config import settings
            key = settings.OPENROUTER_API_KEY
            model = getattr(settings, "OPENROUTER_DEFAULT_MODEL", None)
            if key:
                _instance = OpenRouterClient(api_key=key, model=model)
        except Exception as e:
            logger.warning(f"Không thể khởi tạo OpenRouterClient: {e}")
    return _instance
