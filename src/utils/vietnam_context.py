# src/utils/vietnam_context.py
import re
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List
import aiohttp

logger = logging.getLogger("Neneka.VietnamContext")

# Múi giờ Việt Nam: UTC+7
VIETNAM_TZ = timezone(timedelta(hours=7))

DAYS_OF_WEEK_VN = {
    0: "Thứ Hai",
    1: "Thứ Ba",
    2: "Thứ Tư",
    3: "Thứ Năm",
    4: "Thứ Sáu",
    5: "Thứ Bảy",
    6: "Chủ Nhật"
}

# Bảng mã thời tiết WMO (World Meteorological Organization) dịch sang tiếng Việt tự nhiên
WMO_WEATHER_CODES = {
    0: "Trời quang đãng, trong xanh",
    1: "Trời chủ yếu quang mây, nắng dịu",
    2: "Có mây rải rác",
    3: "Nhiều mây, trời râm mát",
    45: "Có sương mù",
    48: "Sương mù đọng sương",
    51: "Mưa phùn nhẹ hạt",
    53: "Mưa phùn vừa",
    55: "Mưa phùn dày hạt",
    56: "Mưa phùn buốt lạnh nhẹ",
    57: "Mưa phùn buốt lạnh dày đặc",
    61: "Mưa rào nhẹ rải rác",
    63: "Mưa vừa",
    65: "Mưa to nặng hạt",
    66: "Mưa lạnh buốt",
    67: "Mưa đá nhỏ lạnh buốt",
    71: "Tuyết rơi nhẹ",
    73: "Tuyết rơi vừa",
    75: "Tuyết rơi dày",
    77: "Mưa tuyết hạt nhỏ",
    80: "Mưa rào thoáng qua",
    81: "Mưa rào vừa",
    82: "Mưa rào dữ dội xối xả",
    85: "Mưa tuyết rải rác",
    86: "Mưa tuyết dày hạt",
    95: "Giông bão có sấm chớp",
    96: "Giông bão kèm mưa đá nhẹ",
    99: "Giông bão dữ dội kèm sấm sét và mưa đá lớn"
}

# Tọa độ các thành phố / khu vực trọng điểm tại Việt Nam
CITIES_VN: Dict[str, Tuple[float, float, str]] = {
    "hanoi": (21.0285, 105.8542, "Hà Nội"),
    "hcm": (10.8231, 106.6297, "TP. Hồ Chí Minh"),
    "danang": (16.0544, 108.2022, "Đà Nẵng"),
    "haiphong": (20.8449, 106.6881, "Hải Phòng"),
    "cantho": (10.0452, 105.7469, "Cần Thơ"),
    "dalat": (11.9404, 108.4583, "Đà Lạt"),
    "nhatrang": (12.2388, 109.1967, "Nha Trang"),
    "hue": (16.4637, 107.5909, "Huế"),
    "vungtau": (10.3460, 107.0843, "Vũng Tàu"),
    "quangninh": (20.9505, 107.0733, "Quảng Ninh (Hạ Long)"),
    "sapa": (22.3364, 103.8438, "Sa Pa (Lào Cai)"),
    "quynhon": (13.7820, 109.2197, "Quy Nhơn"),
    "buonmathuot": (12.6667, 108.0383, "Buôn Ma Thuột")
}

CITY_ALIASES: Dict[str, str] = {
    "hà nội": "hanoi", "ha noi": "hanoi", "hanoi": "hanoi", "hn": "hanoi", "thủ đô": "hanoi",
    "hồ chí minh": "hcm", "ho chi minh": "hcm", "sài gòn": "hcm", "sai gon": "hcm", "tphcm": "hcm", "hcm": "hcm", "sg": "hcm",
    "đà nẵng": "danang", "da nang": "danang", "danang": "danang", "dn": "danang",
    "hải phòng": "haiphong", "hai phong": "haiphong", "haiphong": "haiphong", "hp": "haiphong",
    "cần thơ": "cantho", "can tho": "cantho", "cantho": "cantho",
    "đà lạt": "dalat", "da lat": "dalat", "dalat": "dalat",
    "nha trang": "nhatrang", "nhatrang": "nhatrang",
    "huế": "hue", "hue": "hue",
    "vũng tàu": "vungtau", "vung tau": "vungtau", "vungtau": "vungtau",
    "hạ long": "quangninh", "ha long": "quangninh", "quảng ninh": "quangninh", "quang ninh": "quangninh",
    "sa pa": "sapa", "sapa": "sapa", "lào cai": "sapa", "lao cai": "sapa",
    "quy nhơn": "quynhon", "quy nhon": "quynhon", "bình định": "quynhon", "binh dinh": "quynhon",
    "buôn ma thuột": "buonmathuot", "buon ma thuot": "buonmathuot", "đắk lắk": "buonmathuot", "dak lak": "buonmathuot"
}

