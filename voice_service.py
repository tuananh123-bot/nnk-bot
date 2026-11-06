# voice_service.py
import os
import asyncio
import base64
from typing import Optional

class VoiceService:
    """
    Hệ thống tạo giọng nói tiếng Nhật anime chuẩn nhân vật Neneka (Utsushimi Neneka).
    - Ưu tiên 1: Gemini 3.8 Flash TTS với Voice Persona riêng biệt (voice_lcogojy42c6q)
      được thiết kế riêng theo chất giọng trầm ấm, điềm đạm, quyến rũ và kiêu kỳ của Thất Vương Neneka.
    - Dự phòng 2: Edge-TTS Neural được hạ cao độ (pitch -14Hz) và tốc độ (-6%) để giữ chất giọng trưởng thành.
    """
    def __init__(self, gemini_api_key: Optional[str] = None):
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        # ID giọng Voice Design riêng biệt cho Neneka (Gemini 3.8 Flash TTS)
        self.gemini_voice_id = "voice_lcogojy42c6q"
        self.default_voice_edge = "ja-JP-NanamiNeural"
        self.output_dir = os.path.join(os.path.dirname(__file__), "temp_audio")
        os.makedirs(self.output_dir, exist_ok=True)

    def _generate_gemini_tts(self, text_ja: str, output_file: str) -> bool:
        """Tạo giọng nói tiếng Nhật bằng Gemini 3.8 Flash TTS với Voice Persona của Neneka"""
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
                            "style": "calm, elegant, mature and teasing anime lady tone, gentle onee-san chuckle",
                        }]
                    }],
                }],
                response_format={"type": "audio"},
                generation_config={
                    "speech_config": [
                        {"voice": self.gemini_voice_id}
                    ]
                },
            )
            if interaction.output_audio and interaction.output_audio.data:
                data = base64.b64decode(interaction.output_audio.data)
                with open(output_file, "wb") as f:
                    f.write(data)
                return True
        except Exception as e:
            print(f"[VoiceService Warning] Gemini Custom TTS gặp lỗi: {e}")
        return False

    async def _generate_edge_tts(self, text_ja: str, output_file: str) -> bool:
        """Tạo giọng nói tiếng Nhật dự phòng qua Edge-TTS với tông trầm trưởng thành"""
        try:
            import edge_tts
            # Hạ cao độ (-14Hz) và làm chậm (-6%) để giọng Nanami không bị trẻ con/nhí nhảnh
            communicate = edge_tts.Communicate(
                text=text_ja,
                voice=self.default_voice_edge,
                rate="-6%",
                pitch="-14Hz"
            )
            await communicate.save(output_file)
            return os.path.exists(output_file) and os.path.getsize(output_file) > 0
        except Exception as e:
            print(f"[VoiceService Warning] Edge-TTS lỗi: {e}")
            return False

    async def generate_voice(self, text_ja: str, custom_filename: Optional[str] = None) -> Optional[str]:
        """
        Chuyển câu tiếng Nhật thành file âm thanh giọng Neneka.
        Trả về đường dẫn tới file âm thanh (.wav hoặc .mp3) nếu thành công, None nếu thất bại.
        """
        if not text_ja or not text_ja.strip():
            return None

        clean_text = text_ja.strip()
        # Loại bỏ các ký tự hành động trong dấu hoa thị *...*
        if clean_text.startswith("*") and "*" in clean_text[1:]:
            parts = clean_text.split("*")
            clean_text = parts[-1].strip()

        base_name = f"neneka_{int(asyncio.get_event_loop().time() * 1000)}"

        # 1. ƯU TIÊN: Gọi Gemini TTS với Voice Persona riêng của Neneka
        if self.gemini_api_key:
            wav_output = os.path.join(self.output_dir, f"{base_name}.wav")
            success_gemini = await asyncio.to_thread(self._generate_gemini_tts, clean_text, wav_output)
            if success_gemini:
                return wav_output

        # 2. DỰ PHÒNG: Nếu Gemini lỗi/hết hạn, dùng Edge-TTS đã chỉnh tông trầm
        mp3_output = os.path.join(self.output_dir, f"{base_name}.mp3")
        success_edge = await self._generate_edge_tts(clean_text, mp3_output)
        if success_edge:
            return mp3_output

        return None

    def generate_voice_sync(self, text_ja: str, custom_filename: Optional[str] = None) -> Optional[str]:
        """Bản đồng bộ cho CLI hoặc môi trường non-async"""
        return asyncio.run(self.generate_voice(text_ja, custom_filename))
