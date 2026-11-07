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

def test_system_prompt_multilingual():
    engine = PersonalityEngine()
    prompt_vi = engine.get_system_prompt("vi", "Kishi")
    assert "You are Neneka from Princess Connect! Re:Dive." in prompt_vi
    assert "PHONG THÁI HỘI THOẠI TIẾNG VIỆT" in prompt_vi

    prompt_ja = engine.get_system_prompt("ja", "Kishi")
    assert "ネネカ（CV: 井口裕香）" in prompt_ja

