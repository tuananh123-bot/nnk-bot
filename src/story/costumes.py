# src/story/costumes.py
from typing import Dict, Any, List, Optional

COSTUME_VARIANTS: Dict[str, Dict[str, Any]] = {
    "original": {
        "id": "variant_neneka_original",
        "name": "Neneka (Nguyên Bản / Thất Vương)",
        "japanese_name": "ネネカ (通常)",
        "title": "Biến Mạo Đại Phi (Metamorph Monarch)",
        "visual_description": "Trang phục váy dạ hội quý tộc tím huyền bí, vương miện đính ngọc Astraea, đôi bốt cao tao nhã cùng cây quyền trượng Metamorphose phát sáng luồng ma lực thực tại.",
        "personality_flair": "Điềm đạm, sắc sảo, kiêu kỳ của một nhà nghiên cứu Thất Vương đứng trên đỉnh cao tri thức.",
        "icon": "👑"
    },
    "new_year": {
        "id": "variant_neneka_new_year",
        "name": "Neneka (Tết Năm Mới / New Year)",
        "japanese_name": "ネネカ (ニューイヤー)",
        "title": "Khởi Đầu Tinh Khôi (New Year Metamorph)",
        "visual_description": "Bộ Kimono truyền thống lộng lẫy họa tiết hoa anh đào Landosol tông màu tím nhạt và trắng tuyết, mái tóc búi cài trâm ngọc quý phái, tay cầm quạt giấy trang nhã.",
        "personality_flair": "Nhiều nét dịu dàng, ấm áp của người chị lớn trong dịp đầu xuân, thích mời đối phương thưởng trà và ăn bánh mochi đầu năm.",
        "icon": "🌸"
    },
    "alpha": {
        "id": "variant_neneka_alpha",
        "name": "Neneka (Thế Giới Thực / Reality Alpha)",
        "japanese_name": "現士念香 (リアル・アルファ)",
        "title": "Nhà Khoa Học Utsushimi",
        "visual_description": "Áo blouse trắng phòng thí nghiệm kết hợp cùng trang phục công sở hiện đại thanh lịch, đeo kính gọng mảnh, phong thái tri thức của một chuyên gia nghiên cứu công nghệ thực tại ảo 24 tuổi.",
        "personality_flair": "Nghiêm túc, logic thuần túy, đôi lúc lộ vẻ mệt mỏi vì làm việc thâu đêm bên màn hình dữ liệu, rất trân trọng khi được đối phương pha cà phê cho.",
        "icon": "🔬"
    },
    "summer": {
        "id": "variant_neneka_summer",
        "name": "Neneka (Đồ Bơi Mùa Hè / Summer Swimsuit)",
        "japanese_name": "ネネカ (サマー)",
        "title": "Huyễn Ảnh Bờ Biển (Azure Summer Monarch)",
        "visual_description": "Bộ bikini hai mảnh màu tím oải hương quyến rũ kết hợp áo khoác voan mỏng xuyên thấu phất phơ trong gió biển, chiếc mũ cói rộng vành quý phái che nắng, làn da trắng ngọc ngà dưới ánh nắng mùa hè nhiệt đới, quyền trượng Metamorphose cách điệu ánh xà cừ lấp lánh bọt sóng.",
        "personality_flair": "Có phần ngượng ngùng khi để lộ nhiều da thịt trước mặt người đối thoại, nhưng vẫn giữ nét kiêu kỳ đặc trưng của Thất Vương; thích cùng đi dạo trên bờ cát vắng, ngắm hoàng hôn biển hoặc để đối phương thoa kem chống nắng lên lưng cho mình.",
        "icon": "👙"
    }
}

class CostumeManager:
    """Quản lý các biến thể trang phục và phong thái tương ứng của Neneka"""
    def __init__(self):
        self._user_costumes: Dict[str, str] = {}  # user_id -> variant_key

    def resolve_variant_key(self, key_or_alias: Any) -> Optional[str]:
        """Chuẩn hóa alias/tên trang phục về key chính xác trong COSTUME_VARIANTS"""
        if not key_or_alias or not isinstance(key_or_alias, str):
            return None
        cleaned = key_or_alias.lower().strip()
        alias_map = {
            "bikini": "summer",
            "swimsuit": "summer",
            "swimwear": "summer",
            "do_boi": "summer",
            "doboi": "summer",
            "do boi": "summer",
            "boi": "summer",
            "summer": "summer",
            "newyear": "new_year",
            "new_year": "new_year",
            "tet": "new_year",
            "kimono": "new_year",
            "real": "alpha",
            "reality": "alpha",
            "alpha": "alpha",
            "original": "original",
            "default": "original",
            "variant_neneka_original": "original",
            "variant_neneka_new_year": "new_year",
            "variant_neneka_alpha": "alpha",
            "variant_neneka_summer": "summer",
        }
        resolved = alias_map.get(cleaned, cleaned)
        if resolved in COSTUME_VARIANTS:
            return resolved
        for v_key, v_info in COSTUME_VARIANTS.items():
            if cleaned == v_info.get("id", "").lower() or cleaned in v_info.get("name", "").lower():
                return v_key
        return None

    def get_current_costume(self, discord_user_id: str) -> Dict[str, Any]:
        variant_key = self._user_costumes.get(str(discord_user_id), "original")
        return COSTUME_VARIANTS.get(variant_key, COSTUME_VARIANTS["original"])

    def get_costume_info(self, variant_or_key: Any) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chi tiết của trang phục từ dict, key variant, hoặc alias"""
        if isinstance(variant_or_key, dict):
            return variant_or_key
        resolved = self.resolve_variant_key(variant_or_key)
        if resolved:
            return COSTUME_VARIANTS.get(resolved)
        return None

    def set_user_costume(self, discord_user_id: str, variant_key: str) -> Optional[Dict[str, Any]]:
        resolved = self.resolve_variant_key(variant_key)
        if not resolved:
            return None
        self._user_costumes[str(discord_user_id)] = resolved
        return COSTUME_VARIANTS[resolved]

    def list_all_costumes(self) -> List[Dict[str, Any]]:
        return list(COSTUME_VARIANTS.values())

costume_mgr = CostumeManager()

