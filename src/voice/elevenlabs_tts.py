# src/voice/elevenlabs_tts.py
import os
import hashlib
import logging
from typing import List, Optional, Dict, Any
import aiohttp

from src.voice.base import BaseTTSProvider
from src.config import settings

logger = logging.getLogger("Neneka.ElevenLabsTTS")

# Emotion mapping for ElevenLabs Voice Cloning
ELEVEN_EMOTION_SETTINGS: Dict[str, Dict[str, float]] = {
    "Normal": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.15},
    "Happy": {"stability": 0.45, "similarity_boost": 0.80, "style": 0.35},
    "Curious": {"stability": 0.50, "similarity_boost": 0.85, "style": 0.25},
    "Sarcastic": {"stability": 0.40, "similarity_boost": 0.85, "style": 0.40},
    "Serious": {"stability": 0.65, "similarity_boost": 0.90, "style": 0.10},
    "Angry": {"stability": 0.35, "similarity_boost": 0.80, "style": 0.45},
    "Sad": {"stability": 0.60, "similarity_boost": 0.85, "style": 0.20},
    "Embarrassed": {"stability": 0.45, "similarity_boost": 0.80, "style": 0.30},
    "Affectionate": {"stability": 0.50, "similarity_boost": 0.90, "style": 0.25},
    "Surprised": {"stability": 0.40, "similarity_boost": 0.80, "style": 0.40}
}

class ElevenLabsTTSProvider(BaseTTSProvider):
    """
    ElevenLabs Instant Voice Cloning Provider
    Sử dụng file mẫu giọng Neneka để nhân bản và phát ra giọng nói tiếng Nhật giống hệt file ghi âm.
    """
    def __init__(self, cache_dir: str = "audio_cache"):
        self.cache_dir = os.path.abspath(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.api_key = settings.ELEVENLABS_API_KEY
        self.voice_id = settings.ELEVENLABS_VOICE_ID
        self.model_id = settings.ELEVENLABS_MODEL_ID
        self.default_emotion = "Normal"

    def get_supported_languages(self) -> List[str]:
        return ["ja", "vi", "en"]

    def get_supported_emotions(self) -> List[str]:
        return list(ELEVEN_EMOTION_SETTINGS.keys())

    def get_audio_format(self) -> str:
        return "mp3"

    def _get_cache_path(self, text: str, emotion: str) -> str:
        key = f"elevenlabs:{self.voice_id}:{emotion}:{text}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return os.path.join(self.cache_dir, f"nnk_el_{digest}.mp3")

    async def generate_speech(
        self,
        text: str,
        emotion: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        if not text or not text.strip():
            return None

        if not self.api_key or not self.voice_id:
            logger.warning("ELEVENLABS_API_KEY hoặc ELEVENLABS_VOICE_ID chưa được cấu hình!")
            return None

        clean_text = text.strip()
        if "*" in clean_text:
            parts = [p.strip() for p in clean_text.split("*") if p.strip()]
            clean_text = parts[-1] if parts else clean_text

        selected_emotion = emotion or self.default_emotion
        v_settings = ELEVEN_EMOTION_SETTINGS.get(selected_emotion, ELEVEN_EMOTION_SETTINGS["Normal"])

        cache_file = self._get_cache_path(clean_text, selected_emotion)
        if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
            return cache_file

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        payload = {
            "text": clean_text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": v_settings["stability"],
                "similarity_boost": v_settings["similarity_boost"],
                "style": v_settings["style"],
                "use_speaker_boost": True
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        audio_data = await resp.read()
                        with open(cache_file, "wb") as f:
                            f.write(audio_data)
                        logger.info(f"Đã tạo giọng clone Neneka thành công qua ElevenLabs: {cache_file}")
                        return cache_file
                    else:
                        err_text = await resp.text()
                        logger.error(f"ElevenLabs TTS lỗi ({resp.status}): {err_text}")
                        return None
        except Exception as e:
            logger.error(f"Lỗi khi kết nối ElevenLabs API: {e}")
            return None
