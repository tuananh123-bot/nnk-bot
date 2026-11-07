# src/database/models.py
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Column, String, Integer, Text, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

# 1. users
class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    discord_user_id = Column(String(32), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    display_name = Column(String(100), nullable=True)
    is_opt_out = Column(Boolean, default=False)  # Quyền không lưu ký ức
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    preferences = relationship("UserPreference", back_populates="user", cascade="all, delete-orphan", uselist=False)
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    short_term_memories = relationship("ShortTermMemory", back_populates="user", cascade="all, delete-orphan")
    long_term_memories = relationship("LongTermMemory", back_populates="user", cascade="all, delete-orphan")
    relationship_memory = relationship("RelationshipMemory", back_populates="user", cascade="all, delete-orphan", uselist=False)
    bond_profile = relationship("BondProfile", back_populates="user", cascade="all, delete-orphan", uselist=False)

# 2. user_preferences
class UserPreference(Base):
    __tablename__ = "user_preferences"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    preferred_name = Column(String(100), nullable=True)
    language = Column(String(10), default="vi")  # vi, ja, en
    voice_enabled = Column(Boolean, default=True)
    allow_dm = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="preferences")

# 3. conversations
class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    guild_id = Column(String(32), nullable=True, index=True)
    channel_id = Column(String(32), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

# 4. messages
class Message(Base):
    __tablename__ = "messages"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    japanese_transcript = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    conversation = relationship("Conversation", back_populates="messages")

# 5. short_term_memories
class ShortTermMemory(Base):
    __tablename__ = "short_term_memories"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id = Column(String(32), nullable=False)
    topic = Column(String(200), nullable=True)
    context_data = Column(Text, nullable=False)  # JSON or text
    current_emotion = Column(String(50), default="calm")
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", back_populates="short_term_memories")

# 6. long_term_memories
class LongTermMemory(Base):
    __tablename__ = "long_term_memories"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(50), default="general")  # preference, hobby, promise, lore, fact
    fact = Column(Text, nullable=False)
    importance = Column(Integer, default=1)  # 1-5
    last_referenced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="long_term_memories")

# 7. relationship_memories
class RelationshipMemory(Base):
    __tablename__ = "relationship_memories"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    interaction_count = Column(Integer, default=0)
    trust_milestones = Column(Text, default="[]")  # JSON
    special_events = Column(Text, default="[]")    # JSON
    nickname_used = Column(String(50), default="Cậu")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="relationship_memory")

# 8. bond_profiles
class BondProfile(Base):
    __tablename__ = "bond_profiles"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    bond_level = Column(Integer, default=0)  # 0: Stranger to 6+: Deep Relationship
    bond_points = Column(Integer, default=0)
    unlocked_features = Column(Text, default="[]")  # JSON list
    last_interacted_at = Column(DateTime, default=utc_now)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="bond_profile")
    events = relationship("BondEvent", back_populates="bond_profile", cascade="all, delete-orphan")

# 9. bond_events
class BondEvent(Base):
    __tablename__ = "bond_events"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    bond_profile_id = Column(String(36), ForeignKey("bond_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # FIRST_INTERACTION, BOND_LEVEL_UP, etc.
    points_awarded = Column(Integer, default=0)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    bond_profile = relationship("BondProfile", back_populates="events")

# 10. character_profiles
class CharacterProfile(Base):
    __tablename__ = "character_profiles"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    code_name = Column(String(50), unique=True, nullable=False)  # neneka
    full_name = Column(String(100), nullable=False)
    japanese_name = Column(String(100), nullable=False)
    title = Column(String(100), nullable=False)  # Metamorph Monarch / Thất Vương
    base_description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    variants = relationship("CharacterVariant", back_populates="profile", cascade="all, delete-orphan")

# 11. character_variants
class CharacterVariant(Base):
    __tablename__ = "character_variants"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    character_profile_id = Column(String(36), ForeignKey("character_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_name = Column(String(50), nullable=False)  # original, new_year, alpha
    display_title = Column(String(100), nullable=False)
    lore_description = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

    profile = relationship("CharacterProfile", back_populates="variants")
    costumes = relationship("Costume", back_populates="variant", cascade="all, delete-orphan")

# 12. costumes
class Costume(Base):
    __tablename__ = "costumes"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    variant_id = Column(String(36), ForeignKey("character_variants.id", ondelete="CASCADE"), nullable=False, index=True)
    costume_name = Column(String(100), nullable=False)
    visual_description = Column(Text, nullable=False)
    dialogue_flair = Column(Text, nullable=True)
    asset_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    variant = relationship("CharacterVariant", back_populates="costumes")

# 13. stories
class Story(Base):
    __tablename__ = "stories"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    category = Column(String(50), nullable=False)  # main, character, bond, event, original_ai
    title = Column(String(200), nullable=False)
    canon_status = Column(String(30), default="CANON")  # CANON, LORE, ORIGINAL_AI, UNKNOWN
    summary = Column(Text, nullable=False)
    related_characters = Column(String(255), default="")
    created_at = Column(DateTime, default=utc_now)

    references = relationship("StoryReference", back_populates="story", cascade="all, delete-orphan")

# 14. story_references
class StoryReference(Base):
    __tablename__ = "story_references"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    story_id = Column(String(36), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(100), nullable=False)  # game_event, main_arc, bond_story
    episode_id = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    story = relationship("Story", back_populates="references")

# 15. voice_profiles
class VoiceProfile(Base):
    __tablename__ = "voice_profiles"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    provider_name = Column(String(50), nullable=False)  # edge, gemini
    voice_identifier = Column(String(100), nullable=False)
    pitch = Column(String(20), default="-14Hz")
    speed = Column(String(20), default="-6%")
    stability = Column(String(20), default="calm")
    created_at = Column(DateTime, default=utc_now)

# 16. voice_cache
class VoiceCache(Base):
    __tablename__ = "voice_cache"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    text_hash = Column(String(64), unique=True, nullable=False, index=True)
    japanese_text = Column(Text, nullable=False)
    audio_path = Column(String(255), nullable=False)
    duration_seconds = Column(Integer, default=0)
    created_at = Column(DateTime, default=utc_now)

# 17. emotion_states
class EmotionStateRecord(Base):
    __tablename__ = "emotion_states"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    discord_user_id = Column(String(32), nullable=False, index=True)
    confidence = Column(Integer, default=85)
    curiosity = Column(Integer, default=75)
    affection = Column(Integer, default=150)
    trust = Column(Integer, default=40)
    amusement = Column(Integer, default=50)
    irritation = Column(Integer, default=10)
    seriousness = Column(Integer, default=70)
    current_emotion = Column(String(50), default="calm_analytical")
    created_at = Column(DateTime, default=utc_now)

# 18. proactive_logs
class ProactiveLog(Base):
    __tablename__ = "proactive_logs"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    guild_id = Column(String(32), nullable=True, index=True)
    channel_id = Column(String(32), nullable=False, index=True)
    trigger_type = Column(String(50), nullable=False)  # scheduled, return_welcome, event
    chosen_action = Column(String(50), nullable=False)  # speak, silent, react
    decision_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

# 19. bot_settings
class BotSetting(Base):
    __tablename__ = "bot_settings"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    guild_id = Column(String(32), nullable=True, index=True)
    key = Column(String(100), nullable=False, index=True)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (UniqueConstraint("guild_id", "key", name="uq_guild_key"),)

