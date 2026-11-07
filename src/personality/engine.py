# src/personality/engine.py
import re
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from src.personality.prompts import (
    NENEKA_CANON_BASE_PROMPT,
    NENEKA_VIETNAMESE_STYLE_PROMPT,
    NENEKA_JAPANESE_STYLE_PROMPT,
    NENEKA_CANON_FACTS
)

@dataclass
class PersonalityState:
    confidence: int = 85      # 0-100: Độ tự tin, phong thái bề trên
    curiosity: int = 75       # 0-100: Tính hiếu kỳ, tò mò khám phá
    affection: int = 150      # 0-1000: Mức độ hảo cảm
    trust: int = 40           # 0-100: Độ tin tưởng
    amusement: int = 50       # 0-100: Thích thú, trêu đùa
    irritation: int = 10      # 0-100: Bực bội, khó chịu
    seriousness: int = 70     # 0-100: Độ nghiêm túc lý tính
    emotional_state: str = "calm_analytical"

    def clamp(self):
        self.confidence = max(0, min(100, self.confidence))
        self.curiosity = max(0, min(100, self.curiosity))
        self.affection = max(0, min(1000, self.affection))
        self.trust = max(0, min(100, self.trust))
        self.amusement = max(0, min(100, self.amusement))
        self.irritation = max(0, min(100, self.irritation))
        self.seriousness = max(0, min(100, self.seriousness))

class PersonalityEngine:
    """
    Personality Engine duy trì tính cách nhất quán, phản ứng cảm xúc logic
    và điều phối System Prompt dựa trên ngữ cảnh và trạng thái nội tâm.
    """
    def __init__(self, initial_state: Optional[PersonalityState] = None):
        self.state = initial_state or PersonalityState()

    @staticmethod
    def detect_language(text: str) -> str:
        """Phát hiện ngôn ngữ người dùng nhập (ja, en, vi)"""
        if not text:
            return "vi"
        # Japanese Kana / Kanji
        if any(('\u3040' <= c <= '\u30ff') or ('\u4e00' <= c <= '\u9fff') for c in text):
            return "ja"
        # Vietnamese diacritics
        vn_chars = "àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
        if any(c in vn_chars for c in text.lower()):
            return "vi"
        # Default English or Vietnamese fallback
        return "vi"

    def update_from_interaction(
        self,
        user_message: str,
        affection_delta: int = 0,
        trust_delta: int = 0,
        irritation_delta: int = 0,
        amusement_delta: int = 0,
        new_emotion: Optional[str] = None
    ):
        """Cập nhật các biến tính cách theo biến cố tương tác hợp lý"""
        lower = user_message.lower()

        # 1. Phát hiện trêu chọc tuổi tác / chiều cao (Điểm nhạy cảm canon)
        if any(k in lower for k in ["bà già", "bà cô", "lùn", "nấm lùn", "bé hạt tiêu", "chân ngắn", "loli"]):
            self.state.irritation += 25
            self.state.amusement += 10
            self.state.seriousness += 15
            self.state.emotional_state = "annoyed_chilly"
            self.state.affection = max(0, self.state.affection - 5)

        # 2. Phát hiện khen ngợi / tán tỉnh (Kích hoạt tsundere / ngượng ngùng)
        elif any(k in lower for k in ["dễ thương", "đáng yêu", "xinh đẹp", "thích em", "yêu em", "tuyệt vời", "kawaii", "suki"]):
            self.state.amusement += 15
            self.state.affection += 8
            self.state.trust += 4
            self.state.emotional_state = "slight_tsundere"

        # 3. Mệt mỏi / than thở (Kích hoạt bản năng bảo bọc / quan tâm)
        elif any(k in lower for k in ["mệt", "kiệt sức", "áp lực", "stress", "buồn", "thất bại", "otsu"]):
            self.state.seriousness += 10
            self.state.trust += 5
            self.state.affection += 5
            self.state.emotional_state = "protective_sister"

        # 4. Áp dụng delta từ bên ngoài nếu có
        self.state.affection += affection_delta
        self.state.trust += trust_delta
        self.state.irritation += irritation_delta
        self.state.amusement += amusement_delta

        if new_emotion:
            self.state.emotional_state = new_emotion

        self.state.clamp()

    def get_system_prompt(self, user_language: str = "vi", user_name: str = "Hiệp sĩ") -> str:
        """Tổng hợp System Prompt đa tầng chuẩn mực cho Neneka"""
        st = self.state

        if user_language == "ja":
            lang_instruction = "IMPORTANT: The user message is in Japanese. Reply in natural, elegant Japanese anime style adhering to the Japanese style prompt."
            style_section = NENEKA_JAPANESE_STYLE_PROMPT
        elif user_language == "en":
            lang_instruction = "IMPORTANT: The user message is in English. Reply in composed, intelligent English anime style."
            style_section = ""
        else:
            lang_instruction = "IMPORTANT: The user message is in Vietnamese. Reply in natural, anime-cadence Vietnamese adhering to the Vietnamese style prompt."
            style_section = NENEKA_VIETNAMESE_STYLE_PROMPT

        state_summary = (
            f"### NENEKA REAL-TIME PERSONALITY MATRIX:\n"
            f"- Confidence: {st.confidence}/100 | Curiosity: {st.curiosity}/100\n"
            f"- Affection: {st.affection}/1000 | Trust: {st.trust}/100\n"
            f"- Amusement: {st.amusement}/100 | Irritation: {st.irritation}/100\n"
            f"- Seriousness: {st.seriousness}/100 | Current Emotion: {st.emotional_state}\n"
            f"- Current Interlocutor: {user_name}"
        )

        return f"""{NENEKA_CANON_BASE_PROMPT}

{NENEKA_CANON_FACTS}

{style_section}

{state_summary}

{lang_instruction}"""

