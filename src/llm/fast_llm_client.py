# src/llm/fast_llm_client.py
"""
Hệ thống LLM Phản Hồi Siêu Tốc (Fast Chat) & Chuyên Viết/Đọc Code Miễn Phí (Fast Coding):
1. Fast Chat Providers:
   - Cerebras Cloud (https://api.cerebras.ai/v1) - ~2,200 tokens/s (Free 1M tokens/ngày)
   - SambaNova Cloud (https://api.sambanova.ai/v1) - ~1,000 tokens/s (Free tier)
   - Groq LPU Cloud (sẵn sàng qua groq_client) - ~800 tokens/s
   - Google Gemini Flash-Lite (sẵn sàng qua GEMINI_API_KEY) - Phản hồi tức thì
2. Free Fast Coding Providers:
   - Mistral Codestral (https://codestral.mistral.ai/v1, model: codestral-latest) - API chuyên Code MIỄN PHÍ cực nhanh!
   - OpenRouter Free Coder (qwen/qwen3-coder:free)
   - Groq Coding (openai/gpt-oss-120b / qwen/qwen3.8-27b)
   - Google Gemini Flash (gemini-3.8-flash / gemini-3.5-flash)
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any

from src.config import settings

logger = logging.getLogger("Neneka.FastLLM")


class FastLLMClient:
    """Điều phối viên gọi các API phản hồi chat siêu nhanh và API đọc/viết code miễn phí."""

    def __init__(self):
        self._oa_clients: Dict[str, Any] = {}
        self._gemini_client = None

    def _get_openai_client(self, cache_key: str, api_key: str, base_url: str, timeout: float = 18.0):
        if cache_key not in self._oa_clients:
            from openai import AsyncOpenAI
            self._oa_clients[cache_key] = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
            )
        return self._oa_clients[cache_key]

    def _get_gemini_client(self):
        if self._gemini_client is None and settings.GEMINI_API_KEY:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
            except Exception as e:
                logger.warning(f"Không khởi tạo được Gemini Chat Client: {e}")
        return self._gemini_client

    @property
    def has_cerebras(self) -> bool:
        return bool(settings.CEREBRAS_API_KEY and len(settings.CEREBRAS_API_KEY) > 10)

    @property
    def has_sambanova(self) -> bool:
        return bool(settings.SAMBANOVA_API_KEY and len(settings.SAMBANOVA_API_KEY) > 10)

    @property
    def has_codestral(self) -> bool:
        return bool(settings.CODESTRAL_API_KEY and len(settings.CODESTRAL_API_KEY) > 10)

    @property
    def has_openrouter(self) -> bool:
        return bool(settings.OPENROUTER_API_KEY and len(settings.OPENROUTER_API_KEY) > 10)

    @property
    def has_gemini(self) -> bool:
        return bool(settings.GEMINI_API_KEY and len(settings.GEMINI_API_KEY) > 10)

    async def _call_oa_provider(
        self,
        name: str,
        api_key: str,
        base_url: str,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout: float = 18.0,
    ) -> str:
        client = self._get_openai_client(name, api_key, base_url, timeout=timeout)
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        from src.utils.response_guard import strip_thinking_blocks
        content = strip_thinking_blocks(resp.choices[0].message.content or "")
        if not content:
            raise RuntimeError(f"{name} ({model}) trả về rỗng.")
        logger.info(f"⚡ [{name} • {model}] phản hồi thành công ({len(content)} chars)")
        return content

    async def chat_gemini_fast(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1500,
        prefer_coding: bool = False,
    ) -> str:
        """Gọi Google Gemini Flash-Lite / Flash (sử dụng GEMINI_API_KEY có sẵn)."""
        g_client = self._get_gemini_client()
        if not g_client:
            raise RuntimeError("GEMINI_API_KEY chưa được cấu hình.")

        from google.genai import types

        sys_inst = ""
        contents = []
        for m in messages:
            role = m.get("role", "user")
            text = m.get("content", "")
            if role == "system":
                sys_inst += (text + "\n")
            elif role == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=text)]))
            else:
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))

        if not contents:
            contents = ["Hello"]

        models = (
            ["gemini-3.8-flash", "gemini-3.5-flash", settings.GEMINI_CHAT_MODEL]
            if prefer_coding
            else [settings.GEMINI_CHAT_MODEL, "gemini-3.5-flash", "gemini-3.8-flash"]
        )
        # Loại trùng lặp giữ nguyên thứ tự
        seen = set()
        ordered_models = [x for x in models if x and not (x in seen or seen.add(x))]

        cfg = types.GenerateContentConfig(
            system_instruction=sys_inst.strip() or None,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        last_err = None
        for m_name in ordered_models:
            try:
                resp = await asyncio.to_thread(
                    g_client.models.generate_content,
                    model=m_name,
                    contents=contents,
                    config=cfg,
                )
                txt = (resp.text or "").strip()
                if txt:
                    logger.info(f"⚡ [Gemini • {m_name}] phản hồi thành công ({len(txt)} chars)")
                    return txt
            except Exception as e:
                logger.warning(f"Gemini model {m_name} lỗi: {e}")
                last_err = e

        raise RuntimeError(f"Gemini chat thất bại: {last_err}")

    async def try_ultra_fast_external_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.78,
        max_tokens: int = 750,
    ) -> Optional[str]:
        """
        Thử các API tốc độ siêu thanh (Cerebras ~2200 tok/s, SambaNova ~1000 tok/s) nếu người dùng đã điền API key.
        Nếu chưa cấu hình key, trả về None ngay lập tức (0ms overhead) để chuyển sang Groq LPU.
        """
        if self.has_cerebras:
            try:
                return await self._call_oa_provider(
                    "Cerebras",
                    settings.CEREBRAS_API_KEY,
                    settings.CEREBRAS_BASE_URL,
                    settings.CEREBRAS_CHAT_MODEL,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=10.0,
                )
            except Exception as e:
                logger.warning(f"Cerebras Fast API lỗi, chuyển sang provider kế tiếp: {e}")

        if self.has_sambanova:
            try:
                return await self._call_oa_provider(
                    "SambaNova",
                    settings.SAMBANOVA_API_KEY,
                    settings.SAMBANOVA_BASE_URL,
                    settings.SAMBANOVA_CHAT_MODEL,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=12.0,
                )
            except Exception as e:
                logger.warning(f"SambaNova Fast API lỗi, chuyển sang provider kế tiếp: {e}")

        return None

    async def generate_code_response(
        self,
        messages: List[Dict[str, str]],
        groq_client=None,
        temperature: float = 0.3,
        max_tokens: int = 2800,
    ) -> str:
        """
        Chuỗi điều phối chuyên biệt để ĐỌC CODE & VIẾT CODE Free + Nhanh:
        1. Mistral Codestral (Free Coding API chuyên dụng nếu có CODESTRAL_API_KEY)
        2. Cerebras / SambaNova (nếu có key)
        3. OpenRouter Free Coder (qwen3-coder:free nếu có OPENROUTER_API_KEY)
        4. Groq LPU Coding (openai/gpt-oss-120b / qwen/qwen3.8-27b)
        5. Google Gemini Flash Coding (gemini-3.8-flash / gemini-3.5-flash)
        """
        # 1. Mistral Codestral (Free chuyên Code)
        if self.has_codestral:
            try:
                return await self._call_oa_provider(
                    "Mistral Codestral",
                    settings.CODESTRAL_API_KEY,
                    settings.CODESTRAL_BASE_URL,
                    settings.CODESTRAL_MODEL,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=25.0,
                )
            except Exception as e:
                logger.warning(f"Codestral API lỗi, fallback sang model code kế tiếp: {e}")

        # 2. Cerebras (tốc độ cực cao cho Qwen-3-32B code)
        if self.has_cerebras:
            try:
                return await self._call_oa_provider(
                    "Cerebras Coder",
                    settings.CEREBRAS_API_KEY,
                    settings.CEREBRAS_BASE_URL,
                    settings.CEREBRAS_CHAT_MODEL,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=18.0,
                )
            except Exception as e:
                logger.warning(f"Cerebras Coder lỗi: {e}")

        # 3. OpenRouter Free Coder
        if self.has_openrouter:
            try:
                return await self._call_oa_provider(
                    "OpenRouter Coder",
                    settings.OPENROUTER_API_KEY,
                    settings.OPENROUTER_BASE_URL,
                    settings.OPENROUTER_CODE_MODEL,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=25.0,
                )
            except Exception as e:
                logger.warning(f"OpenRouter Coder lỗi: {e}")

        # 4. Groq LPU (sẵn có GROQ_API_KEY)
        if groq_client and getattr(groq_client, "is_available", False):
            try:
                return await groq_client.chat_completion(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                logger.warning(f"Groq Coding lỗi, chuyển sang Gemini Flash Coding: {e}")

        # 5. Google Gemini Flash (sẵn có GEMINI_API_KEY)
        if self.has_gemini:
            return await self.chat_gemini_fast(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                prefer_coding=True,
            )

        raise RuntimeError("Không có API nào khả dụng để xử lý yêu cầu đọc/viết code.")


fast_llm_client = FastLLMClient()
