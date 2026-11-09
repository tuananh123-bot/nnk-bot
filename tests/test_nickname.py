# tests/test_nickname.py
import re
import pytest
from src.memory.engine import MemoryEngine

@pytest.mark.asyncio
async def test_set_and_get_nickname():
    mem_engine = MemoryEngine()
    test_user_id = "999888777111"
    test_username = "tester_san"
    new_nick = "Tiểu Kiếm Sĩ"

    # Đặt biệt danh
    success = await mem_engine.set_preferred_name(test_user_id, new_nick, test_username)
    assert success is True

    # Lấy biệt danh
    saved_nick = await mem_engine.get_preferred_name(test_user_id)
    assert saved_nick == new_nick

    # Kiểm tra trong Memory Context
    ctx = await mem_engine.get_memory_context(test_user_id, "chào em")
    assert ctx["preferred_name"] == new_nick
    assert any("Tiểu Kiếm Sĩ" in f for f in ctx["relevant_facts"])

    # Reset biệt danh
    await mem_engine.set_preferred_name(test_user_id, None, test_username)
    reset_nick = await mem_engine.get_preferred_name(test_user_id)
    assert reset_nick is None


def test_natural_nickname_regex():
    pattern = r'(?:từ giờ\s+)?(?:hãy\s+)?(?:đặt biệt danh cho|gọi)\s+(.+?)\s+là\s+([^\n.,!?;]+)'

    m1 = re.search(pattern, "từ giờ hãy gọi <@12345678> là Mèo Con nhé", re.IGNORECASE)
    assert m1 is not None
    assert "<@12345678>" in m1.group(1)
    assert "Mèo Con" in m1.group(2)

    m2 = re.search(pattern, "hãy gọi tôi là Kishi-kun", re.IGNORECASE)
    assert m2 is not None
    assert "tôi" in m2.group(1).lower()
    assert "Kishi-kun" in m2.group(2)

    m3 = re.search(pattern, "Neneka ơi, đặt biệt danh cho mình là Hiệp Sĩ", re.IGNORECASE)
    assert m3 is not None
    assert "mình" in m3.group(1).lower()
    assert "Hiệp Sĩ" in m3.group(2)
