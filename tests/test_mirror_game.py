# tests/test_mirror_game.py
import pytest
from src.bond.engine import BondEngine
from src.entertainment.mirror_game import start_mirror_game, MIRROR_SCENARIOS

def test_mirror_scenarios_structure():
    assert len(MIRROR_SCENARIOS) >= 3
    for s in MIRROR_SCENARIOS:
        assert "title" in s
        assert "story" in s
        assert len(s["options"]) == 3
        # Phải có ít nhất 1 đáp án đúng
        assert any(opt.get("is_correct") for opt in s["options"])


@pytest.mark.asyncio
async def test_start_mirror_game():
    bond_engine = BondEngine()
    test_user_id = "555444333222"

    embed, view, err = start_mirror_game(test_user_id, bond_engine)
    assert err is None
    assert embed is not None
    assert view is not None
    assert len(view.children) == 3

    # Kiểm tra cooldown khi gọi lại ngay lập tức
    embed2, view2, err2 = start_mirror_game(test_user_id, bond_engine)
    assert err2 is not None
    assert "đang hồi phục ma lực" in err2
