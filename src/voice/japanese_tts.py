# src/voice/japanese_tts.py
import os
import hashlib
import asyncio
import logging
from typing import List, Optional, Dict, Any

from src.voice.base import BaseTTSProvider
from src.voice.elevenlabs_tts import ElevenLabsTTSProvider
from src.voice.sovits_tts import GPTSoVITSTTSProvider
from src.config import settings

logger = logging.getLogger("Neneka.JapaneseTTS")

EMOTION_PRESETS: Dict[str, Dict[str, str]] = {
    "Normal": {"rate": "-6%", "pitch": "-14Hz"},
    "Happy": {"rate": "-2%", "pitch": "-10Hz"},
    "Curious": {"rate": "-4%", "pitch": "-12Hz"},
    "Sarcastic": {"rate": "-8%", "pitch": "-16Hz"},
    "Serious": {"rate": "-10%", "pitch": "-18Hz"},
    "Angry": {"rate": "+2%", "pitch": "-12Hz"},
    "Sad": {"rate": "-12%", "pitch": "-20Hz"},
    "Embarrassed": {"rate": "+0%", "pitch": "-8Hz"},
    "Affectionate": {"rate": "-8%", "pitch": "-16Hz"},
    "Surprised": {"rate": "+4%", "pitch": "-6Hz"}
}

class JapaneseTTSProvider(BaseTTSProvider):
    """
    Japanese TTS Provider chuyên biệt cho nhân vật Neneka
    - Hỗ trợ Voice Cloning qua ElevenLabs (Instant Voice Cloning) và GPT-SoVITS
    - Fallback mượt mà sang Licensed Neural TTS (Edge-TTS Nanami)
    - Tinh chỉnh cao độ và trường độ để thể hiện phong thái trưởng thành, điềm đạm, kiêu kỳ
    - 10 Preset cảm xúc chuyên biệt (Normal, Happy, Curious, Sarcastic, Serious, v.v.)
    - Bộ nhớ đệm âm thanh (Audio Cache) dựa trên hash SHA-256
    """
    def __init__(self, cache_dir: str = "audio_cache"):
        self.cache_dir = os.path.abspath(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.voice_id = settings.DEFAULT_JAPANESE_VOICE
        self.default_emotion = "Normal"
        self.default_speed = settings.VOICE_RATE_ADJUST
        self.default_pitch = settings.VOICE_PITCH_ADJUST

        # Khởi tạo các provider Voice Cloning
        self.elevenlabs_provider = ElevenLabsTTSProvider(cache_dir=cache_dir)
        self.sovits_provider = GPTSoVITSTTSProvider(cache_dir=cache_dir)

    def get_supported_languages(self) -> List[str]:
        return ["ja"]

    def get_supported_emotions(self) -> List[str]:
        return list(EMOTION_PRESETS.keys())

    def get_audio_format(self) -> str:
        return "mp3"

    def configure_voice(self, voice_id: str):
        self.voice_id = voice_id

    def configure_speed(self, speed: str):
        self.default_speed = speed

    def configure_pitch(self, pitch: str):
        self.default_pitch = pitch

    def configure_emotion(self, emotion: str):
        if emotion in EMOTION_PRESETS:
            self.default_emotion = emotion

    def _get_cache_path(self, text: str, emotion: str) -> str:
        key = f"{self.voice_id}:{emotion}:{text}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return os.path.join(self.cache_dir, f"nnk_{digest}.mp3")

    async def generate_speech(
        self,
        text: str,
        emotion: Optional[str] = None,
        speed: Optional[str] = None,
        pitch: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        """Tạo file âm thanh tiếng Nhật từ văn bản (có hỗ trợ Voice Clone & bộ nhớ đệm)"""
        if not text or not text.strip():
            return None

        clean_text = text.strip()
        # Loại bỏ các đoạn hành động dạng *...* nếu có
        if "*" in clean_text:
            parts = [p.strip() for p in clean_text.split("*") if p.strip()]
            clean_text = parts[-1] if parts else clean_text

        selected_emotion = emotion or self.default_emotion

        # 1. Thử nghiệm Voice Cloning với ElevenLabs nếu được cấu hình
        if settings.TTS_PROVIDER == "elevenlabs" or (settings.ELEVENLABS_API_KEY and settings.ELEVENLABS_VOICE_ID):
            audio = await self.elevenlabs_provider.generate_speech(clean_text, emotion=selected_emotion)
            if audio:
                return audio
            logger.warning("ElevenLabs Voice Clone thất bại hoặc hết quota, đang fallback sang Edge-TTS...")

        # 2. Thử nghiệm Voice Cloning với GPT-SoVITS nếu được cấu hình
        if settings.TTS_PROVIDER == "gpt_sovits":
            audio = await self.sovits_provider.generate_speech(clean_text, emotion=selected_emotion)
            if audio:
                return audio
            logger.warning("GPT-SoVITS Voice Clone thất bại, đang fallback sang Edge-TTS...")

        # 3. Mặc định / Fallback sang Edge-TTS
        preset = EMOTION_PRESETS.get(selected_emotion, EMOTION_PRESETS["Normal"])
        applied_rate = speed or preset["rate"]
        applied_pitch = pitch or preset["pitch"]

        cache_file = self._get_cache_path(clean_text, selected_emotion)
        if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
            return cache_file

        try:
            import edge_tts
            communicate = edge_tts.Communicate(
                text=clean_text,
                voice=self.voice_id,
                rate=applied_rate,
                pitch=applied_pitch
            )
            await communicate.save(cache_file)
            if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
                return cache_file
        except Exception as e:
            logger.error(f"Lỗi khi tạo Japanese TTS: {e}")

        return None

japanese_tts = JapaneseTTSProvider()


