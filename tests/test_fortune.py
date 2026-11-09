# tests/test_fortune.py
import pytest
from src.config import settings
from src.entertainment.fortune import get_daily_fortune, FORTUNE_TIERS

def test_daily_fortune_standard_user():
    test_user_id = "1234567890123"
    fortune, is_cached = get_daily_fortune(test_user_id, username="TestUser", is_creator=False)

    assert is_cached is False
    assert "title" in fortune
    assert "kanji" in fortune
    assert "badge" in fortune
    assert "score" in fortune
    assert 50 <= fortune["score"] <= 100
    assert "lucky_color" in fortune
    assert "lucky_food" in fortune
    assert "lucky_item" in fortune
    assert "oracle" in fortune
    assert "japanese_oracle" in fortune

    # Lần gọi thứ 2 trong cùng ngày phải trả về cùng kết quả và is_cached=True
    fortune2, is_cached2 = get_daily_fortune(test_user_id, username="TestUser", is_creator=False)
    assert is_cached2 is True
    assert fortune2["title"] == fortune["title"]
    assert fortune2["score"] == fortune["score"]


def test_daily_fortune_creator():
    creator_id = str(settings.CREATOR_USER_ID)
    fortune, is_cached = get_daily_fortune(creator_id, username="Sheffy", is_creator=True)

    assert fortune["score"] == 100
    assert "Sheffy-sama" in fortune["oracle"] or "Sheffy-sama" in fortune["japanese_oracle"]
    assert "ĐẤNG SÁNG TẠO" in fortune["badge"]

