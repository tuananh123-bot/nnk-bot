# tests/test_lust_arousal.py
"""
Unit tests cho tính năng thanh mức độ dâm dục (Lust) và thanh mức độ hứng cảm (Arousal) của Neneka.
"""
import pytest
from src.personality.engine import PersonalityState, PersonalityEngine


class TestPersonalityStateLustArousal:
    """Kiểm tra khởi tạo và các hàm tiện ích của Lust và Arousal trong PersonalityState."""

    def test_default_values(self):
        state = PersonalityState()
        assert hasattr(state, "lust")
        assert hasattr(state, "arousal")
        assert state.lust == 10
        assert state.arousal == 10

    def test_clamp_upper_bound(self):
        state = PersonalityState(lust=150, arousal=200)
        state.clamp()
        assert state.lust == 100
        assert state.arousal == 100

    def test_clamp_lower_bound(self):
        state = PersonalityState(lust=-30, arousal=-50)
        state.clamp()
        assert state.lust == 0
        assert state.arousal == 0

    def test_render_bar_visual(self):
        bar_0 = PersonalityState.render_bar(0, 100, length=10)
        assert bar_0 == "[▱▱▱▱▱▱▱▱▱▱] 0/100"

        bar_50 = PersonalityState.render_bar(50, 100, length=10)
        assert bar_50 == "[▰▰▰▰▰▱▱▱▱▱] 50/100"

        bar_100 = PersonalityState.render_bar(100, 100, length=10)
        assert bar_100 == "[▰▰▰▰▰▰▰▰▰▰] 100/100"

    def test_lust_bar_property(self):
        state = PersonalityState(lust=70)
        bar = state.lust_bar
        assert "70/100" in bar
        assert "▰" in bar

    def test_arousal_bar_property(self):
        state = PersonalityState(arousal=40)
        bar = state.arousal_bar
        assert "40/100" in bar
        assert "▰" in bar

    def test_lust_descriptions(self):
        state = PersonalityState(lust=10)
        assert "Thanh khiết" in state.lust_description

        state.lust = 30
        assert "Gợi cảm" in state.lust_description

        state.lust = 50
        assert "Khao khát" in state.lust_description

        state.lust = 75
        assert "Mê đắm" in state.lust_description

        state.lust = 95
        assert "Dâm dục tột đỉnh" in state.lust_description

    def test_arousal_descriptions(self):
        state = PersonalityState(arousal=10)
        assert "Bình thản" in state.arousal_description

        state.arousal = 30
        assert "Rạo rực" in state.arousal_description

        state.arousal = 50
        assert "Hưng phấn" in state.arousal_description

        state.arousal = 75
        assert "nhạy cảm" in state.arousal_description

        state.arousal = 95
        assert "Cao trào cực khoái" in state.arousal_description


class TestPersonalityEngineLustArousalInteractions:
    """Kiểm tra phản hồi động của Lust và Arousal qua các tương tác người dùng."""

    def test_soft_sensual_increase(self):
        engine = PersonalityEngine()
        initial_lust = engine.state.lust
        initial_arousal = engine.state.arousal

        engine.update_from_interaction("Neneka hôm nay thật gợi cảm và quyến rũ")
        assert engine.state.lust > initial_lust
        assert engine.state.arousal > initial_arousal

    def test_medium_sensual_increase(self):
        engine = PersonalityEngine()
        initial_lust = engine.state.lust
        initial_arousal = engine.state.arousal

        engine.update_from_interaction("Muốn ôm và hôn môi nàng, khẽ cởi chiếc áo choàng Thất Vương")
        assert engine.state.lust >= initial_lust + 12
        assert engine.state.arousal >= initial_arousal + 15

    def test_heavy_sensual_increase(self):
        engine = PersonalityEngine()
        initial_lust = engine.state.lust
        initial_arousal = engine.state.arousal

        engine.update_from_interaction("Cùng nàng ân ái trong khoái lạc, thở dốc và tận hưởng dục vọng")
        assert engine.state.lust >= initial_lust + 25
        assert engine.state.arousal >= initial_arousal + 25
        # Trạng thái cảm xúc chuyển biến
        assert engine.state.emotional_state in ["ecstatic_passion", "flustered_heat"]

    def test_unaccented_vietnamese_support(self):
        engine = PersonalityEngine()
        initial_lust = engine.state.lust
        initial_arousal = engine.state.arousal

        # Gõ tiếng Việt không dấu: "em quyen ru va goi cam qua"
        engine.update_from_interaction("em quyen ru va goi cam qua")
        assert engine.state.lust > initial_lust
        assert engine.state.arousal > initial_arousal

    def test_creator_sensual_boost(self):
        engine_user = PersonalityEngine()
        engine_creator = PersonalityEngine()

        msg = "Muốn vuốt ve bờ vai gợi cảm của nàng"
        engine_user.update_from_interaction(msg, is_creator=False)
        engine_creator.update_from_interaction(msg, is_creator=True)

        # Creator có hệ số nhạy cảm 1.5x
        assert engine_creator.state.lust >= engine_user.state.lust
        assert engine_creator.state.arousal >= engine_user.state.arousal
        assert engine_creator.state.affection == 1000
        assert engine_creator.state.trust == 100

    def test_irritation_decreases_arousal(self):
        engine = PersonalityEngine(initial_state=PersonalityState(arousal=40))
        engine.update_from_interaction("Chào bà già lùn tịt")
        # Khi bị chê bà già lùn, hứng cảm giảm
        assert engine.state.arousal <= 30
        assert engine.state.irritation > 0


class TestSystemPromptLustArousal:
    """Kiểm tra ma trận dâm dục và hứng cảm xuất hiện trong System Prompt."""

    def test_prompt_contains_lust_and_arousal(self):
        engine = PersonalityEngine(initial_state=PersonalityState(lust=45, arousal=55))
        prompt = engine.get_system_prompt()
        assert "Lust: 45/100" in prompt
        assert "Arousal: 55/100" in prompt
        assert "Khao khát & Rung động" in prompt
        assert "Hưng phấn dồn dập" in prompt

    def test_prompt_nsfw_mode_has_sensual_guide(self):
        engine = PersonalityEngine(initial_state=PersonalityState(lust=50, arousal=50))
        prompt = engine.get_system_prompt(is_nsfw=True)
        assert "CHỈ SỐ DỤC VỌNG & HỨNG CẢM HIỆN TẠI" in prompt
        assert "QUY TẮC NHẬP VAI BIỂU HIỆN CẢM XÚC THỂ XÁC" in prompt
        assert "Mức Độ Dâm Dục (Lust)" in prompt
        assert "Mức Độ Hứng Cảm (Arousal)" in prompt