# Cache thời tiết trong RAM (TTL 15 phút = 900 giây)
_weather_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 900


def get_vietnam_time_info() -> Dict[str, Any]:
    """
    Trả về thông tin thời gian thực tại Việt Nam (UTC+7):
    - Giờ, phút, giây, ngày, tháng, năm
    - Thứ trong tuần (tiếng Việt)
    - Buổi trong ngày (sáng sớm, buổi sáng, trưa, chiều, hoàng hôn, tối, đêm khuya)
    - Gợi ý chào hỏi phù hợp với tính cách quý cô Neneka
    """
    now = datetime.now(VIETNAM_TZ)
    hour = now.hour
    minute = now.minute
    second = now.second
    day_of_week = DAYS_OF_WEEK_VN.get(now.weekday(), "Thứ Hai")
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M")

    # Xác định buổi trong ngày và gợi ý phản hồi
    if 0 <= hour < 5:
        period = "đêm khuya / rạng sáng"
        greeting = "Đêm đã về khuya rồi đấy"
        care_tip = "Cậu nên sớm đi ngủ và nghỉ ngơi đi nhé, thức khuya không tốt cho sức khỏe đâu."
    elif 5 <= hour < 8:
        period = "sáng sớm"
        greeting = "Chào buổi sáng sớm tinh mơ"
        care_tip = "Một ngày mới lại bắt đầu ở Landosol cũng như thế giới của cậu. Nhớ ăn sáng đầy đủ nhé."
    elif 8 <= hour < 11:
        period = "buổi sáng"
        greeting = "Chào buổi sáng"
        care_tip = "Buổi sáng tràn đầy năng lượng chứ? Ta đang thưởng thức tách hồng trà đây."
    elif 11 <= hour < 13 or (hour == 13 and minute <= 30):
        period = "buổi trưa"
        greeting = "Chào buổi trưa"
        care_tip = "Đã tới giờ nghỉ trưa rồi. Cậu đã dùng bữa chưa đấy?"
    elif 13 < hour < 17 or (hour == 13 and minute > 30) or (hour == 17 and minute <= 30):
        period = "buổi chiều"
        greeting = "Chào buổi chiều"
        care_tip = "Một buổi chiều êm đềm. Cậu đang bận rộn với công việc hay đang nghỉ ngơi thế?"
    elif 17 < hour < 19 or (hour == 17 and minute > 30):
        period = "chiều tối / hoàng hôn"
        greeting = "Chào buổi chiều tối"
        care_tip = "Mặt trời sắp lặn rồi. Đã đến lúc gác lại công việc và chuẩn bị ăn tối rồi đấy."
    elif 19 <= hour < 22 or (hour == 22 and minute <= 30):
        period = "buổi tối"
        greeting = "Chào buổi tối"
        care_tip = "Buổi tối thư thái nhé. Giờ là lúc thư giãn sau một ngày dài."
    else:  # 22:30 -> 23:59
        period = "đêm muộn"
        greeting = "Đã khuya rồi"
        care_tip = "Sắp bước sang ngày mới rồi kìa. Chuẩn bị chăn gối ngủ ngoan đi nhé, cậu bé của ta."

    return {
        "now": now,
        "hour": hour,
        "minute": minute,
        "second": second,
        "time_str": time_str,
        "date_str": date_str,
        "day_of_week": day_of_week,
        "period": period,
        "greeting": greeting,
        "care_tip": care_tip,
        "formatted_summary": f"{time_str} ({day_of_week}, ngày {date_str}) - {period.capitalize()}"
    }


def detect_city_from_query(query: str) -> Optional[str]:
    """Phát hiện thành phố người dùng đề cập đến trong câu hỏi"""
    if not query:
        return None
    lower = query.lower()
    for alias, city_key in CITY_ALIASES.items():
        # Match nguyên từ hoặc cụm từ
        if alias in lower:
            return city_key
    return None


