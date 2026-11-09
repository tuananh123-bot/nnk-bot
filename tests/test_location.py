# tests/test_location.py
import re
import pytest
from src.memory.engine import MemoryEngine
from src.utils.vietnam_context import detect_city_from_query, CITIES_VN

@pytest.mark.asyncio
async def test_set_and_get_user_location():
    mem_engine = MemoryEngine()
    test_user_id = "777666555222"
    test_username = "traveler_san"
    test_city = "Đà Nẵng"

    # Đặt vị trí
    success = await mem_engine.set_user_location(test_user_id, test_city, test_username)
    assert success is True

    # Lấy vị trí
    saved_loc = await mem_engine.get_user_location(test_user_id)
    assert saved_loc == test_city

    # Đổi sang vị trí khác (TP. Hồ Chí Minh)
    await mem_engine.set_user_location(test_user_id, "TP. Hồ Chí Minh", test_username)
    updated_loc = await mem_engine.get_user_location(test_user_id)
    assert updated_loc == "TP. Hồ Chí Minh"

    # Reset vị trí
    await mem_engine.set_user_location(test_user_id, None, test_username)
    cleared_loc = await mem_engine.get_user_location(test_user_id)
    assert cleared_loc is None


def test_natural_location_regex():
    pattern = r'(?:tôi|mình|ta|anh|em|nhà tôi|nhà mình|hiện tại)\s+(?:đang\s+)?(?:ở|sống tại|sinh sống tại|ở tại)\s+([^\n.,!?;]+)'

    m1 = re.search(pattern, "mình đang ở Sài Gòn nè neneka", re.IGNORECASE)
    assert m1 is not None
    city_raw1 = m1.group(1).strip()
    assert detect_city_from_query(city_raw1) == "hcm"

    m2 = re.search(pattern, "tôi sống tại Đà Nẵng", re.IGNORECASE)
    assert m2 is not None
    city_raw2 = m2.group(1).strip()
    assert detect_city_from_query(city_raw2) == "danang"

    m3 = re.search(pattern, "nhà mình ở Cần Thơ nha", re.IGNORECASE)
    assert m3 is not None
    city_raw3 = m3.group(1).strip()
    assert detect_city_from_query(city_raw3) == "cantho"

    m4 = re.search(pattern, "hiện tại ở Bình Dương", re.IGNORECASE)
    assert m4 is not None
    city_raw4 = m4.group(1).strip()
    assert detect_city_from_query(city_raw4) == "binhduong"

    # Câu nói không liên quan đến địa danh trong CITIES_VN
    m5 = re.search(pattern, "mình đang ở nhà thôi", re.IGNORECASE)
    assert m5 is not None
    city_raw5 = m5.group(1).strip()
    assert detect_city_from_query(city_raw5) is None

