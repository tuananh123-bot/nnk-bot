# tests/test_story_costume.py
import pytest
from src.story.costumes import costume_mgr, COSTUME_VARIANTS
from src.story.engine import story_engine

def test_costume_switching():
    user = "user_costume_tester"
    default_c = costume_mgr.get_current_costume(user)
    assert default_c["id"] == "variant_neneka_original"

    # Switch to new_year
    switched = costume_mgr.set_user_costume(user, "new_year")
    assert switched["id"] == "variant_neneka_new_year"

    current = costume_mgr.get_current_costume(user)
    assert current["id"] == "variant_neneka_new_year"

    # Switch to summer (swimwear)
    switched_summer = costume_mgr.set_user_costume(user, "summer")
    assert switched_summer["id"] == "variant_neneka_summer"
    assert "Đồ Bơi" in switched_summer["name"]

    # Test alias (bikini / do_boi)
    switched_bikini = costume_mgr.set_user_costume(user, "bikini")
    assert switched_bikini["id"] == "variant_neneka_summer"

def test_costume_info_and_prompt_integration():
    from src.personality.engine import PersonalityEngine

    # Test get_costume_info with various inputs
    info_summer = costume_mgr.get_costume_info("summer")
    assert info_summer is not None
    assert info_summer["id"] == "variant_neneka_summer"

    info_bikini = costume_mgr.get_costume_info("bikini")
    assert info_bikini is not None
    assert info_bikini["id"] == "variant_neneka_summer"

    info_dict = costume_mgr.get_costume_info(info_summer)
    assert info_dict == info_summer

    info_invalid = costume_mgr.get_costume_info("non_existent_costume_123")
    assert info_invalid is None

    # Test system prompt integration with dict (what chat.py passes)
    engine = PersonalityEngine()
    
    # Original costume dict -> should not inject special costume section
    original_dict = costume_mgr.get_costume_info("original")
    prompt_orig = engine.get_system_prompt(costume=original_dict)
    assert "### TRANG PHỤC HIỆN TẠI:" not in prompt_orig

    # Summer costume dict -> must inject special costume section
    prompt_summer = engine.get_system_prompt(costume=info_summer)
    assert "### TRANG PHỤC HIỆN TẠI:" in prompt_summer
    assert "Đồ Bơi Mùa Hè" in prompt_summer
    assert "bikini" in prompt_summer.lower()

    # Summer costume string alias -> must also inject correctly
    prompt_bikini = engine.get_system_prompt(costume="bikini")
    assert "### TRANG PHỤC HIỆN TẠI:" in prompt_bikini
    assert "Đồ Bơi Mùa Hè" in prompt_bikini

def test_story_canon_status():
    canon_status = story_engine.verify_canon_status("Sự Xuất Hiện Của Thất Vương")
    assert canon_status == "CANON"

    ai_story = story_engine.verify_canon_status("Đêm Trắng Tại Tháp Tri Thức")
    assert ai_story == "ORIGINAL_AI"

    fake_story = story_engine.verify_canon_status("Neneka đi mua sắm ở Paris thế kỷ 18")
    assert fake_story == "UNKNOWN"

