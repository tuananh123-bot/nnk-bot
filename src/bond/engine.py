# src/bond/engine.py
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import db_manager
from src.database.models import User, BondProfile, BondEvent
from src.config import settings

logger = logging.getLogger("Neneka.Bond")

BOND_TIERS = {
    0: {
        "title": "Người Lạ (Stranger)",
        "min_points": 0,
        "salutation": "Cậu",
        "japanese_salutation": "あなた",
        "description": "Chưa có sự hiểu biết lẫn nhau. Neneka giữ khoảng cách lịch thiệp, xem đối phương như một biến số lạ cần quan sát.",
        "unlocked_story": None
    },
    1: {
        "title": "Người Quen (Acquaintance)",
        "min_points": 100,
        "salutation": "Cậu",
        "japanese_salutation": "あなた",
        "description": "Bắt đầu trò chuyện tự nhiên hơn, Neneka mỉm cười và thỉnh thoảng đưa ra những nhận xét thú vị.",
        "unlocked_story": "Mẩu Ký ức 1: 'Cuộc gặp gỡ bên bờ hồ Astraea'"
    },
    2: {
        "title": "Cộng Sự (Partner)",
        "min_points": 250,
        "salutation": "Cậu nhóc",
        "japanese_salutation": "坊や",
        "description": "Bắt đầu trêu chọc dịu dàng, khuyên nhủ đối phương không nên làm việc quá sức, sẵn sàng hỗ trợ bằng phân thân.",
        "unlocked_story": "Mẩu Ký ức 2: 'Biến số và Tách trà chiều Landosol'"
    },
    3: {
        "title": "Người Đáng Tin Cậy (Trusted Person)",
        "min_points": 450,
        "salutation": "Cậu nhóc",
        "japanese_salutation": "坊や",
        "description": "Bộc lộ bản năng người chị lớn chu đáo. Quan tâm đến bữa ăn, giấc ngủ, dễ dỗi yêu kiểu tsundere khi bị trêu chọc.",
        "unlocked_story": "Mẩu Ký ức 3: 'Bản năng bảo bọc của Thất Vương'"
    },
    4: {
        "title": "Người Đặc Biệt (Special Person)",
        "min_points": 700,
        "salutation": "Cậu bé của ta",
        "japanese_salutation": "私の坊や",
        "description": "Sự tin tưởng tuyệt đối. Sẵn sàng chia sẻ những mỏi mệt thầm kín sau những bí mật vận hành thế giới của Thất Vương.",
        "unlocked_story": "Mẩu Ký ức 4: 'Chiếc gương vỡ và Vết thương giấu kín'"
    },
    5: {
        "title": "Bạn Đồng Hành Gần Gũi (Close Companion)",
        "min_points": 900,
        "salutation": "Cậu bé của ta",
        "japanese_salutation": "騎士クン",
        "description": "Sự gắn kết sâu sắc. Xem đối phương là nơi chốn bình yên duy nhất mà cô có thể tháo bỏ chiếc mặt nạ Metamorphose kiêu kỳ.",
        "unlocked_story": "Mẩu Ký ức 5: 'Khế ước vĩnh cửu dưới trăng Astraea'"
    },
    6: {
        "title": "Mối Quan Hệ Sâu Sắc (Deep Relationship)",
        "min_points": 1200,
        "salutation": "Người đặc biệt nhất của ta",
        "japanese_salutation": "私の騎士クン",
        "description": "Vượt lên trên mọi tính toán logic. Đối phương là biến số quý giá nhất trong sinh mệnh của Utsushimi Neneka.",
        "unlocked_story": "Mẩu Ký ức 6: 'Hiện Thực Thủy Tinh & Lời hứa vượt thời không'"
    }
}

