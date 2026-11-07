# src/database/connection.py
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.config import settings
from src.database.models import Base

logger = logging.getLogger("Neneka.Database")

class DatabaseManager:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self.is_sqlite_fallback = False

    async def initialize(self):
        """Khởi tạo kết nối DB: Thử PostgreSQL trước, fallback SQLite nếu offline"""
        # 1. Thử kết nối PostgreSQL
        try:
            logger.info(f"Đang kết nối PostgreSQL qua: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'localhost'}...")
            pg_engine = create_async_engine(
                settings.DATABASE_URL,
                echo=settings.DB_ECHO,
                pool_pre_ping=True
            )
            # Test kết nối bằng một execute nhỏ
            async with pg_engine.connect() as conn:
                pass

            self.engine = pg_engine
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            self.is_sqlite_fallback = False
            logger.info("Kết nối PostgreSQL thành công!")

        except Exception as e:
            logger.warning(
                f"Không thể kết nối PostgreSQL ({e}). Đang tự động chuyển sang Async SQLite Fallback: {settings.SQLITE_FALLBACK_URL}"
            )
            self.engine = create_async_engine(
                settings.SQLITE_FALLBACK_URL,
                echo=settings.DB_ECHO
            )
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            self.is_sqlite_fallback = True

        # Tự động tạo bảng nếu chưa có (rất thuận tiện cho SQLite & dev)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Khởi tạo cấu trúc các bảng Database thành công!")

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        if not self.session_factory:
            await self.initialize()
        async with self.session_factory() as session:
            yield session

    async def close(self):
        if self.engine:
            await self.engine.dispose()

db_manager = DatabaseManager()

