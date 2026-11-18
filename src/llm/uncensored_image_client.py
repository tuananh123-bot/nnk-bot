# src/llm/uncensored_image_client.py
"""
Client kết nối tới Uncensored AI API (https://api.uncensored.com)
Hỗ trợ tạo ảnh Text-to-Image không kiểm duyệt (Uncensored / Mature / Realistic / Anime).
Model mặc định: seedream-v5
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import aiohttp

from src.config import settings

logger = logging.getLogger("Neneka.UncensoredImage")


class UncensoredImageClient:
    """Client tương tác với Uncensored AI Images API (/api/v1/images/generations)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
    ):
        self.api_key = api_key if api_key is not None else getattr(settings, "UNCENSORED_API_KEY", "")
        raw_base = base_url if base_url is not None else getattr(settings, "UNCENSORED_IMAGE_BASE_URL", "https://api.uncensored.com/api/v1")
        self.base_url = raw_base.rstrip("/")
        self.default_model = default_model if default_model is not None else getattr(settings, "UNCENSORED_IMAGE_MODEL", "seedream-v5")

    def is_available(self) -> bool:
        """Kiểm tra API key có được cấu hình và hợp lệ hay không."""
        return bool(self.api_key and self.api_key.startswith("uai_"))

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-api-key": self.api_key,
        }

    async def _post_generate(self, session: aiohttp.ClientSession, endpoint: str, payload: dict) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        async with session.post(url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=45)) as resp:
            if resp.status == 402:
                err_body = await resp.text()
                raise RuntimeError(
                    f"Tài khoản Uncensored AI không đủ credit (402 Insufficient credits). "
                    f"Vui lòng nạp thêm credit trên uncensored.com. Chi tiết: {err_body}"
                )
            if resp.status not in (200, 201, 202):
                err_body = await resp.text()
                raise RuntimeError(f"Uncensored AI submit error ({resp.status}): {err_body}")
            return await resp.json()

    async def _poll_status(self, session: aiohttp.ClientSession, status_url: str, timeout_seconds: int, poll_interval: float) -> dict:
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout_seconds:
            await asyncio.sleep(poll_interval)
            try:
                async with session.get(status_url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    status = data.get("status", "").lower()
                    if status in ("completed", "succeeded", "ready") or data.get("url"):
                        return data
                    if status in ("failed", "error"):
                        raise RuntimeError(f"Uncensored AI job failed: {data.get('error', 'Unknown error')}")
            except Exception as e:
                logger.warning(f"Lỗi khi poll status Uncensored AI: {e}")
        raise TimeoutError(f"Quá thời gian chờ ({timeout_seconds}s) khi tạo ảnh trên Uncensored AI.")

    async def generate_image(
        self,
        prompt: str,
        model: Optional[str] = None,
        timeout_seconds: int = 120,
        poll_interval: float = 3.0,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Dict[str, Any]:
        """
        Gửi yêu cầu tạo ảnh đến Uncensored AI endpoint:
        POST /api/v1/images/generations
        """
        clean_prompt = prompt.strip()
        chosen_model = model or self.default_model or "seedream-v5"

        payload = {
            "model": chosen_model,
            "prompt": clean_prompt,
        }

        async def _execute(sess: aiohttp.ClientSession) -> Dict[str, Any]:
            logger.info(f"Submitting image generation to Uncensored AI [{chosen_model}]...")
            data = await self._post_generate(sess, "images/generations", payload)

            # Trường hợp 1: Trả về URL trực tiếp
            img_url = data.get("url")
            if not img_url and isinstance(data.get("data"), list) and len(data["data"]) > 0:
                img_url = data["data"][0].get("url")

            # Trường hợp 2: Trả về status_url để polling
            if not img_url and data.get("status_url"):
                status_url = data["status_url"]
                logger.info(f"Uncensored AI returned status_url, polling: {status_url}")
                poll_result = await self._poll_status(sess, status_url, timeout_seconds, poll_interval)
                img_url = poll_result.get("url")
                if not img_url and isinstance(poll_result.get("data"), list) and len(poll_result["data"]) > 0:
                    img_url = poll_result["data"][0].get("url")

            if not img_url:
                raise RuntimeError(f"Không tìm thấy URL ảnh trong phản hồi của Uncensored AI: {data}")

            return {
                "img_url": img_url,
                "model": chosen_model,
                "prompt": clean_prompt,
                "provider": "uncensored.com",
            }

        if session is not None:
            return await _execute(session)

        async with aiohttp.ClientSession() as sess:
            return await _execute(sess)


uncensored_image_client = UncensoredImageClient()