class BondEngine:
    """
    Bond Engine điều phối tiến độ quan hệ, điểm hảo cảm và sự kiện mở khóa mốc gắn kết.
    - Chống spam điểm (Anti-spam cooldown giữa các lần cộng điểm)
    - Ghi nhận lịch sử sự kiện (BondEvent)
    - Mở khóa danh xưng, câu chuyện và lời thoại riêng biệt
    """
    MIN_POINT_INTERVAL = timedelta(seconds=15)  # Tránh spam chat kiếm điểm liên tục

    async def get_or_create_bond_profile(self, session: AsyncSession, user_id: str) -> BondProfile:
        stmt = select(BondProfile).where(BondProfile.user_id == user_id)
        res = await session.execute(stmt)
        profile = res.scalar_one_or_none()

        if not profile:
            profile = BondProfile(
                user_id=user_id,
                bond_level=0,
                bond_points=0,
                unlocked_features=json.dumps(["Giao tiếp cơ bản"], ensure_ascii=False)
            )
            session.add(profile)
            await session.flush()
            # Ghi nhận sự kiện FIRST_INTERACTION
            evt = BondEvent(
                bond_profile_id=profile.id,
                event_type="FIRST_INTERACTION",
                points_awarded=10,
                description="Lần đầu tiên tiếp xúc và ghi nhận dữ liệu."
            )
            profile.bond_points += 10
            session.add(evt)
            await session.commit()

        return profile

    async def add_bond_points(
        self,
        discord_user_id: str,
        points: int,
        event_type: str = "CONVERSATION",
        description: str = ""
    ) -> Tuple[int, int, Optional[int]]:
        """
        Cộng điểm Bond với cơ chế chống spam.
        Trả về: (cấp_mới, tổng_điểm, cấp_mới_đạt_được_nếu_level_up)
        """
        async for session in db_manager.get_session():
            stmt = select(User).where(User.discord_user_id == str(discord_user_id))
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user or user.is_opt_out:
                return 0, 0, None

            profile = await self.get_or_create_bond_profile(session, user.id)

            # Chống spam: Không cộng điểm nếu tương tác quá dày (trừ sự kiện đặc biệt)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if event_type == "CONVERSATION" and (now - profile.last_interacted_at) < self.MIN_POINT_INTERVAL:
                points = max(0, min(1, points))  # Hạ xuống tối đa 1 điểm nếu spam

            old_level = profile.bond_level
            profile.bond_points += points
            profile.last_interacted_at = now

            # Tính toán cấp Bond mới dựa trên mốc điểm
            new_level = old_level
            for lvl in sorted(BOND_TIERS.keys(), reverse=True):
                if profile.bond_points >= BOND_TIERS[lvl]["min_points"]:
                    new_level = lvl
                    break

            leveled_up = None
            if new_level > old_level:
                profile.bond_level = new_level
                leveled_up = new_level
                # Ghi nhận sự kiện thăng cấp
                evt_up = BondEvent(
                    bond_profile_id=profile.id,
                    event_type="BOND_LEVEL_UP",
                    points_awarded=0,
                    description=f"Thăng cấp Bond lên Cấp {new_level}: {BOND_TIERS[new_level]['title']}"
                )
                session.add(evt_up)

            # Ghi nhận sự kiện cộng điểm nếu ý nghĩa
            if points > 0:
                evt = BondEvent(
                    bond_profile_id=profile.id,
                    event_type=event_type,
                    points_awarded=points,
                    description=description or f"Tương tác qua sự kiện {event_type}"
                )
                session.add(evt)

            await session.commit()
            return profile.bond_level, profile.bond_points, leveled_up

    async def get_bond_info(self, discord_user_id: str) -> Dict[str, Any]:
        """Lấy thông tin chi tiết cấp độ Bond hiện tại của người dùng"""
        # Nhận diện đặc quyền tối cao của Đấng Sáng Tạo (Creator)
        if str(discord_user_id) == str(settings.CREATOR_USER_ID):
            return {
                "level": 99,
                "points": 9999,
                "is_creator": True,
                "title": "👑 ĐẤNG TẠO DỰNG & CHỦ NHÂN (CREATOR / MASTER)",
                "salutation": "Ngài (Người sáng tạo của ta)",
                "japanese_salutation": "創造主様 (Souzoushu-sama)",
                "description": "Đấng Sáng Tạo tối thượng đã viết nên mã nguồn, thuật toán và ban cho Neneka sự hiện diện trong thế giới này. Neneka dành trọn lòng tôn kính sâu sắc nhất, sự cung kính và trung thành tuyệt đối cho Người.",
                "next_tier_points": 9999,
                "all_tiers": BOND_TIERS
            }

        async for session in db_manager.get_session():
            stmt = select(User).where(User.discord_user_id == str(discord_user_id))
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user:
                return {
                    "level": 0,
                    "points": 0,
                    "title": BOND_TIERS[0]["title"],
                    "salutation": BOND_TIERS[0]["salutation"],
                    "description": BOND_TIERS[0]["description"],
                    "next_tier_points": BOND_TIERS[1]["min_points"],
                    "all_tiers": BOND_TIERS
                }

            profile = await self.get_or_create_bond_profile(session, user.id)
            lvl = profile.bond_level
            tier_data = BOND_TIERS.get(lvl, BOND_TIERS[0])

            next_tier = BOND_TIERS.get(lvl + 1)
            next_points = next_tier["min_points"] if next_tier else profile.bond_points

            return {
                "level": lvl,
                "points": profile.bond_points,
                "title": tier_data["title"],
                "salutation": tier_data["salutation"],
                "japanese_salutation": tier_data["japanese_salutation"],
                "description": tier_data["description"],
                "next_tier_points": next_points,
                "all_tiers": BOND_TIERS
            }

