# src/llm/vision_client.py
import asyncio
import logging
from typing import Optional, List, Tuple
from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger("Neneka.VisionClient")

DEFAULT_VISION_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash"
]

class VisionClient:
    """
    Client đa phương thức (Multimodal Vision Client) sử dụng Google Gemini SDK.
    Chuyên trách nhận diện hình ảnh, phân tích ảnh chụp/meme/fanart và phản hồi
    bằng nhận thức sắc bén của Thất Vương Neneka.
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        models: Optional[List[str]] = None
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.models = models or DEFAULT_VISION_MODELS
        self._client: Optional[genai.Client] = None

        if self.api_key:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Khởi tạo Gemini Vision Client thất bại: {e}")

    @property
    def is_available(self) -> bool:
        return bool(self._client and self.api_key)

    def _sync_generate(
        self,
        model_name: str,
        contents: list,
        config: Optional[types.GenerateContentConfig] = None
    ) -> str:
        """Hàm đồng bộ gọi Gemini API để thực thi trong asyncio worker thread"""
        response = self._client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )
        return (response.text or "").strip()

    async def analyze_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        user_prompt: str = "",
        system_instruction: str = ""
    ) -> str:
        """
        Nhận diện và phân tích hình ảnh kết hợp với System Prompt của Neneka:
        - Tự động fallback qua các model vision nếu một model bị quá tải hoặc lỗi
        - Chạy non-blocking qua asyncio.to_thread
        """
        if not self.is_available:
            raise RuntimeError("Gemini Vision API chưa được cấu hình GEMINI_API_KEY!")

        # Chuẩn hóa MIME Type cho ảnh
        clean_mime = mime_type.split(";")[0].strip().lower()
        if clean_mime not in ["image/png", "image/jpeg", "image/webp", "image/gif"]:
            clean_mime = "image/png"

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=clean_mime)
        clean_prompt = user_prompt.strip() if user_prompt else (
            "Hãy quan sát kỹ bức ảnh này và đưa ra nhận xét, cảm nghĩ, hoặc giải thích chi tiết những gì ngươi nhìn thấy "
            "theo đúng phong thái quý cô Thất Vương Neneka (thông thái, sắc sảo, ân cần và hơi trêu đùa)."
        )

        contents = [image_part, clean_prompt]
        config = types.GenerateContentConfig(
            system_instruction=system_instruction if system_instruction else None,
            temperature=0.75,
            max_output_tokens=1500
        )

        last_error = None
        for model_candidate in self.models:
            for attempt in range(1, 3):
                try:
                    logger.info(f"Đang phân tích hình ảnh với model {model_candidate} (Lần thử {attempt})...")
                    result_text = await asyncio.to_thread(
                        self._sync_generate,
                        model_name=model_candidate,
                        contents=contents,
                        config=config
                    )
                    if result_text:
                        return result_text
                except Exception as e:
                    logger.warning(f"Lỗi khi nhận diện ảnh bằng model {model_candidate} (Attempt {attempt}): {e}")
                    last_error = e
                    await asyncio.sleep(1.0 * attempt)

        raise RuntimeError(f"Tất cả các model Vision đều thất bại khi nhận diện ảnh. Lỗi cuối: {last_error}")


vision_client = VisionClient()
