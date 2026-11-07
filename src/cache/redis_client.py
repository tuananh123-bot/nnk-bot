# src/cache/redis_client.py
import time
import asyncio
import logging
from typing import Optional, Any
from src.config import settings

logger = logging.getLogger("Neneka.Cache")

class InMemoryCache:
    """Bộ nhớ đệm trong RAM dùng khi Redis không khả dụng."""
    def __init__(self):
        self._store = {}
        self._expiry = {}

    async def get(self, key: str) -> Optional[str]:
        if key in self._expiry and time.time() > self._expiry[key]:
            del self._store[key]
            del self._expiry[key]
            return None
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        self._store[key] = value
        if ex:
            self._expiry[key] = time.time() + ex
        elif key in self._expiry:
            del self._expiry[key]
        return True

    async def delete(self, key: str) -> int:
        deleted = 0
        if key in self._store:
            del self._store[key]
            deleted = 1
        if key in self._expiry:
            del self._expiry[key]
        return deleted

    async def exists(self, key: str) -> bool:
        val = await self.get(key)
        return val is not None

class RedisManager:
    """
    Quản lý kết nối Redis Async. Tự động chuyển đổi sang InMemoryCache
    nếu Redis server offline hoặc chưa được cấu hình.
    """
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis = None
        self._fallback = InMemoryCache()
        self._use_fallback = False

    async def initialize(self):
        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=1.5
            )
            # Test ping
            await client.ping()
            self._redis = client
            self._use_fallback = False
            logger.info("Kết nối Redis thành công!")
        except Exception as e:
            logger.warning(f"Không thể kết nối Redis ({e}). Tự động kích hoạt In-Memory Cache.")
            self._use_fallback = True

    async def get(self, key: str) -> Optional[str]:
        if self._use_fallback or not self._redis:
            return await self._fallback.get(key)
        try:
            return await self._redis.get(key)
        except Exception as e:
            logger.warning(f"Lỗi khi đọc Redis key {key}: {e}. Đang đọc từ cache dự phòng.")
            return await self._fallback.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        if self._use_fallback or not self._redis:
            return await self._fallback.set(key, value, ex=ex)
        try:
            return await self._redis.set(key, value, ex=ex)
        except Exception as e:
            logger.warning(f"Lỗi khi ghi Redis key {key}: {e}. Đang ghi vào cache dự phòng.")
            return await self._fallback.set(key, value, ex=ex)

    async def delete(self, key: str) -> int:
        if self._use_fallback or not self._redis:
            return await self._fallback.delete(key)
        try:
            return await self._redis.delete(key)
        except Exception:
            return await self._fallback.delete(key)

    async def close(self):
        if self._redis:
            await self._redis.close()

cache = RedisManager()
