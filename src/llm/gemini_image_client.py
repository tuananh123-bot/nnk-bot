# src/llm/gemini_image_client.py
"""
Client vẽ tranh và tạo ảnh thông qua Google Gemini Nano Banana (Flash Image).
Model mặc định: gemini-2.5-flash-image / gemini-nano-banana-2.1 (Nano Banana 🍌)
"""

import asyncio
import base64
import io
import logging
from typing import Dict, Any, Optional, List
from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger("Neneka.GeminiImage")

DEFAULT_NANO_BANANA_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-nano-banana-2.1",
    "gemini-3.1-flash-lite-image",
]


class GeminiImageClient:
    """Client tương tác với Google Gemini để tạo ảnh thông thường bằng Nano Banana."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key if api_key is not None else getattr(settings, "GEMINI_API_KEY", "")
        self.model = model or getattr(settings, "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> Optional[genai.Client]:
        if self._client is None and self.api_key:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Khởi tạo Gemini Client thất bại: {e}")
        return self._client

    def is_available(self) -> bool:
        """Kiểm tra Gemini API Key có sẵn sàng không."""
        return bool(self.api_key and len(self.api_key) > 10)

    def _sync_generate(self, model_name: str, prompt: str, aspect_ratio: str) -> bytes:
        """Hàm đồng bộ gọi Gemini API để thực thi trong worker thread."""
        client = self._get_client()
        if not client:
            raise RuntimeError("Gemini Client chưa được khởi tạo.")

        # 1. Thử Interactions API trước (Nano Banana 2.1 / 3.1 Flash Image)
        try:
            interaction = client.interactions.create(
                model=model_name,
                input=prompt,
                response_format={
                    "type": "image",
                    "aspect_ratio": aspect_ratio,
                },
            )
            if hasattr(interaction, "output_image") and interaction.output_image:
                data = getattr(interaction.output_image, "data", None)
                if data:
                    return base64.b64decode(data)
        except Exception as e_inter:
            logger.debug(f"Interactions API cho model {model_name} chưa hỗ trợ, thử generate_content: {e_inter}")

        # 2. Fallback sang classic generate_content
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=aspect_ratio,
            ),
        )

        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )

        for part in resp.parts:
            if part.inline_data and part.inline_data.data:
                return part.inline_data.data

        raise RuntimeError(f"Gemini Nano Banana không trả về dữ liệu ảnh hợp lệ.")

    async def generate_image(
        self,
        prompt: str,
        orientation: str = "portrait",
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sinh ảnh bằng Google Gemini Nano Banana.
        """
        if not self.is_available():
            raise RuntimeError("GEMINI_API_KEY chưa được cấu hình.")

        # Ánh xạ orientation sang aspect_ratio của Gemini
        if orientation == "landscape":
            aspect_ratio = "16:9"
        elif orientation == "square":
            aspect_ratio = "1:1"
        else:
            aspect_ratio = "9:16"

        chosen_model = model or self.model
        models_to_try = [chosen_model] + [m for m in DEFAULT_NANO_BANANA_MODELS if m != chosen_model]

        last_err = None
        for m in models_to_try:
            try:
                logger.info(f"Đang tạo ảnh với Google Nano Banana [{m}] (ratio={aspect_ratio})...")
                img_bytes = await asyncio.to_thread(self._sync_generate, m, prompt, aspect_ratio)
                return {
                    "image_bytes": img_bytes,
                    "model": f"Google Nano Banana ({m})",
                    "prompt": prompt,
                    "provider": "Google Gemini (Nano Banana 🍌)",
                    "orientation": orientation,
                }
            except Exception as e:
                err_str = str(e)
                logger.warning(f"Google Nano Banana model [{m}] lỗi: {err_str}")
                last_err = e
                # Nếu là lỗi hết hạn mức hoặc rate limit thì dừng ngay
                if "ResourceExhausted" in err_str or "quota" in err_str.lower() or "limit exceeded" in err_str.lower():
                    break

        raise RuntimeError(f"Google Nano Banana thất bại: {last_err}")


gemini_image_client = GeminiImageClient()
