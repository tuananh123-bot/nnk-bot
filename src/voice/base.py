# src/voice/base.py
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

class BaseTTSProvider(ABC):
    """Giao diện trừu tượng chuẩn mực cho mọi Voice / TTS Provider"""

    @abstractmethod
    async def generate_speech(self, text: str, **kwargs) -> Optional[str]:
        """Tạo file âm thanh và trả về đường dẫn file kết quả"""
        pass

    @abstractmethod
    def get_supported_languages(self) -> List[str]:
        """Danh sách mã ngôn ngữ hỗ trợ (vd: ['ja', 'vi', 'en'])"""
        pass

    @abstractmethod
    def get_supported_emotions(self) -> List[str]:
        """Danh sách cảm xúc hỗ trợ"""
        pass

    @abstractmethod
    def get_audio_format(self) -> str:
        """Định dạng âm thanh đầu ra (vd: 'mp3', 'wav')"""
        pass
