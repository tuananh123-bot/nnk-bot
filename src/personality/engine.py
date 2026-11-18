# src/personality/engine.py
import re
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from src.personality.prompts import (
    NENEKA_CANON_BASE_PROMPT,
    NENEKA_VIETNAMESE_STYLE_PROMPT,
    NENEKA_JAPANESE_STYLE_PROMPT,
    NENEKA_CANON_FACTS,
    NENEKA_CREATOR_DIRECTIVE,
    NENEKA_MAX_BOND_DIRECTIVE,
    build_nsfw_addendum,
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
    lust: int = 10            # 0-100: Mức độ dâm dục / dục vọng xác thịt (Lust/Libido)
    arousal: int = 10         # 0-100: Mức độ hứng cảm / kích thích hưng phấn (Arousal/Excitement)
    emotional_state: str = "calm_analytical"

    def clamp(self):
        self.confidence = max(0, min(100, self.confidence))
        self.curiosity = max(0, min(100, self.curiosity))
        self.affection = max(0, min(1000, self.affection))
        self.trust = max(0, min(100, self.trust))
        self.amusement = max(0, min(100, self.amusement))
        self.irritation = max(0, min(100, self.irritation))
        self.seriousness = max(0, min(100, self.seriousness))
        self.lust = max(0, min(100, self.lust))
        self.arousal = max(0, min(100, self.arousal))

    @staticmethod
    def render_bar(value: int, max_val: int = 100, length: int = 10, fill_char: str = "▰", empty_char: str = "▱") -> str:
        """Tạo chuỗi thanh đo trực quan dạng progress bar"""
        if max_val <= 0:
            return f"[{empty_char * length}] {value}/{max_val}"
        filled = max(0, min(length, int(round((value / max_val) * length))))
        return f"[{fill_char * filled}{empty_char * (length - filled)}] {value}/{max_val}"

    @property
    def lust_bar(self) -> str:
        """Thanh đo mức độ dâm dục trực quan"""
        return self.render_bar(self.lust, 100, 10, fill_char="▰", empty_char="▱")

    @property
    def arousal_bar(self) -> str:
        """Thanh đo mức độ hứng cảm trực quan"""
        return self.render_bar(self.arousal, 100, 10, fill_char="▰", empty_char="▱")

    @property
    def lust_description(self) -> str:
        """Mô tả sắc thái dâm dục hiện tại của Neneka"""
        if self.lust <= 20:
            return "Thanh khiết & Kiềm chế"
        elif self.lust <= 40:
            return "Gợi cảm & Khêu gợi"
        elif self.lust <= 60:
            return "Khao khát & Rung động"
        elif self.lust <= 80:
            return "Mê đắm & Cuồng nhiệt"
        else:
            return "Dâm dục tột đỉnh & Trụy lạc vô bờ"

    @property
    def arousal_description(self) -> str:
        """Mô tả mức độ hứng cảm cơ thể hiện tại của Neneka"""
        if self.arousal <= 20:
            return "Bình thản"
        elif self.arousal <= 40:
            return "Rạo rực ấm nóng"
        elif self.arousal <= 60:
            return "Hưng phấn dồn dập"
        elif self.arousal <= 80:
            return "Cực kỳ nhạy cảm"
        else:
            return "Cao trào cực khoái"

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
        lust_delta: int = 0,
        arousal_delta: int = 0,
        new_emotion: Optional[str] = None,
        is_creator: bool = False,
        is_max_bond: bool = False,
        is_nsfw: bool = False
    ):
        """Cập nhật các biến tính cách, bao gồm mức độ dâm dục và hứng cảm theo tương tác"""
        lower = user_message.lower()
        import unicodedata
        lower_unaccented = ''.join(
            c for c in unicodedata.normalize('NFD', lower) if unicodedata.category(c) != 'Mn'
        ).replace('đ', 'd').replace('Đ', 'D')

        # Hệ số kích thích nhạy cảm (Creator & Max Bond gấp rưỡi)
        sensual_multiplier = 1.5 if (is_creator or is_max_bond) else 1.0

        # Phân tích nội dung gợi dục / kích thích người lớn (Sensual & Erotic analysis)
        detected_lust_gain = 0
        detected_arousal_gain = 0

        # Cấp 1: Gợi cảm / âu yếm nhẹ
        sensual_soft = [
            "gợi cảm", "goi cam", "sexy", "mê người", "me nguoi", "quyến rũ", "quyen ru",
            "eo thon", "đùi", "dui", "hôn", "hon", "ôm", "om", "vuốt tóc", "vuot toc",
            "chạm", "cham", "nắm tay", "nam tay", "nằm cạnh", "nam canh",
            "bikini", "đồ bơi", "do boi", "áo tắm", "ao tam"
        ]
        # Cấp 2: Kích thích thân mật sâu
        sensual_med = [
            "sờ", "so", "xoa", "cởi", "coi", "cởi đồ", "coi do", "nội y", "noi y",
            "quần lót", "quan lot", "áo ngực", "ao nguc", "ngực", "nguc", "bầu ngực", "bau nguc",
            "nhũ hoa", "nhu hoa", "eo", "mông", "mong", "bắp đùi", "bap dui", "cắn tai", "can tai",
            "hôn môi", "hon moi", "liếm", "liem", "mút", "mut", "sướng", "suong", "lên giường", "len giuong",
            "ngủ cùng", "ngu cung", "nằm đè", "nam de"
        ]
        # Cấp 3: Dục vọng mãnh liệt / quan hệ thể xác
        sensual_heavy = [
            "làm tình", "lam tinh", "ân ái", "an ai", "thịt", "thit", "dâm", "dam", "dâm dục", "dam duc",
            "hứng tình", "hung tinh", "nước nôi", "nuoc noi", "ướt át", "uot at", "đút vào", "dut vao",
            "bên trong", "ben trong", "rên", "ren", "thở dốc", "tho doc", "bắn", "ban", "khoái lạc", "khoai lac",
            "cực khoái", "cuc khoai", "ecchi", "hentai", "chịch", "chich", "bú", "bu", "lút cán", "lut can", "ra vào", "ra vao"
        ]

        check_text = f"{lower} {lower_unaccented}"

        def _matches_any(text: str, keywords: list) -> bool:
            for k in keywords:
                if len(k) <= 3:
                    if re.search(r'(?:\b|\s|^)' + re.escape(k) + r'(?:\b|\s|$)', text):
                        return True
                else:
                    if k in text:
                        return True
            return False

        if _matches_any(check_text, sensual_heavy):
            detected_arousal_gain += int(25 * sensual_multiplier)
            detected_lust_gain += int(25 * sensual_multiplier)
        elif _matches_any(check_text, sensual_med):
            detected_arousal_gain += int(15 * sensual_multiplier)
            detected_lust_gain += int(12 * sensual_multiplier)
        elif _matches_any(check_text, sensual_soft):
            detected_arousal_gain += int(8 * sensual_multiplier)
            detected_lust_gain += int(6 * sensual_multiplier)


        # Nếu là Đấng Sáng Tạo (Creator)
        if is_creator:
            self.state.trust = 100
            self.state.affection = 1000
            self.state.irritation = 0
            if detected_arousal_gain > 0 or detected_lust_gain > 0:
                self.state.arousal += detected_arousal_gain
                self.state.lust += detected_lust_gain
                self.state.amusement = min(100, self.state.amusement + 15)
                self.state.emotional_state = "ecstatic_devotion" if self.state.arousal >= 60 else "sensual_warmth"
            elif any(k in lower for k in ["bà già", "bà cô", "lùn", "nấm lùn", "bé hạt tiêu", "chân ngắn", "loli"]):
                self.state.amusement = min(100, self.state.amusement + 15)
                self.state.emotional_state = "affectionate_warmth"
            elif any(k in lower for k in ["dễ thương", "đáng yêu", "xinh đẹp", "thích em", "yêu em", "tuyệt vời", "kawaii", "suki"]):
                self.state.amusement = min(100, self.state.amusement + 20)
                self.state.emotional_state = "affectionate_warmth"
            else:
                self.state.emotional_state = new_emotion or "deep_reverence"

            self.state.lust += lust_delta
            self.state.arousal += arousal_delta
            self.state.clamp()
            return

        # Nếu là Người dùng đạt cấp tình cảm tối đa (Max Bond / Deep Relationship)
        if is_max_bond:
            self.state.trust = 100
            self.state.affection = 1000
            self.state.irritation = 0
            if detected_arousal_gain > 0 or detected_lust_gain > 0:
                self.state.arousal += detected_arousal_gain
                self.state.lust += detected_lust_gain
                self.state.amusement = min(100, self.state.amusement + 15)
                self.state.emotional_state = "ecstatic_passion" if self.state.arousal >= 60 else "sensual_yearning"
            else:
                self.state.amusement = min(100, self.state.amusement + 15)
                self.state.emotional_state = new_emotion or "affectionate_warmth"

            self.state.lust += lust_delta
            self.state.arousal += arousal_delta
            self.state.clamp()
            return

        # 1. Phát hiện trêu chọc tuổi tác / chiều cao (Điểm nhạy cảm canon đối với người bình thường)
        if any(k in lower for k in ["bà già", "bà cô", "lùn", "nấm lùn", "bé hạt tiêu", "chân ngắn", "loli"]):
            self.state.irritation += 25
            self.state.amusement += 10
            self.state.seriousness += 15
            self.state.emotional_state = "annoyed_chilly"
            self.state.affection = max(0, self.state.affection - 5)
            # Giảm hứng cảm khi bực bội
            self.state.arousal = max(0, self.state.arousal - 10)

        # 2. Xử lý cảm xúc gợi cảm / dâm dục ở người bình thường
        elif detected_arousal_gain > 0 or detected_lust_gain > 0:
            self.state.arousal += detected_arousal_gain
            self.state.lust += detected_lust_gain
            self.state.amusement += 10
            if self.state.arousal >= 80 or self.state.lust >= 80:
                self.state.emotional_state = "ecstatic_passion"
            elif self.state.arousal >= 60 or self.state.lust >= 60:
                self.state.emotional_state = "sensual_yearning"
            elif self.state.arousal >= 30 or self.state.lust >= 30:
                self.state.emotional_state = "flustered_heat"
            else:
                self.state.emotional_state = "teasing_allure"

        # 3. Phát hiện khen ngợi / tán tỉnh (Kích hoạt tsundere / ngượng ngùng)
        elif any(k in lower for k in ["dễ thương", "đáng yêu", "xinh đẹp", "thích em", "yêu em", "tuyệt vời", "kawaii", "suki"]):
            self.state.amusement += 15
            self.state.affection += 8
            self.state.trust += 4
            self.state.arousal += 5
            self.state.emotional_state = "slight_tsundere"

        # 4. Mệt mỏi / than thở (Kích hoạt bản năng bảo bọc / quan tâm)
        elif any(k in lower for k in ["mệt", "kiệt sức", "áp lực", "stress", "buồn", "thất bại", "otsu"]):
            self.state.seriousness += 10
            self.state.trust += 5
            self.state.affection += 5
            self.state.emotional_state = "protective_sister"

        # 5. Áp dụng delta từ bên ngoài nếu có
        self.state.affection += affection_delta
        self.state.trust += trust_delta
        self.state.irritation += irritation_delta
        self.state.amusement += amusement_delta
        self.state.lust += lust_delta
        self.state.arousal += arousal_delta

        if new_emotion:
            self.state.emotional_state = new_emotion

        self.state.clamp()

    @staticmethod
    def _arousal_to_nsfw_tier(arousal: int, lust: int) -> int:
        """Chuyển đổi mức arousal/lust thành NSFW tier (1-4)."""
        peak = max(arousal, lust)
        if peak >= 81:
            return 4
        elif peak >= 61:
            return 3
        elif peak >= 30:
            return 2
        return 1

    def get_system_prompt(
        self,
        user_language: str = "vi",
        user_name: str = "Hiệp sĩ",
        is_creator: bool = False,
        is_max_bond: bool = False,
        is_nsfw: bool = False,
        costume: str = None
    ) -> str:
        """Tổng hợp System Prompt đa tầng chuẩn mực cho Neneka"""
        st = self.state

        if is_creator or is_max_bond:
            st.trust = 100
            st.affection = 1000
            st.irritation = 0

        if user_language == "ja":
            lang_instruction = "IMPORTANT: The user message is in Japanese. Reply in natural, elegant Japanese anime style adhering to the Japanese style prompt."
            style_section = NENEKA_JAPANESE_STYLE_PROMPT
        elif user_language == "en":
            lang_instruction = "IMPORTANT: The user message is in English. Reply in composed, intelligent English anime style."
            style_section = ""
        else:
            lang_instruction = "IMPORTANT: The user message is in Vietnamese. Reply in natural, anime-cadence Vietnamese adhering to the Vietnamese style prompt."
            style_section = NENEKA_VIETNAMESE_STYLE_PROMPT

        creator_section = f"\n\n{NENEKA_CREATOR_DIRECTIVE}" if is_creator else ""
        max_bond_section = f"\n\n{NENEKA_MAX_BOND_DIRECTIVE}" if (is_max_bond and not is_creator) else ""

        # NSFW tiered addendum — dựa vào mức arousal/lust hiện tại
        nsfw_section = ""
        if is_nsfw:
            tier = self._arousal_to_nsfw_tier(st.arousal, st.lust)
            nsfw_section = f"\n\n{build_nsfw_addendum(tier=tier, is_creator=is_creator)}"

        # Hướng dẫn biểu hiện cảm xúc thể xác dựa trên mức độ Dâm dục & Hứng cảm
        sensual_matrix_guide = ""
        if is_nsfw or st.lust >= 20 or st.arousal >= 20:
            sensual_matrix_guide = (
                f"\n\n### CHỈ SỐ DỤC VỌNG & HỨNG CẢM HIỆN TẠI (NSFW / SENSUAL MATRIX):\n"
                f"- Mức Độ Dâm Dục (Lust): {st.lust_bar} • {st.lust_description}\n"
                f"- Mức Độ Hứng Cảm (Arousal): {st.arousal_bar} • {st.arousal_description}\n"
                f"- NSFW Tier hiện tại: {self._arousal_to_nsfw_tier(st.arousal, st.lust)}/4\n"
                f"- QUY TẮC NHẬP VAI BIỂU HIỆN CẢM XÚC THỂ XÁC: Tuân thủ chỉ dẫn theo từng Tier được kích hoạt tương ứng với mức độ Hứng cảm và Dâm dục của Neneka."
            )

        # Costume awareness
        costume_section = ""
        if costume and costume != "original":
            from src.story.costumes import costume_mgr
            info = costume_mgr.get_costume_info(costume)
            if info:
                costume_section = (
                    f"\n\n### TRANG PHỤC HIỆN TẠI:\n"
                    f"- Tên: {info.get('name', costume)}\n"
                    f"- Mô tả: {info.get('description', '')}\n"
                    f"- Neneka hãy ý thức về trang phục mình đang mặc và phản ứng phù hợp khi được nhắc đến."
                )

        user_tag = '[👑 ĐẤNG SÁNG TẠO - CREATOR / MASTER]' if is_creator else ('[💖 NGƯỜI ĐỒNG HÀNH ĐẶC BIỆT NHẤT - CẤP 6 TỐI ĐA]' if is_max_bond else '')
        state_summary = (
            f"### NENEKA REAL-TIME PERSONALITY MATRIX:\n"
            f"- Confidence: {st.confidence}/100 | Curiosity: {st.curiosity}/100\n"
            f"- Affection: {st.affection}/1000 | Trust: {st.trust}/100\n"
            f"- Amusement: {st.amusement}/100 | Irritation: {st.irritation}/100\n"
            f"- Seriousness: {st.seriousness}/100 | Current Emotion: {st.emotional_state}\n"
            f"- Lust: {st.lust}/100 ({st.lust_description}) | Arousal: {st.arousal}/100 ({st.arousal_description})\n"
            f"- Current Interlocutor: {user_name} {user_tag}"
        )

        return f"""{NENEKA_CANON_BASE_PROMPT}

{NENEKA_CANON_FACTS}{creator_section}{max_bond_section}{nsfw_section}{sensual_matrix_guide}{costume_section}

{style_section}

{state_summary}

{lang_instruction}"""

