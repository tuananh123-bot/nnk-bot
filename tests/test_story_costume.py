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

def test_story_canon_status():
    canon_status = story_engine.verify_canon_status("Sự Xuất Hiện Của Thất Vương")
    assert canon_status == "CANON"

    ai_story = story_engine.verify_canon_status("Đêm Trắng Tại Tháp Tri Thức")
    assert ai_story == "ORIGINAL_AI"

    fake_story = story_engine.verify_canon_status("Neneka đi mua sắm ở Paris thế kỷ 18")
    assert fake_story == "UNKNOWN"

