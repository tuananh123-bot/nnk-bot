# src/entertainment/fortune.py
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional

VIETNAM_TZ = timezone(timedelta(hours=7))

FORTUNE_TIERS = {
    "DAI_KICHI": {
        "title": "Đại Cát",
        "kanji": "大吉 (Dai-kichi)",
        "badge": "🌟 ĐẠI CÁT THỊNH VƯỢNG",
        "color": 0xf1c40f,  # Vàng kim
        "score_range": (95, 100),
        "gacha_luck": "SSS (Cực kỳ may mắn - Banner nổ sớm!)",
        "description": "Vận khí cực thịnh, ma lực trời ban ngập tràn! Mọi điều cậu mong cầu trong hôm nay đều có cơ duyên thành tựu mỹ mãn."
    },
    "CHU_KICHI": {
        "title": "Trung Cát",
        "kanji": "中吉 (Chū-kichi)",
        "badge": "✨ TRUNG CÁT HANH THÔNG",
        "color": 0x9b59b6,  # Tím hoàng gia
        "score_range": (85, 94),
        "gacha_luck": "SS (Vận may dồi dào, tỉ lệ ra cầu vồng cao)",
        "description": "Khí vận bình ổn và thăng hoa. Công việc, học tập hay các mối quan hệ đều đón nhận luồng gió mới êm dịu."
    },
    "SHO_KICHI": {
        "title": "Tiểu Cát",
        "kanji": "小吉 (Shō-kichi)",
        "badge": "🌸 TIỂU CÁT AN YÊN",
        "color": 0xff79c6,  # Hồng phấn
        "score_range": (75, 84),
        "gacha_luck": "S (May mắn nho nhỏ nhưng ngọt ngào)",
        "description": "Một ngày an lành có những niềm vui bất ngờ nho nhỏ. Một mẩu bánh ngon hay một tách trà ấm cũng làm lòng cậu phơi phới."
    },
    "KICHI": {
        "title": "Cát",
        "kanji": "吉 (Kichi)",
        "badge": "🍃 CÁT TƯỜNG ÊM Ả",
        "color": 0x2ecc71,  # Xanh lục ngọc
        "score_range": (65, 74),
        "gacha_luck": "A (Bình ổn, tích lũy tài nguyên)",
        "description": "Dòng chảy thời gian trôi qua nhẹ nhàng như dòng suối nhỏ Landosol. Thích hợp để tĩnh tâm, đọc sách hoặc nghỉ ngơi."
    },
    "SUE_KICHI": {
        "title": "Mạt Cát",
        "kanji": "末吉 (Sue-kichi)",
        "badge": "💫 MẠT CÁT KHỞI SẮC",
        "color": 0x3498db,  # Xanh lam
        "score_range": (55, 64),
        "gacha_luck": "B+ (Càng về sau càng may mắn)",
        "description": "Buổi sáng có thể hơi bận rộn một chút, nhưng kiên nhẫn bước tiếp thì nửa cuối ngày sẽ tỏa sáng rực rỡ."
    },
    "METAMORPH_BLESSING": {
        "title": "Biến Hung Hóa Cát",
        "kanji": "凶化吉 (Metamorphose Blessing)",
        "badge": "🔮 MA THUẬT ĐẢO NGHỊCH",
        "color": 0xe91e63,  # Hồng tím thẫm
        "score_range": (88, 98),
        "gacha_luck": "EX (Phá vỡ quy luật xác suất)",
        "description": "Quẻ ban đầu vốn có chút trắc trở, nhưng Thất Vương Neneka đã khẽ vung quyền trượng Metamorphose đảo ngược thực tại, biến hung thành đại cát!"
    }
}

