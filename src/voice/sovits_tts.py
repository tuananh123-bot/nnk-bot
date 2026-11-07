# src/voice/sovits_tts.py
import os
import hashlib
import logging
from typing import List, Optional, Dict, Any
import aiohttp

from src.voice.base import BaseTTSProvider
from src.config import settings

logger = logging.getLogger("Neneka.GPTSoVITS")

class GPTSoVITSTTSProvider(BaseTTSProvider):
    """
    GPT-SoVITS / Open-Source Voice Clone Provider
    Kết nối tới API GPT-SoVITS local hoặc trên Google Colab / Server riêng
    Sử dụng file ghi âm mẫu Neneka làm prompt audio.
    """
    def __init__(self, cache_dir: str = "audio_cache"):
        self.cache_dir = os.path.abspath(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.api_url = settings.SOVITS_API_URL.rstrip("/")
        self.ref_audio_path = os.path.abspath(os.path.join("assets", "voice_samples", "neneka_sample_short.mp3"))
        self.ref_prompt_text = "もう一人の私よ。セブンクラウンズの力が必要なのですね。いいでしょう、そこでじっくりと見ていなさい。"
        self.ref_language = "ja"

    def get_supported_languages(self) -> List[str]:
        return ["ja", "zh", "en"]

    def get_supported_emotions(self) -> List[str]:
        return ["Normal", "Happy", "Serious", "Angry", "Sad"]

    def get_audio_format(self) -> str:
        return "wav"

    def _get_cache_path(self, text: str, emotion: str) -> str:
        key = f"sovits:{emotion}:{text}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return os.path.join(self.cache_dir, f"nnk_sovits_{digest}.wav")

    async def generate_speech(
        self,
        text: str,
        emotion: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        if not text or not text.strip():
            return None

        clean_text = text.strip()
        if "*" in clean_text:
            parts = [p.strip() for p in clean_text.split("*") if p.strip()]
            clean_text = parts[-1] if parts else clean_text

        cache_file = self._get_cache_path(clean_text, emotion or "Normal")
        if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
            return cache_file

        url = f"{self.api_url}/tts"
        payload = {
            "text": clean_text,
            "text_lang": "ja",
            "ref_audio_path": self.ref_audio_path,
            "prompt_text": self.ref_prompt_text,
            "prompt_lang": self.ref_language,
            "top_k": 5,
            "top_p": 1.0,
            "temperature": 1.0,
            "speed": 1.0
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        audio_data = await resp.read()
                        with open(cache_file, "wb") as f:
                            f.write(audio_data)
                        logger.info(f"Đã tạo giọng clone Neneka qua GPT-SoVITS: {cache_file}")
                        return cache_file
                    else:
                        err_text = await resp.text()
                        logger.error(f"GPT-SoVITS lỗi ({resp.status}): {err_text}")
                        return None
        except Exception as e:
            logger.error(f"Lỗi khi kết nối GPT-SoVITS API ({self.api_url}): {e}")
            return None

