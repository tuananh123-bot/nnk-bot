# src/story/engine.py
from typing import Dict, Any, List, Optional

CANON_STORIES: List[Dict[str, Any]] = [
    {
        "id": "main_arc_1_seven_crowns",
        "category": "Main Story",
        "title": "Sự Xuất Hiện Của Thất Vương",
        "canon_status": "CANON",
        "episode_id": "Arc 1 - Chapter 8",
        "summary": "Neneka lần đầu lộ diện thân phận là một trong Thất Vương (Seven Crowns). Sử dụng năng lực phân thân hoàn hảo để quan sát các phe phái tại Landosol và tìm cách ngăn chặn âm mưu thâu tóm thực tại của Mana Senri (Kaiser Insight).",
        "related_characters": "Kaiser Insight, Yuuki, Pecorine, Kokkoro, Karyl",
        "source": "Princess Connect! Re:Dive Main Story Arc 1"
    },
    {
        "id": "char_story_mirror_realm",
        "category": "Character Story",
        "title": "Thế Giới Phía Sau Chiếc Gương Phản Chiếu",
        "canon_status": "CANON",
        "episode_id": "Neneka Story Ep 1-4",
        "summary": "Neneka đưa hiệp sĩ vào không gian ma thuật đặc biệt để kiểm tra khả năng phục hồi trí nhớ và tác động của luồng ma lực Astraea. Cô bộc lộ sự quan sát tinh tế và bảo vệ cậu trước những quái thú ma lực bất ngờ xuất hiện.",
        "related_characters": "Yuuki, Phân thân Neneka",
        "source": "Neneka Character Story In-Game"
    },
    {
        "id": "bond_story_1_tea_and_logic",
        "category": "Bond Story",
        "title": "Tách Trà Chiều Của Bậc Thất Vương",
        "canon_status": "CANON",
        "episode_id": "Bond 1",
        "summary": "Neneka mời hiệp sĩ thưởng thức trà đen Landosol và bánh crepe. Cô chỉ ra rằng những biến số bất định của con người chính là thứ làm cho các phương trình ma thuật trở nên thi vị nhất.",
        "related_characters": "Yuuki",
        "source": "Bond Story Canon"
    },
    {
        "id": "event_story_new_year_shrine",
        "category": "Event Story",
        "title": "Nguyện Ước Đón Xuân Cùng Thất Vương",
        "canon_status": "CANON",
        "episode_id": "New Year Event",
        "summary": "Neneka trong bộ Kimono tao nhã cùng hiệp sĩ viếng đền đầu năm. Cô từ tốn bốc quẻ thẻ và mỉm cười bí ẩn, hứa rằng năm mới này cô sẽ tiếp tục làm quân sư bên cạnh cậu.",
        "related_characters": "Pecorine (New Year), Yuuki",
        "source": "New Year Event Canon"
    },
    {
        "id": "ai_story_late_night_research",
        "category": "Original AI Story",
        "title": "Đêm Trắng Tại Tháp Tri Thức",
        "canon_status": "ORIGINAL_AI",
        "episode_id": "AI-Episode-01",
        "summary": "Mẩu chuyện tương tác nguyên bản giữa Neneka và người dùng Discord: Neneka thức khuya phân tích dữ liệu, cằn nhằn yêu thương nhắc nhở người dùng phải đi ngủ sớm giữ gìn sức khỏe.",
        "related_characters": "Discord User",
        "source": "Neneka Autonomous AI Experience"
    }
]

class StoryEngine:
    """Story Engine tra cứu câu chuyện, kiểm tra Canon Status và phòng chống bịa đặt Lore"""
    def __init__(self):
        self._stories = {s["id"]: s for s in CANON_STORIES}

    def get_story_by_id(self, story_id: str) -> Optional[Dict[str, Any]]:
        return self._stories.get(story_id)

    def search_stories(self, query: str) -> List[Dict[str, Any]]:
        query_l = query.lower()
        results = []
        for s in self._stories.values():
            if (query_l in s["title"].lower() or
                query_l in s["summary"].lower() or
                query_l in s["category"].lower()):
                results.append(s)
        return results

    def list_by_category(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        if not category:
            return list(self._stories.values())
        cat_l = category.lower()
        return [s for s in self._stories.values() if cat_l in s["category"].lower()]

    def verify_canon_status(self, subject: str) -> str:
        """Kiểm tra xem chủ đề có phải thông tin Canon được kiểm chứng hay không"""
        subj_l = subject.lower()
        matches = self.search_stories(subj_l)
        if matches:
            return matches[0]["canon_status"]
        return "UNKNOWN"

story_engine = StoryEngine()

