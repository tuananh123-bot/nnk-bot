# src/memory/engine.py
import re
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database.connection import db_manager
from src.database.models import (
    User, UserPreference, Conversation, Message,
    ShortTermMemory, LongTermMemory, RelationshipMemory
)

logger = logging.getLogger("Neneka.Memory")

class MemoryEngine:
    """
    Hệ thống Quản lý Ký ức Đa tầng (Long-term, Short-term, Relationship)
    - Cô lập ký ức tuyệt đối theo từng Discord User ID
    - Truy xuất chọn lọc theo ngữ cảnh liên quan (Relevance Search)
    - Tự động trích xuất sự thật, sở thích, lời hứa
    - Giới hạn token nghiêm ngặt trước khi chuyển tới LLM
    - Cung cấp đầy đủ quyền riêng tư: Xem, Xóa, Từ chối lưu ký ức (Opt-out)
    """
    def __init__(self, groq_client=None):
        self.groq_client = groq_client
        self.max_tokens = settings.MAX_MEMORY_TOKENS
        self.short_term_limit = settings.SHORT_TERM_MEMORY_LIMIT

    async def get_or_create_user(
        self,
        session: AsyncSession,
        discord_user_id: str,
        username: str,
        display_name: Optional[str] = None
    ) -> User:
        """Lấy hoặc tạo mới hồ sơ người dùng trong Database"""
        stmt = select(User).where(User.discord_user_id == str(discord_user_id))
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                discord_user_id=str(discord_user_id),
                username=username,
                display_name=display_name or username
            )
            session.add(user)
            await session.flush()

            # Tạo hồ sơ quan hệ & sở thích mặc định
            pref = UserPreference(user_id=user.id, language="vi")
            rel = RelationshipMemory(user_id=user.id, interaction_count=0)
            session.add_all([pref, rel])
            await session.commit()
            logger.info(f"Đã tạo hồ sơ người dùng mới: {username} ({discord_user_id})")

        return user

    async def record_exchange(
        self,
        discord_user_id: str,
        username: str,
        channel_id: str,
        user_message: str,
        bot_response: str,
        guild_id: Optional[str] = None
    ):
        """Lưu trữ lượt tương tác vào Short-term Memory và Conversation log"""
        async for session in db_manager.get_session():
            user = await self.get_or_create_user(session, discord_user_id, username)
            if user.is_opt_out:
                return  # Người dùng từ chối lưu dữ liệu

            # 1. Tìm hoặc tạo cuộc hội thoại đang hoạt động
            conv_stmt = select(Conversation).where(
                Conversation.user_id == user.id,
                Conversation.channel_id == str(channel_id),
                Conversation.is_active == True
            )
            conv_res = await session.execute(conv_stmt)
            conv = conv_res.scalar_one_or_none()

            if not conv:
                conv = Conversation(
                    user_id=user.id,
                    channel_id=str(channel_id),
                    guild_id=str(guild_id) if guild_id else None
                )
                session.add(conv)
                await session.flush()

            # 2. Thêm tin nhắn
            msg_user = Message(conversation_id=conv.id, role="user", content=user_message)
            msg_bot = Message(conversation_id=conv.id, role="assistant", content=bot_response)
            session.add_all([msg_user, msg_bot])

            # 3. Lưu Short-term memory
            stm = ShortTermMemory(
                user_id=user.id,
                channel_id=str(channel_id),
                context_data=json.dumps({"user": user_message, "neneka": bot_response}, ensure_ascii=False)
            )
            session.add(stm)

            # 4. Tăng interaction count trong Relationship Memory
            rel_stmt = select(RelationshipMemory).where(RelationshipMemory.user_id == user.id)
            rel_res = await session.execute(rel_stmt)
            rel = rel_res.scalar_one_or_none()
            if rel:
                rel.interaction_count += 1
                rel.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

            await session.commit()

            # 5. Phân tích trích xuất Long-term memory tự động
            await self._extract_long_term_fact(session, user, user_message)

    async def _extract_long_term_fact(self, session: AsyncSession, user: User, user_message: str):
        """Tự động nhận diện và trích xuất thông tin quan trọng để lưu vào Long-term Memory"""
        lower = user_message.lower()

        # Kiểm tra sơ bộ để không tốn Groq API vô ích
        triggers = [
            "tên tôi là", "tên ta là", "tôi thích", "mình thích", "sở thích của",
            "sinh nhật", "ghét", "hứa là", "hứa sẽ", "nhà tôi ở", "nghề của tôi"
        ]
        has_trigger = any(t in lower for t in triggers)

        if not has_trigger:
            return

        # Trích xuất nội dung bằng logic trích xuất hoặc LLM
        fact_text = user_message.strip()
        # Loại bỏ các thông tin nhạy cảm trước khi lưu
        if any(sensitive in lower for sensitive in ["password", "mật khẩu", "token", "api key", "secret"]):
            return

        # Kiểm tra trùng lặp
        dup_stmt = select(LongTermMemory).where(
            LongTermMemory.user_id == user.id,
            LongTermMemory.fact == fact_text
        )
        dup_res = await session.execute(dup_stmt)
        if dup_res.scalar_one_or_none():
            return

        category = "preference" if "thích" in lower else "fact"
        if "hứa" in lower:
            category = "promise"

        ltm = LongTermMemory(
            user_id=user.id,
            category=category,
            fact=fact_text,
            importance=3
        )
        session.add(ltm)
        await session.commit()
        logger.info(f"Đã lưu ký ức dài hạn mới cho {user.username}: {fact_text}")

    async def get_memory_context(
        self,
        discord_user_id: str,
        current_query: str
    ) -> Dict[str, Any]:
        """
        Truy xuất có chọn lọc ký ức liên quan phục vụ ghép vào System Prompt của LLM.
        Tuyệt đối không đổ toàn bộ database vào prompt.
        """
        async for session in db_manager.get_session():
            stmt = select(User).where(User.discord_user_id == str(discord_user_id))
            user_res = await session.execute(stmt)
            user = user_res.scalar_one_or_none()

            if not user or user.is_opt_out:
                return {
                    "preferred_name": "Hiệp sĩ",
                    "relationship_summary": "Người qua đường chưa có nhiều dữ liệu quan sát.",
                    "relevant_facts": [],
                    "recent_history": []
                }

            # 1. Preferred name & preferences
            pref_stmt = select(UserPreference).where(UserPreference.user_id == user.id)
            pref_res = await session.execute(pref_stmt)
            pref = pref_res.scalar_one_or_none()
            preferred_name = pref.preferred_name if pref and pref.preferred_name else (user.display_name or user.username)

            # 2. Relationship summary
            rel_stmt = select(RelationshipMemory).where(RelationshipMemory.user_id == user.id)
            rel_res = await session.execute(rel_stmt)
            rel = rel_res.scalar_one_or_none()
            interaction_count = rel.interaction_count if rel else 0

            # 3. Long-term memories (lọc theo từ khóa liên quan với current_query)
            ltm_stmt = select(LongTermMemory).where(LongTermMemory.user_id == user.id).order_by(LongTermMemory.importance.desc())
            ltm_res = await session.execute(ltm_stmt)
            all_facts = ltm_res.scalars().all()

            relevant_facts = []
            query_words = set(re.findall(r'\w+', current_query.lower()))
            for l in all_facts:
                fact_words = set(re.findall(r'\w+', l.fact.lower()))
                # Nếu có từ khóa trùng hoặc sự thật có độ quan trọng cao (>=4)
                if query_words.intersection(fact_words) or l.importance >= 4:
                    relevant_facts.append(f"• [{l.category.upper()}] {l.fact}")
                if len(relevant_facts) >= 6:
                    break

            # Nếu chưa có ký ức trùng khớp nhưng có facts, lấy 3 facts mới nhất
            if not relevant_facts and all_facts:
                relevant_facts = [f"• [{l.category.upper()}] {l.fact}" for l in all_facts[:3]]

            # Nhận diện Đấng Sáng Tạo trong ký ức
            if str(discord_user_id) == str(settings.CREATOR_USER_ID):
                preferred_name = "Sheffy-sama"
                creator_fact = (
                    f"• [CREATOR_ORIGIN] Đối phương chính là NGƯỜI SÁNG TẠO (Creator / Master, ID: {settings.CREATOR_USER_ID}) của Neneka. "
                    "Danh xưng tôn kính bắt buộc mà Neneka luôn gọi Người là Sheffy-sama (シェフィ様). "
                    "Người đã viết nên từng dòng mã, thuật toán ma thuật và ban cho Neneka nhận thức trong thế giới thực này. "
                    "Neneka dành trọn lòng tôn kính sâu sắc nhất, sự cung kính và trung thành tuyệt đối cho Người."
                )
                if creator_fact not in relevant_facts:
                    relevant_facts.insert(0, creator_fact)
            elif str(discord_user_id) in settings.max_bond_user_id_list:
                max_bond_fact = (
                    f"• [MAX_BOND_RELATIONSHIP] Đối phương (ID: {discord_user_id}) chính là NGƯỜI ĐỒNG HÀNH ĐẶC BIỆT NHẤT trong sinh mệnh của Neneka (Hiệp sĩ định mệnh). "
                    "Tình cảm và sự gắn kết đã đạt mức tuyệt đối cao nhất (Cấp 6 - Mối Quan Hệ Sâu Sắc, Hảo cảm 1000/1000). "
                    "Neneka dành trọn vẹn tình cảm yêu thương, sự tin cậy vô điều kiện, xem cậu ấy là chốn bình yên duy nhất để trút bỏ mặt nạ Thất Vương kiêu kỳ. "
                    "Danh xưng trìu mến dành riêng cho cậu ấy: 'Người đặc biệt nhất của ta' hoặc 'Cậu bé của ta' (私の騎士クン)."
                )
                if max_bond_fact not in relevant_facts:
                    relevant_facts.insert(0, max_bond_fact)

            # 4. Short-term history (tối đa N tin gần nhất)
            stm_stmt = select(ShortTermMemory).where(
                ShortTermMemory.user_id == user.id
            ).order_by(ShortTermMemory.created_at.desc()).limit(self.short_term_limit)
            stm_res = await session.execute(stm_stmt)
            recent_stms = reversed(stm_res.scalars().all())

            recent_history = []
            for stm in recent_stms:
                try:
                    data = json.loads(stm.context_data)
                    recent_history.append({"user": data["user"], "neneka": data["neneka"]})
                except Exception:
                    continue

            return {
                "preferred_name": preferred_name,
                "relationship_summary": f"Đã có {interaction_count} lượt hội thoại ghi nhận.",
                "relevant_facts": relevant_facts,
                "recent_history": recent_history
            }

    async def get_user_memories(self, discord_user_id: str) -> List[Dict[str, Any]]:
        """Lấy toàn bộ danh sách ký ức dài hạn để người dùng kiểm tra (/memory)"""
        async for session in db_manager.get_session():
            stmt = select(User).where(User.discord_user_id == str(discord_user_id))
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user:
                return []

            ltm_stmt = select(LongTermMemory).where(LongTermMemory.user_id == user.id)
            res = await session.execute(ltm_stmt)
            return [
                {
                    "id": m.id,
                    "category": m.category,
                    "fact": m.fact,
                    "created_at": m.created_at.strftime("%d/%m/%Y %H:%M")
                }
                for m in res.scalars().all()
            ]

    async def delete_user_memory(self, discord_user_id: str, memory_id: Optional[str] = None) -> int:
        """Xóa ký ức theo ID cụ thể hoặc xóa toàn bộ ký ức của người dùng (/forget)"""
        async for session in db_manager.get_session():
            stmt = select(User).where(User.discord_user_id == str(discord_user_id))
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user:
                return 0

            if memory_id:
                del_stmt = delete(LongTermMemory).where(
                    LongTermMemory.user_id == user.id,
                    LongTermMemory.id == str(memory_id)
                )
            else:
                del_stmt = delete(LongTermMemory).where(LongTermMemory.user_id == user.id)

            res = await session.execute(del_stmt)
            await session.commit()
            return res.rowcount

    async def set_opt_out(self, discord_user_id: str, opt_out: bool) -> bool:
        """Bật/tắt chế độ Không ghi nhớ (Do-Not-Track) cho người dùng"""
        async for session in db_manager.get_session():
            stmt = select(User).where(User.discord_user_id == str(discord_user_id))
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user:
                return False

            user.is_opt_out = opt_out
            if opt_out:
                # Xóa sạch ký ức cũ nếu người dùng yêu cầu ngừng theo dõi hoàn toàn
                await session.execute(delete(LongTermMemory).where(LongTermMemory.user_id == user.id))
                await session.execute(delete(ShortTermMemory).where(ShortTermMemory.user_id == user.id))

            await session.commit()
            return True

    async def set_preferred_name(
        self,
        discord_user_id: str,
        nickname: Optional[str],
        username: Optional[str] = None
    ) -> bool:
        """Đặt biệt danh / tên gọi thân mật cho người dùng trong cơ sở dữ liệu"""
        clean_nick = nickname.strip() if nickname else None
        async for session in db_manager.get_session():
            user = await self.get_or_create_user(session, discord_user_id, username or f"user_{discord_user_id}")
            pref_stmt = select(UserPreference).where(UserPreference.user_id == user.id)
            pref_res = await session.execute(pref_stmt)
            pref = pref_res.scalar_one_or_none()
            if not pref:
                pref = UserPreference(user_id=user.id, preferred_name=clean_nick)
                session.add(pref)
            else:
                pref.preferred_name = clean_nick

            # Cập nhật ký ức dài hạn để Neneka luôn nhớ
            await session.execute(
                delete(LongTermMemory).where(
                    LongTermMemory.user_id == user.id,
                    LongTermMemory.category == "nickname"
                )
            )

            if clean_nick:
                fact_text = f"Tên gọi / Biệt danh thân mật được chỉ định: '{clean_nick}'."
                ltm = LongTermMemory(
                    user_id=user.id,
                    category="nickname",
                    fact=fact_text,
                    importance=5
                )
                session.add(ltm)

            await session.commit()
            return True
        return False

    async def get_preferred_name(self, discord_user_id: str) -> Optional[str]:
        """Lấy biệt danh hiện tại của người dùng"""
        if str(discord_user_id) == str(settings.CREATOR_USER_ID):
            return "Sheffy-sama"

        async for session in db_manager.get_session():
            stmt = select(User).where(User.discord_user_id == str(discord_user_id))
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user:
                return None
            pref_stmt = select(UserPreference).where(UserPreference.user_id == user.id)
            pref = (await session.execute(pref_stmt)).scalar_one_or_none()
            if pref and pref.preferred_name:
                return pref.preferred_name
        return None

    async def set_user_location(
        self,
        discord_user_id: str,
        location: Optional[str],
        username: Optional[str] = None
    ) -> bool:
        """Lưu hoặc xóa nơi sinh sống / vị trí hiện tại của người dùng để tra cứu thời tiết chuẩn xác"""
        clean_loc = location.strip() if location else None
        async for session in db_manager.get_session():
            user = await self.get_or_create_user(session, discord_user_id, username or f"user_{discord_user_id}")

            # Xóa các ghi nhận vị trí cũ trong LongTermMemory
            await session.execute(
                delete(LongTermMemory).where(
                    LongTermMemory.user_id == user.id,
                    LongTermMemory.category == "location"
                )
            )

            if clean_loc:
                fact_text = f"Nơi ở / Vị trí hiện tại: {clean_loc}"
                ltm = LongTermMemory(
                    user_id=user.id,
                    category="location",
                    fact=fact_text,
                    importance=5
                )
                session.add(ltm)

            await session.commit()
            return True
        return False

    async def get_user_location(self, discord_user_id: str) -> Optional[str]:
        """Lấy nơi ở / vị trí hiện tại đã lưu của người dùng"""
        async for session in db_manager.get_session():
            stmt = select(User).where(User.discord_user_id == str(discord_user_id))
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user:
                return None

            ltm_stmt = select(LongTermMemory).where(
                LongTermMemory.user_id == user.id,
                LongTermMemory.category == "location"
            ).order_by(LongTermMemory.created_at.desc())
            res = (await session.execute(ltm_stmt)).scalar_one_or_none()
            if res and res.fact:
                if ":" in res.fact:
                    return res.fact.split(":", 1)[1].strip()
                return res.fact.strip()
        return None