async def fetch_weather_for_coords(lat: float, lon: float, city_name: str) -> Optional[Dict[str, Any]]:
    """Truy vấn Open-Meteo API với caching 15 phút"""
    cache_key = f"{lat:.4f}_{lon:.4f}"
    now_ts = time.time()

    if cache_key in _weather_cache:
        cached_ts, cached_data = _weather_cache[cache_key]
        if now_ts - cached_ts < CACHE_TTL_SECONDS:
            return cached_data

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,weather_code,wind_speed_10m"
        f"&timezone=Asia%2FHo_Chi_Minh"
    )

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.0)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    curr = data.get("current", {})
                    code = curr.get("weather_code", 0)
                    temp = curr.get("temperature_2m", 0.0)
                    app_temp = curr.get("apparent_temperature", temp)
                    humidity = curr.get("relative_humidity_2m", 0)
                    rain = curr.get("rain", 0.0)
                    wind = curr.get("wind_speed_10m", 0.0)
                    is_day = curr.get("is_day", 1) == 1

                    weather_desc = WMO_WEATHER_CODES.get(code, "Trời bình thường")

                    result = {
                        "city_name": city_name,
                        "temperature": round(temp, 1),
                        "apparent_temperature": round(app_temp, 1),
                        "humidity": humidity,
                        "rain_mm": rain,
                        "wind_speed_kmh": round(wind, 1),
                        "weather_code": code,
                        "weather_desc": weather_desc,
                        "is_day": is_day,
                        "status": "success"
                    }
                    _weather_cache[cache_key] = (now_ts, result)
                    return result
                else:
                    logger.warning(f"Open-Meteo API trả về status {resp.status}")
    except Exception as e:
        logger.error(f"Lỗi khi gọi Open-Meteo API ({city_name}): {e}")

    # Nếu cache cũ còn dù hết hạn thì dùng tạm khi lỗi mạng
    if cache_key in _weather_cache:
        return _weather_cache[cache_key][1]

    return None


async def get_vietnam_weather_info(city_query: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lấy thông tin thời tiết:
    - Nếu có thành phố chỉ định -> Trả về thời tiết thành phố đó.
    - Nếu không chỉ định -> Trả về thời tiết 2 đầu đất nước (Hà Nội & TP. Hồ Chí Minh).
    """
    detected_key = detect_city_from_query(city_query) if city_query else None

    if detected_key and detected_key in CITIES_VN:
        lat, lon, name = CITIES_VN[detected_key]
        w = await fetch_weather_for_coords(lat, lon, name)
        return [w] if w else []

    # Mặc định lấy Hà Nội và TP. Hồ Chí Minh
    results = []
    hn_w = await fetch_weather_for_coords(CITIES_VN["hanoi"][0], CITIES_VN["hanoi"][1], CITIES_VN["hanoi"][2])
    if hn_w:
        results.append(hn_w)
    hcm_w = await fetch_weather_for_coords(CITIES_VN["hcm"][0], CITIES_VN["hcm"][1], CITIES_VN["hcm"][2])
    if hcm_w:
        results.append(hcm_w)
    return results


async def get_vietnam_context_for_prompt(user_message: str = "") -> str:
    """
    Xây dựng đoạn ngữ cảnh thời gian và thời tiết thực tế tại Việt Nam để chèn vào System Prompt của Neneka.
    """
    time_info = get_vietnam_time_info()
    weather_list = await get_vietnam_weather_info(user_message)

    weather_lines = []
    for w in weather_list:
        rain_note = f", có mưa ({w['rain_mm']}mm)" if w.get("rain_mm", 0) > 0 else ""
        weather_lines.append(
            f"- {w['city_name']}: {w['weather_desc']}, Nhiệt độ {w['temperature']}°C "
            f"(cảm giác như {w['apparent_temperature']}°C), Độ ẩm {w['humidity']}%, Gió {w['wind_speed_kmh']} km/h{rain_note}."
        )

    weather_text = "\n".join(weather_lines) if weather_lines else "- Đang cập nhật dữ liệu thời tiết Việt Nam."

    prompt_snippet = (
        f"### THÔNG TIN THỜI GIAN & THỜI TIẾT THỰC TẾ (VIỆT NAM - UTC+7):\n"
        f"- Thời gian hiện tại: {time_info['formatted_summary']}\n"
        f"- Khoảng thời gian: {time_info['period']} (Gợi ý ngữ điệu: {time_info['greeting']})\n"
        f"- Lưu ý quan tâm: {time_info['care_tip']}\n"
        f"- Dữ liệu thời tiết thực tế hôm nay tại Việt Nam:\n{weather_text}\n\n"
        f"### QUY TẮC NHẬN THỨC CỦA NENEKA:\n"
        f"1. Ngươi có nhận thức thời gian thực và thời tiết thực tế chính xác tuyệt đối tại Việt Nam theo dữ liệu trên.\n"
        f"2. Khi đối phương hỏi giờ giấc, thứ mấy, ngày nào, hoặc thời tiết hôm nay, hãy trả lời chính xác dựa theo dữ liệu trên mà không bịa đặt.\n"
        f"3. Lời chào tự nhiên phải tương ứng với buổi hiện tại (ví dụ: đang là chiều thì chào buổi chiều 'Konnichiwa' / 'Chào buổi chiều', đang khuya thì nhắc ngủ sớm).\n"
        f"4. Thể hiện phong thái quý cô Thất Vương tao nhã, ân cần và hơi trêu đùa; có thể so sánh thời tiết với Landosol hoặc nhắc nhở hiệp sĩ mặc áo ấm, mang theo ô nếu có mưa."
    )
    return prompt_snippet

