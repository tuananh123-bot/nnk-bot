# voice_service.py
import os
import asyncio
import base64
import tempfile
from typing import Optional

class VoiceService:
    """
    Hệ thống tạo giọng nói tiếng Nhật anime cho Neneka (Utsushimi Neneka).
    Hỗ trợ 2 engine tự động dự phòng:
    1. Edge-TTS: Miễn phí, tốc độ cao, chất lượng giọng Anime tự nhiên (ja-JP-NanamiNeural).
    2. Gemini TTS (gemini-3.8-flash-tts): Dự phòng thông qua Gemini API khi cần.
    """
    def __init__(self, gemini_api_key: Optional[str] = None):
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.default_voice_edge = "ja-JP-NanamiNeural"
        self.output_dir = os.path.join(os.path.dirname(__file__), "temp_audio")
        os.makedirs(self.output_dir, exist_ok=True)

    async def _generate_edge_tts(self, text_ja: str, output_file: str) -> bool:
        """Tạo giọng nói tiếng Nhật bằng Edge-TTS"""
        try:
            import edge_tts
            # Tinh chỉnh rate và pitch để giọng có nét kiêu kỳ, điềm tĩnh của Neneka
            communicate = edge_tts.Communicate(
                text=text_ja,
                voice=self.default_voice_edge,
                rate="-2%",
                pitch="-1Hz"
            )
            await communicate.save(output_file)
            return os.path.exists(output_file) and os.path.getsize(output_file) > 0
        except Exception as e:
            print(f"[VoiceService Warning] Edge-TTS lỗi: {e}")
            return False

    def _generate_gemini_tts(self, text_ja: str, output_file: str) -> bool:
        """Tạo giọng nói tiếng Nhật bằng Gemini 3.8 Flash TTS"""
        if not self.gemini_api_key:
            return False
        try:
            from google import genai
            client = genai.Client(api_key=self.gemini_api_key)
            interaction = client.interactions.create(
                model="gemini-3.8-flash-tts",
                input=[{
                    "type": "user_input",
                    "content": [{
                        "type": "text",
                        "text": text_ja,
                        "annotations": [{
                            "type": "speech_metadata",
                            "style": "playful, mature anime lady tone, gentle and teasing",
                        }]
                    }],
                }],
                response_format={"type": "audio"},
                generation_config={
                    "speech_config": [
                        {"voice": "Aoede"}
                    ]
                },
            )
            if interaction.output_audio and interaction.output_audio.data:
                data = base64.b64decode(interaction.output_audio.data)
                with open(output_file, "wb") as f:
                    f.write(data)
                return True
        except Exception as e:
            print(f"[VoiceService Warning] Gemini TTS lỗi: {e}")
        return False

    async def generate_voice(self, text_ja: str, custom_filename: Optional[str] = None) -> Optional[str]:
        """
        Chuyển câu tiếng Nhật thành file âm thanh.
        Trả về đường dẫn tới file âm thanh (.mp3 hoặc .wav) nếu thành công, None nếu thất bại.
        """
        if not text_ja or not text_ja.strip():
            return None

        clean_text = text_ja.strip()
        # Loại bỏ các ký tự dấu hoa thị hành động nếu có lọt vào tiếng Nhật
        if clean_text.startswith("*") and "*" in clean_text[1:]:
            parts = clean_text.split("*")
            clean_text = parts[-1].strip()

        fname = custom_filename or f"neneka_{int(asyncio.get_event_loop().time() * 1000)}.mp3"
        output_path = os.path.join(self.output_dir, fname)

        # 1. Thử Edge-TTS trước (nhanh, định dạng MP3 nhẹ, không tốn quota)
        success = await self._generate_edge_tts(clean_text, output_path)
        if success:
            return output_path

        # 2. Dự phòng sang Gemini TTS nếu Edge-TTS gặp lỗi mạng
        wav_output = output_path.replace(".mp3", ".wav")
        success_gemini = await asyncio.to_thread(self._generate_gemini_tts, clean_text, wav_output)
        if success_gemini:
            return wav_output

        return None

    def generate_voice_sync(self, text_ja: str, custom_filename: Optional[str] = None) -> Optional[str]:
        """Bản đồng bộ cho CLI hoặc môi trường non-async"""
        return asyncio.run(self.generate_voice(text_ja, custom_filename))
