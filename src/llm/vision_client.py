# src/llm/vision_client.py
import asyncio
import io
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


def convert_gif_to_storyboard_png(gif_bytes: bytes, max_frames: int = 3) -> Optional[bytes]:
    """
    Trích xuất tối đa 3 khung hình đại diện (Đầu - Giữa - Cuối) từ ảnh động GIF/WEBP
    và ghép ngang thành 1 dải ảnh PNG sắc nét để nhận diện hoàn hảo chuyển động của GIF.
    """
    try:
        from PIL import Image, ImageSequence

        with Image.open(io.BytesIO(gif_bytes)) as img:
            frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(img)]
            if not frames:
                return None

            if len(frames) == 1:
                selected = [frames[0]]
            elif len(frames) == 2 or max_frames <= 2:
                selected = [frames[0], frames[-1]]
            else:
                mid = len(frames) // 2
                selected = [frames[0], frames[mid], frames[-1]]

            # Thu nhỏ nhẹ nếu khung hình quá lớn để tăng tốc độ phản hồi Vision
            resized = []
            for f in selected:
                w, h = f.size
                if max(w, h) > 512:
                    scale = 512.0 / max(w, h)
                    f = f.resize((max(1, int(w * scale)), max(1, int(h * scale))))
                resized.append(f)

            total_w = sum(f.size[0] for f in resized) + (8 * (len(resized) - 1))
            max_h = max(f.size[1] for f in resized)
            canvas = Image.new("RGBA", (total_w, max_h), (24, 24, 28, 255))

            x_offset = 0
            for f in resized:
                canvas.paste(f, (x_offset, 0))
                x_offset += f.size[0] + 8

            out = io.BytesIO()
            canvas.convert("RGB").save(out, format="PNG", optimize=True)
            return out.getvalue()
    except Exception as e:
        logger.debug(f"Không thể chuyển GIF sang storyboard PNG: {e}")
        return None


class VisionClient:
    """
    Client đa phương thức (Multimodal Vision & GIF Client) sử dụng Google Gemini SDK.
    Chuyên trách nhận diện ảnh tĩnh, ảnh chụp code/màn hình, meme và ảnh động GIF (Tenor/Giphy/Discord).
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
        system_instruction: str = "",
        media_hint: Optional[str] = None,
    ) -> str:
        """
        Nhận diện và phân tích hình ảnh hoặc ảnh động GIF kết hợp với System Prompt của Neneka:
        - Hỗ trợ đọc ảnh code, meme, screenshot và cả ảnh động GIF (trích xuất chuyển động 3 khung hình khi cần).
        - Tự động fallback qua các model vision nếu một model bị quá tải hoặc lỗi.
        """
        if not self.is_available:
            raise RuntimeError("Gemini Vision API chưa được cấu hình GEMINI_API_KEY!")

        clean_mime = mime_type.split(";")[0].strip().lower()
        if clean_mime not in ["image/png", "image/jpeg", "image/webp", "image/gif"]:
            clean_mime = "image/png"

        is_gif = (clean_mime == "image/gif") or (media_hint and "gif" in media_hint.lower())

        # Với GIF nặng (> 3.5MB), chuyển thành dải 3 khung hình (đầu-giữa-cuối) để gửi siêu tốc
        use_bytes = image_bytes
        use_mime = clean_mime
        storyboard_backup: Optional[bytes] = None
        if clean_mime == "image/gif":
            storyboard_backup = convert_gif_to_storyboard_png(image_bytes)
            if len(image_bytes) > 3.5 * 1024 * 1024 and storyboard_backup:
                use_bytes = storyboard_backup
                use_mime = "image/png"

        if user_prompt.strip():
            clean_prompt = user_prompt.strip()
        elif is_gif:
            clean_prompt = (
                "Người dùng vừa gửi một ảnh động GIF trong cuộc trò chuyện Discord. "
                "Hãy nắm bắt biểu cảm/hành động trong GIF và đáp lại thật tự nhiên, ngắn gọn, dí dỏm đúng mạch chat."
            )
        else:
            clean_prompt = (
                "Quan sát bức ảnh này (nếu là ảnh chụp code/lỗi thì đọc và giải thích/sửa lỗi; nếu là meme/ảnh thường thì bình luận tự nhiên, thông minh, gần gũi như đang chat Discord)."
            )

        if media_hint:
            clean_prompt = f"[Ngữ cảnh đính kèm: {media_hint}]\n{clean_prompt}"

        image_part = types.Part.from_bytes(data=use_bytes, mime_type=use_mime)
        contents = [image_part, clean_prompt]
        config = types.GenerateContentConfig(
            system_instruction=system_instruction if system_instruction else None,
            temperature=0.72,
            max_output_tokens=1500
        )

        last_error = None
        for model_candidate in self.models:
            for attempt in range(1, 3):
                try:
                    logger.info(f"Đang phân tích {'GIF' if is_gif else 'ảnh'} với model {model_candidate} (Lần {attempt})...")
                    result_text = await asyncio.to_thread(
                        self._sync_generate,
                        model_name=model_candidate,
                        contents=contents,
                        config=config
                    )
                    if result_text:
                        return result_text
                except Exception as e:
                    logger.warning(f"Lỗi khi nhận diện ảnh/GIF bằng model {model_candidate} (Attempt {attempt}): {e}")
                    last_error = e
                    # Nếu lỗi do định dạng image/gif thô, chuyển sang bản storyboard PNG ngay ở lần thử kế tiếp
                    if use_mime == "image/gif" and storyboard_backup:
                        use_bytes = storyboard_backup
                        use_mime = "image/png"
                        contents = [types.Part.from_bytes(data=use_bytes, mime_type="image/png"), clean_prompt]
                    await asyncio.sleep(0.5 * attempt)

        raise RuntimeError(f"Tất cả các model Vision đều thất bại khi nhận diện ảnh/GIF. Lỗi cuối: {last_error}")


vision_client = VisionClient()
