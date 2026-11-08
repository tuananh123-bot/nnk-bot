# tests/test_creator_respect.py
import pytest
from src.config import settings
from src.bond.engine import BondEngine
from src.personality.engine import PersonalityEngine
from src.personality.prompts import NENEKA_CREATOR_DIRECTIVE
from src.memory.engine import MemoryEngine

CREATOR_ID = "483169533922639902"

def test_creator_config_id():
    assert settings.CREATOR_USER_ID == CREATOR_ID


@pytest.mark.asyncio
async def test_creator_bond_info():
    bond_engine = BondEngine()
    info = await bond_engine.get_bond_info(CREATOR_ID)
    assert info.get("is_creator") is True
    assert info["level"] == 99
    assert info["points"] == 9999
    assert "Ngài" in info["salutation"] or "Người sáng tạo" in info["salutation"]
    assert "創造主様" in info["japanese_salutation"]


def test_creator_personality_system_prompt():
    engine = PersonalityEngine()
    prompt = engine.get_system_prompt("vi", "Master", is_creator=True)
    assert NENEKA_CREATOR_DIRECTIVE in prompt
    assert CREATOR_ID in prompt
    assert "[👑 ĐẤNG SÁNG TẠO - CREATOR / MASTER]" in prompt
    assert engine.state.trust == 100
    assert engine.state.affection == 1000
    assert engine.state.irritation == 0


def test_creator_interaction_immunity():
    engine = PersonalityEngine()
    # Thử trêu chọc tuổi tác / chiều cao
    engine.update_from_interaction("Bà già lùn tịt nấm lùn", is_creator=True)
    # Neneka không tức giận với Đấng Sáng Tạo
    assert engine.state.irritation == 0
    assert engine.state.affection == 1000
    assert engine.state.emotional_state == "affectionate_warmth"


@pytest.mark.asyncio
async def test_creator_memory_context():
    mem_engine = MemoryEngine()
    ctx = await mem_engine.get_memory_context(CREATOR_ID, "Xin chào Neneka")
    assert any("CREATOR_ORIGIN" in fact for fact in ctx["relevant_facts"])
    assert CREATOR_ID in "\n".join(ctx["relevant_facts"])
