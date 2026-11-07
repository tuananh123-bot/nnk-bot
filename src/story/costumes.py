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
    }
}

class CostumeManager:
    """Quản lý các biến thể trang phục và phong thái tương ứng của Neneka"""
    def __init__(self):
        self._user_costumes: Dict[str, str] = {}  # user_id -> variant_key

    def get_current_costume(self, discord_user_id: str) -> Dict[str, Any]:
        variant_key = self._user_costumes.get(str(discord_user_id), "original")
        return COSTUME_VARIANTS.get(variant_key, COSTUME_VARIANTS["original"])

    def set_user_costume(self, discord_user_id: str, variant_key: str) -> Optional[Dict[str, Any]]:
        variant_key = variant_key.lower().strip()
        if variant_key not in COSTUME_VARIANTS:
            return None
        self._user_costumes[str(discord_user_id)] = variant_key
        return COSTUME_VARIANTS[variant_key]

    def list_all_costumes(self) -> List[Dict[str, Any]]:
        return list(COSTUME_VARIANTS.values())

costume_mgr = CostumeManager()
