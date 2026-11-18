# tests/test_bond.py
import uuid
import pytest
from src.database.connection import db_manager
from src.bond.engine import BondEngine, BOND_TIERS
from src.memory.engine import MemoryEngine

@pytest.mark.asyncio
async def test_bond_calculation_and_unlock():
    await db_manager.initialize()
    mem = MemoryEngine()
    bond = BondEngine()

    uid = f"test_bond_knight_{uuid.uuid4().hex[:8]}"
    async for session in db_manager.get_session():
        await mem.get_or_create_user(session, uid, "Knight")

    info_initial = await bond.get_bond_info(uid)
    assert info_initial["level"] == 0

    # Add points to cross into level 1 (min 100)
    lvl, pts, up = await bond.add_bond_points(uid, points=120, event_type="SPECIAL_CONVERSATION")
    assert lvl == 1
    assert up == 1
    assert pts >= 100

    info_lvl1 = await bond.get_bond_info(uid)
    assert info_lvl1["level"] == 1
    assert info_lvl1["title"] == BOND_TIERS[1]["title"]

    await db_manager.close()

def test_build_bond_embed_other_user():
    from unittest.mock import MagicMock
    from src.cogs.bond import build_bond_embed

    mock_user = MagicMock()
    mock_user.display_name = "Pecorine"

    mock_info = {
        "points": 350,
        "level": 2,
        "next_tier_points": 500,
        "title": "Người Bạn Đồng Hành Đáng Tin",
        "description": "Neneka xem bạn là một đồng minh hữu dụng.",
        "salutation": "Pecorine",
        "japanese_salutation": "ペコリーヌ",
        "all_tiers": {
            0: {"unlocked_story": None},
            1: {"unlocked_story": "Câu chuyện đầu tiên"},
            2: {"unlocked_story": "Bí mật Thất Vương"}
        }
    }

    embed = build_bond_embed(mock_user, mock_info)
    assert "Pecorine" in embed.title
    assert "350" in embed.fields[0].value
    assert "Pecorine" in embed.fields[1].value
    assert len(embed.fields) >= 3


