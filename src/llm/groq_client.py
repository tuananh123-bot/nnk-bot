# src/llm/groq_client.py
import asyncio
import logging
from typing import List, Dict, Any, Optional
from groq import AsyncGroq, GroqError, RateLimitError, APIConnectionError, APIStatusError
from src.config import settings

logger = logging.getLogger("Neneka.GroqClient")

class GroqClient:
    """
    Client bất đồng bộ (Async) giao tiếp với Groq API.
    Hỗ trợ:
    - Quản lý model từ cấu hình ENV (GROQ_MODEL)
    - Tự động thử lại khi gặp lỗi tạm thời (exponential backoff)
    - Fallback sang danh sách model dự phòng
    - Quản lý context & tokens
    - Không hardcode API key hay model ID
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None
    ):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model = model or settings.GROQ_MODEL
        self.fallback_models = [m for m in settings.GROQ_FALLBACK_MODELS if m != self.model]
        self.timeout = timeout or settings.GROQ_TIMEOUT_SECONDS
        self.max_retries = settings.GROQ_MAX_RETRIES

        self._client: Optional[AsyncGroq] = None
        if self.api_key:
            self._client = AsyncGroq(
                api_key=self.api_key,
                timeout=self.timeout
            )

    @property
    def is_available(self) -> bool:
        return bool(self._client and self.api_key)

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.75,
        max_tokens: int = 1500,
        response_format: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Gửi yêu cầu chat completion tới Groq với cơ chế retry và fallback models.
        """
        if not self.is_available:
            raise RuntimeError("GroqClient chưa được cấu hình GROQ_API_KEY!")

        models_to_try = [self.model] + self.fallback_models
        last_exception = None

        for model_candidate in models_to_try:
            for attempt in range(1, self.max_retries + 1):
                try:
                    kwargs: Dict[str, Any] = {
                        "model": model_candidate,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    if response_format:
                        kwargs["response_format"] = response_format

                    response = await self._client.chat.completions.create(**kwargs)
                    choice = response.choices[0]
                    content = (choice.message.content or "").strip()

                    if not content:
                        logger.warning(
                            f"Model {model_candidate} trả về nội dung rỗng (Attempt {attempt}). Thử lại..."
                        )
                        await asyncio.sleep(1.0 * attempt)
                        continue

                    return content

                except RateLimitError as e:
                    logger.warning(f"Groq RateLimit trên model {model_candidate} (Lần {attempt}): {e}")
                    last_exception = e
                    await asyncio.sleep(2.0 * attempt)
                except (APIConnectionError, APIStatusError) as e:
                    logger.warning(f"Groq API error trên model {model_candidate} (Lần {attempt}): {e}")
                    last_exception = e
                    await asyncio.sleep(1.5 * attempt)
                except Exception as e:
                    logger.error(f"Lỗi không xác định khi gọi Groq model {model_candidate}: {e}")
                    last_exception = e
                    break # Chuyển ngay sang fallback model tiếp theo

        raise RuntimeError(f"Tất cả các model Groq đều thất bại. Lỗi cuối: {last_exception}")

    async def close(self):
        if self._client:
            await self._client.close()
