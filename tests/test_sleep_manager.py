# tests/test_sleep_manager.py
import pytest
from src.voice.sleep_manager import sleep_manager, SLEEP_LULLABIES

def test_sleep_lullabies_catalog():
    assert len(SLEEP_LULLABIES) >= 5
    for l in SLEEP_LULLABIES:
        assert "id" in l
        assert "title" in l
        assert "japanese_whisper" in l
        assert "vietnamese_story" in l
        assert "bedtime_tip" in l


def test_get_sleep_lullaby_by_theme():
    # Test tìm theo chủ đề đếm cừu
    l_sheep = sleep_manager.get_sleep_lullaby("đếm cừu ru ngủ")
    assert "cừu" in l_sheep["title"].lower() or l_sheep["id"] == "counting_sheep"

    # Test tìm theo trà
    l_tea = sleep_manager.get_sleep_lullaby("uống tách trà ấm")
    assert "trà" in l_tea["title"].lower() or l_tea["id"] == "chamomile_tea"

    # Test ngẫu nhiên khi không có chủ đề
    l_rand = sleep_manager.get_sleep_lullaby()
    assert l_rand in SLEEP_LULLABIES


def test_create_sleep_embed():
    lullaby = SLEEP_LULLABIES[0]
    embed = sleep_manager.create_sleep_embed(lullaby, "<@12345678>")
    assert embed.title is not None
    assert "Chế Độ Ru Ngủ" in embed.title
    assert len(embed.fields) >= 2

