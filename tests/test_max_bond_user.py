# tests/test_max_bond_user.py
import pytest
from src.config import settings
from src.bond.engine import BondEngine
from src.memory.engine import MemoryEngine
from src.personality.engine import PersonalityEngine

TARGET_USER_ID = "864077473661845504"

def test_max_bond_user_in_settings():
    assert TARGET_USER_ID in settings.max_bond_user_id_list


@pytest.mark.asyncio
async def test_max_bond_engine_info():
    bond_engine = BondEngine()
    info = await bond_engine.get_bond_info(TARGET_USER_ID)

    assert info["level"] == 6
    assert info["points"] >= 9999
    assert info["is_max_bond"] is True
    assert info["salutation"] == "Người đặc biệt nhất của ta"
    assert "私の騎士クン" in info["japanese_salutation"]
    assert "TỐI THƯỢNG" in info["title"]


@pytest.mark.asyncio
async def test_max_bond_memory_context():
    mem_engine = MemoryEngine()
    ctx = await mem_engine.get_memory_context(TARGET_USER_ID, "Hôm nay em thế nào?")

    assert any("MAX_BOND_RELATIONSHIP" in f for f in ctx["relevant_facts"])
    assert any("Người đặc biệt nhất" in f for f in ctx["relevant_facts"])


def test_max_bond_personality_engine():
    p_engine = PersonalityEngine()

    # Thử trêu chọc tuổi tác/chiều cao
    p_engine.update_from_interaction("Bà già lùn tịt", is_max_bond=True)
    assert p_engine.state.affection == 1000
    assert p_engine.state.trust == 100
    assert p_engine.state.irritation == 0

    # System prompt chứa chỉ dẫn quan hệ tối thượng
    prompt = p_engine.get_system_prompt(is_max_bond=True)
    assert "ĐẶC QUYỀN MỐI QUAN HỆ SÂU SẮC NHẤT" in prompt
    assert "1000/1000" in prompt
    assert "私の騎士クン" in prompt