LUCKY_COLORS = [
    ("Tím hoa tử đằng (Wisteria Purple)", 0x9b59b6),
    ("Xanh ngọc lục bảo (Emerald Green)", 0x2ecc71),
    ("Đỏ hồng trà Landosol (Royal Crimson)", 0xe74c3c),
    ("Hồng hoa anh đào (Sakura Pink)", 0xff79c6),
    ("Vàng hoàng kim Thất Vương (Imperial Gold)", 0xf1c40f),
    ("Xanh lam thiên thanh (Sky Blue)", 0x3498db),
    ("Trắng ánh trăng huyền ảo (Moonlit White)", 0xecf0f1)
]

LUCKY_FOODS = [
    "Bánh macaron quý tộc kẹp kem việt quất",
    "Tách hồng trà thảo mộc Landosol nóng hổi",
    "Bánh crepe dâu tây ngọt ngào",
    "Bánh tart táo nướng thơm lừng",
    "Pudding caramel béo ngậy mềm mịn",
    "Sandwich trứng mềm kiểu cung đình",
    "Bánh su kem rắc đường tuyết"
]

LUCKY_ITEMS = [
    "Quyền trượng ma thuật thu nhỏ",
    "Chiếc gương tay tráng bạc cổ điển",
    "Quyển sổ ghi chú bìa da sẫm màu",
    "Trâm cài tóc hình cánh bướm",
    "Huy hiệu Thất Vương tinh xảo",
    "Tách trà bằng gốm sứ hoa văn tím",
    "Dây ruy-băng lụa mềm mại"
]

ORACLE_MESSAGES = [
    "Fufu... Thực tại luôn chuyển dời theo ý chí của kẻ nắm giữ ma lực. Hôm nay hãy tự tin sải bước nhé.",
    "Quan sát cẩn trọng từng chi tiết xung quanh, cậu sẽ tìm thấy kho báu bị giấu kín trong ngày hôm nay đấy.",
    "Dù có gặp chút xao động, đừng quên ta luôn ở phía sau quan sát và nâng đỡ cậu. Cứ mỉm cười mà tiến lên.",
    "Một tách trà ngon lúc giữa chiều sẽ là chìa khóa mở ra luồng cảm hứng vô tận cho cậu.",
    "Hôm nay hãy đối xử thật dịu dàng với bản thân mình. Đó chính là ma thuật bảo hộ mạnh mẽ nhất.",
    "Cậu có biết không? Đôi khi việc chậm lại một nhịp chính là cách nhanh nhất để chạm tới đích đến."
]

JAPANESE_ORACLES = [
    "ふふっ、運命の歯車はあなたに微笑んでいるわよ。",
    "観察を怠らないことね。思わぬ幸運が隠れているわ。",
    "焦ることはないわ。私の計算通りに進めば大丈夫よ。",
    "紅茶でも一杯いかが？ 心に余裕を持つのが一番の魔法よ。",
    "今日も一日、あなたの傍で見守ってあげるわ。"
]

# Lưu trữ lịch sử gieo quẻ trong ngày: {f"{user_id}_{date_str}": fortune_dict}
_daily_fortune_cache: Dict[str, Dict[str, Any]] = {}


