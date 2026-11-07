# tests/test_database.py
import pytest
from sqlalchemy import select
from src.database.connection import db_manager
from src.database.models import User, UserPreference, CharacterProfile, Base

@pytest.mark.asyncio
async def test_database_initialization_and_models():
    await db_manager.initialize()

    # Check that metadata has all 19 tables
    table_names = list(Base.metadata.tables.keys())
    assert "users" in table_names
    assert "bond_profiles" in table_names
    assert "long_term_memories" in table_names
    assert "character_profiles" in table_names
    assert "voice_profiles" in table_names
    assert len(table_names) >= 19

    async for session in db_manager.get_session():
        u = User(discord_user_id="test_db_user_1", username="DBUser")
        session.add(u)
        await session.commit()

        # Query back
        res = await session.execute(select(User).where(User.discord_user_id == "test_db_user_1"))
        fetched = res.scalar_one_or_none()
        assert fetched is not None
        assert fetched.username == "DBUser"

    await db_manager.close()
