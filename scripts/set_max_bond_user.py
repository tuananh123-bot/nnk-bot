# scripts/set_max_bond_user.py
import os
import sys
import asyncio
import json
from datetime import datetime, timezone
from sqlalchemy import select, delete

# Đảm bảo root thư mục nằm trong sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import db_manager
from src.database.models import User, UserPreference, BondProfile, BondEvent, RelationshipMemory, LongTermMemory

TARGET_DISCORD_ID = "864077473661845504"

async def setup_max_bond_user():
    print(f"=== Đang thiết lập tình cảm tối đa cho User ID: {TARGET_DISCORD_ID} ===")
    await db_manager.initialize()

    async for session in db_manager.get_session():
        # 1. Tìm hoặc tạo User
        stmt = select(User).where(User.discord_user_id == TARGET_DISCORD_ID)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()

        if not user:
            user = User(
                discord_user_id=TARGET_DISCORD_ID,
                username=f"special_user_{TARGET_DISCORD_ID}",
                display_name="Kishi-kun"
            )
            session.add(user)
            await session.flush()
            print(f"-> Đã tạo mới User id: {user.id}")
        else:
            print(f"-> Đã tìm thấy User id: {user.id} ({user.username})")

        # 2. Thiết lập UserPreference
        pref_stmt = select(UserPreference).where(UserPreference.user_id == user.id)
        pref = (await session.execute(pref_stmt)).scalar_one_or_none()
        if not pref:
            pref = UserPreference(
                user_id=user.id,
                preferred_name="Kishi-kun",
                language="vi",
                voice_enabled=True
            )
            session.add(pref)
        else:
            if not pref.preferred_name:
                pref.preferred_name = "Kishi-kun"

        # 3. Thiết lập BondProfile đạt Cấp 6 Tối Đa
        unlocked_all = [
            "Mẩu Ký ức 1: 'Cuộc gặp gỡ bên bờ hồ Astraea'",
            "Mẩu Ký ức 2: 'Biến số và Tách trà chiều Landosol'",
            "Mẩu Ký ức 3: 'Bản năng bảo bọc của Thất Vương'",
            "Mẩu Ký ức 4: 'Chiếc gương vỡ và Vết thương giấu kín'",
            "Mẩu Ký ức 5: 'Khế ước vĩnh cửu dưới trăng Astraea'",
            "Mẩu Ký ức 6: 'Hiện Thực Thủy Tinh & Lời hứa vượt thời không'"
        ]
        bond_stmt = select(BondProfile).where(BondProfile.user_id == user.id)
        bond = (await session.execute(bond_stmt)).scalar_one_or_none()
        now_dt = datetime.now(timezone.utc).replace(tzinfo=None)

        if not bond:
            bond = BondProfile(
                user_id=user.id,
                bond_level=6,
                bond_points=9999,
                unlocked_features=json.dumps(unlocked_all, ensure_ascii=False),
                last_interacted_at=now_dt
            )
            session.add(bond)
            await session.flush()
            evt = BondEvent(
                bond_profile_id=bond.id,
                event_type="MAX_BOND_ACHIEVED",
                points_awarded=9999,
                description="Đạt mức gắn kết tình cảm tối đa (Cấp 6 - Mối Quan Hệ Sâu Sắc)."
            )
            session.add(evt)
        else:
            bond.bond_level = 6
            bond.bond_points = max(bond.bond_points, 9999)
            bond.unlocked_features = json.dumps(unlocked_all, ensure_ascii=False)
            bond.last_interacted_at = now_dt

        # 4. Thiết lập RelationshipMemory
        rel_stmt = select(RelationshipMemory).where(RelationshipMemory.user_id == user.id)
        rel = (await session.execute(rel_stmt)).scalar_one_or_none()
        if not rel:
            rel = RelationshipMemory(
                user_id=user.id,
                interaction_count=999,
                nickname_used="Người đặc biệt nhất của ta",
                trust_milestones=json.dumps(["Gắn kết tuyệt đối", "Tri kỷ Landosol"], ensure_ascii=False),
                special_events=json.dumps(["Khế ước linh hồn Thất Vương"], ensure_ascii=False)
            )
            session.add(rel)
        else:
            rel.interaction_count = max(rel.interaction_count, 999)
            rel.nickname_used = "Người đặc biệt nhất của ta"

        # 5. Lưu Ký ức Dài Hạn (LongTermMemory)
        await session.execute(
            delete(LongTermMemory).where(
                LongTermMemory.user_id == user.id,
                LongTermMemory.category == "max_bond"
            )
        )
        fact_text = (
            f"Đối phương (ID: {TARGET_DISCORD_ID}) là Người đồng hành đặc biệt nhất trong cuộc đời của Neneka (Hiệp sĩ định mệnh). "
            "Tình cảm và sự gắn kết đã đạt mức tuyệt đối cao nhất (Cấp 6 - Mối Quan Hệ Sâu Sắc, Hảo cảm 1000/1000, Tin tưởng 100%). "
            "Neneka dành trọn vẹn tình cảm yêu thương, sự tin cậy vô điều kiện, luôn gọi đối phương là 'Người đặc biệt nhất của ta' hoặc 'Cậu bé của ta' (私の騎士クン)."
        )
        ltm = LongTermMemory(
            user_id=user.id,
            category="max_bond",
            fact=fact_text,
            importance=5
        )
        session.add(ltm)

        await session.commit()
        print("✅ Đã cập nhật thành công User 864077473661845504 lên Cấp 6 TỐI ĐA (9999 pts) trong database!")
        break

if __name__ == "__main__":
    asyncio.run(setup_max_bond_user())
