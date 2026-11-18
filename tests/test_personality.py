# tests/test_personality.py
import pytest
from src.personality.engine import PersonalityEngine, PersonalityState

def test_character_personality_initial():
    engine = PersonalityEngine()
    assert engine.state.confidence == 85
    assert engine.state.curiosity == 75
    assert engine.state.emotional_state == "calm_analytical"

def test_character_personality_height_tease():
    engine = PersonalityEngine()
    engine.update_from_interaction("Chào bà cô lùn tịt")
    assert engine.state.emotional_state == "annoyed_chilly"
    assert engine.state.irritation > 10

def test_character_personality_compliment():
    engine = PersonalityEngine()
    engine.update_from_interaction("Hôm nay Neneka dễ thương và xinh đẹp quá")
    assert engine.state.emotional_state == "slight_tsundere"
    assert engine.state.affection > 150

def test_character_personality_sensual_soft():
    engine = PersonalityEngine()
    engine.update_from_interaction("hôn neneka")
    assert engine.state.arousal > 10
    assert engine.state.lust > 10

def test_system_prompt_multilingual():
    engine = PersonalityEngine()
    prompt_vi = engine.get_system_prompt("vi", "Kishi")
    assert "You are Neneka from Princess Connect! Re:Dive." in prompt_vi
    assert "PHONG THÁI HỘI THOẠI TIẾNG VIỆT" in prompt_vi

    prompt_ja = engine.get_system_prompt("ja", "Kishi")
    assert "ネネカ（CV: 井口裕香）" in prompt_ja

    prompt_en = engine.get_system_prompt("en", "Kishi")
    assert "NENEKA'S ENGLISH DIALOGUE STYLE & PERSONA" in prompt_en
    assert "dignified, intellectual, and composed mature lady" in prompt_en

def test_detect_language():
    engine = PersonalityEngine()
    # English
    assert engine.detect_language("Hello Neneka, how are you today?") == "en"
    assert engine.detect_language("Can you tell me about the Seven Crowns?") == "en"
    assert engine.detect_language("What time is it right now?") == "en"

    # Japanese
    assert engine.detect_language("こんにちは、ネネカさん！") == "ja"
    assert engine.detect_language("おはようございます") == "ja"

    # Vietnamese (accented and unaccented)
    assert engine.detect_language("Chào buổi sáng quý cô Neneka!") == "vi"
    assert engine.detect_language("hom nay the nao em") == "vi"
    assert engine.detect_language("em an com chua") == "vi"
