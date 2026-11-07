# tests/test_bond.py
import pytest
from src.database.connection import db_manager
from src.bond.engine import BondEngine, BOND_TIERS
from src.memory.engine import MemoryEngine

@pytest.mark.asyncio
async def test_bond_calculation_and_unlock():
    await db_manager.initialize()
    mem = MemoryEngine()
    bond = BondEngine()

    uid = "test_bond_knight"
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
