# src/voice/fish_audio_tts.py
import os
import hashlib
import logging
from typing import List, Optional, Dict, Any
import aiohttp

from src.voice.base import BaseTTSProvider
from src.config import settings

logger = logging.getLogger("Neneka.FishAudioTTS")

class FishAudioTTSProvider(BaseTTSProvider):
    """
    Fish Audio TTS Provider
    Sử dụng API của nền tảng Fish Audio (https://fish.audio)
    Hỗ trợ mô hình Anime / Voice Clone Neneka tiếng Nhật với độ tự nhiên cao.
    """
    API_URL = "https://api.fish.audio/v1/tts"

    def __init__(self, cache_dir: str = "audio_cache"):
        self.cache_dir = os.path.abspath(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.api_key = settings.FISH_AUDIO_API_KEY
        self.model_id = settings.FISH_AUDIO_MODEL_ID
        self.default_emotion = "Normal"

    def get_supported_languages(self) -> List[str]:
        return ["ja", "zh", "en"]

    def get_supported_emotions(self) -> List[str]:
        return ["Normal", "Happy", "Curious", "Sarcastic", "Serious", "Angry", "Sad", "Affectionate"]

    def get_audio_format(self) -> str:
        return "mp3"

    def _get_cache_path(self, text: str, emotion: str) -> str:
        key = f"fishaudio:{self.model_id}:{emotion}:{text}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return os.path.join(self.cache_dir, f"nnk_fish_{digest}.mp3")

    async def generate_speech(
        self,
        text: str,
        emotion: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        """Tạo file âm thanh qua Fish Audio API có bộ nhớ đệm SHA-256"""
        if not text or not text.strip():
            return None

        clean_text = text.strip()
        # Loại bỏ các đoạn miêu tả hành động dạng *...* nếu có
        if "*" in clean_text:
            parts = [p.strip() for p in clean_text.split("*") if p.strip()]
            clean_text = parts[-1] if parts else clean_text

        api_key = settings.FISH_AUDIO_API_KEY or self.api_key
        model_id = settings.FISH_AUDIO_MODEL_ID or self.model_id

        if not api_key:
            logger.warning("FISH_AUDIO_API_KEY chưa được cấu hình!")
            return None

        selected_emotion = emotion or self.default_emotion
        cache_file = self._get_cache_path(clean_text, selected_emotion)
        if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
            return cache_file

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload: Dict[str, Any] = {
            "text": clean_text,
            "format": "mp3"
        }

        if model_id:
            payload["reference_id"] = model_id

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.API_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=25)
                ) as resp:
                    if resp.status == 200:
                        audio_data = await resp.read()
                        with open(cache_file, "wb") as f:
                            f.write(audio_data)
                        logger.info(f"Đã tạo giọng Neneka thành công qua Fish Audio: {cache_file}")
                        return cache_file
                    else:
                        err_text = await resp.text()
                        logger.error(f"Fish Audio TTS lỗi ({resp.status}): {err_text}")
                        return None
        except Exception as e:
            logger.error(f"Lỗi khi kết nối Fish Audio API: {e}")
            return None