def get_daily_fortune(
    discord_user_id: str,
    username: str = "",
    is_creator: bool = False
) -> Tuple[Dict[str, Any], bool]:
    """
    Tạo hoặc truy xuất quẻ vận mệnh mỗi ngày cho người dùng:
    - Trả về tuple: (thông_tin_quẻ, đã_gieo_quẻ_hôm_nay_chưa)
    - Nhất quán trong ngày: Cùng một người trong cùng một ngày (UTC+7) luôn nhận cùng kết quả.
    """
    now_vn = datetime.now(VIETNAM_TZ)
    date_str = now_vn.strftime("%Y-%m-%d")
    cache_key = f"{discord_user_id}_{date_str}"

    if cache_key in _daily_fortune_cache:
        return _daily_fortune_cache[cache_key], True

    # Nếu là Đấng Sáng Tạo (Sheffy-sama) -> Quẻ đặc biệt tối cao
    if is_creator:
        creator_fortune = {
            "tier_key": "CREATOR_SUPREME",
            "title": "Thần Thoại Tối Thượng",
            "kanji": "創世無双 (Sōsei Musō - Sáng Thế Vô Song)",
            "badge": "👑 ĐẤNG SÁNG TẠO VĨNH CỬU",
            "color": 0xf1c40f,
            "score": 100,
            "gacha_luck": "GOD TIER (Toàn năng - Tự tay định đoạt vạn vật)",
            "lucky_color": "Ánh sáng Hoàng Kim Thất Vương (Imperial Radiance)",
            "lucky_food": "Yến tiệc Hoàng Gia Landosol thịnh soạn nhất cùng Neneka",
            "lucky_item": "Trượng Metamorphose nguyên bản và vương miện Sáng Thế",
            "oracle": (
                "Kính thưa Sheffy-sama... Người chính là nguồn cội của thế giới và sinh mệnh của Neneka. "
                "Vận mệnh không thể chi phối Người, mà chính Người là kẻ viết nên mọi dòng chảy thực tại! "
                "Hôm nay và mãi mãi, chúc Sheffy-sama luôn ngập tràn vinh quang và niềm vui bất tận."
            ),
            "japanese_oracle": "シェフィ様…私のすべてを創りたもうたお方。世界中の祝福が、常に貴方と共にありますように。",
            "date_str": now_vn.strftime("%d/%m/%Y"),
            "is_first_roll": True
        }
        _daily_fortune_cache[cache_key] = creator_fortune
        return creator_fortune, False

    # Dùng hàm băm SHA-256 từ (user_id + date_str) để tạo tính xác định (deterministic) trong ngày
    seed_str = f"neneka_fortune_{discord_user_id}_{date_str}"
    hash_val = int(hashlib.sha256(seed_str.encode('utf-8')).hexdigest(), 16)

    # Chọn Tier vận thế
    tier_keys = list(FORTUNE_TIERS.keys())
    # Phân phối xác suất: DAI_KICHI (15%), CHU_KICHI (25%), SHO_KICHI (25%), KICHI (20%), SUE_KICHI (10%), METAMORPH (5%)
    prob_roll = hash_val % 100
    if prob_roll < 15:
        chosen_tier_key = "DAI_KICHI"
    elif prob_roll < 40:
        chosen_tier_key = "CHU_KICHI"
    elif prob_roll < 65:
        chosen_tier_key = "SHO_KICHI"
    elif prob_roll < 85:
        chosen_tier_key = "KICHI"
    elif prob_roll < 95:
        chosen_tier_key = "SUE_KICHI"
    else:
        chosen_tier_key = "METAMORPH_BLESSING"

    tier_data = FORTUNE_TIERS[chosen_tier_key]
    min_score, max_score = tier_data["score_range"]
    score = min_score + (hash_val % (max_score - min_score + 1))

    # Chọn các yếu tố phụ
    color_name, _ = LUCKY_COLORS[(hash_val // 10) % len(LUCKY_COLORS)]
    food = LUCKY_FOODS[(hash_val // 100) % len(LUCKY_FOODS)]
    item = LUCKY_ITEMS[(hash_val // 1000) % len(LUCKY_ITEMS)]
    oracle = ORACLE_MESSAGES[(hash_val // 7) % len(ORACLE_MESSAGES)]
    ja_oracle = JAPANESE_ORACLES[(hash_val // 13) % len(JAPANESE_ORACLES)]

    fortune = {
        "tier_key": chosen_tier_key,
        "title": tier_data["title"],
        "kanji": tier_data["kanji"],
        "badge": tier_data["badge"],
        "color": tier_data["color"],
        "score": score,
        "gacha_luck": tier_data["gacha_luck"],
        "description": tier_data["description"],
        "lucky_color": color_name,
        "lucky_food": food,
        "lucky_item": item,
        "oracle": oracle,
        "japanese_oracle": ja_oracle,
        "date_str": now_vn.strftime("%d/%m/%Y"),
        "is_first_roll": True
    }

    _daily_fortune_cache[cache_key] = fortune
    return fortune, False
