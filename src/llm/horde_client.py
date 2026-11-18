# src/llm/horde_client.py
"""
Client tích hợp AI Horde API (https://aihorde.net/)
Hỗ trợ:
1. Sinh ảnh AI phân tán (Stable Diffusion, SDXL, Anime, Illustrious, Pony, NSFW)
2. Sinh văn bản / Chat LLM (KoboldAI Horde)
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import aiohttp

from src.config import settings

logger = logging.getLogger("Neneka.AIHorde")

AI_HORDE_BASE_URL = "https://aihorde.net/api/v2"
CLIENT_AGENT = "NenekaDiscordBot:1.0:github.com/tuananh123-bot/nnk-bot"

# Danh sách model vẽ anime / nghệ thuật phổ biến trên AI Horde
DEFAULT_ANIME_IMAGE_MODELS = [
    "WAI-ANI-NSFW-PONYXL",
    "Animagine XL",
    "Counterfeit",
    "Grapefruit Hentai",
    "DreamShaper XL",
    "Juggernaut XL",
    "ICBINP XL"
]

NENEKA_PROMPT_TAGS = (
    "1girl, utsushimi neneka, (neneka \\(princess connect!\\):1.3), "
    "purple hair, long twintails, purple eyes, golden crown, mature female, "
    "masterpiece, best quality, highly detailed"
)

DEFAULT_NEGATIVE_PROMPT = (
    "ugly, deformed, disfigured, poor quality, bad anatomy, bad hands, missing fingers, "
    "extra limbs, blurry, cropped, watermark, signature, username, lowres"
)


class AIHordeClient:
    """Client tương tác với AI Horde REST API v2."""

    def __init__(self, api_key: Optional[str] = None):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = getattr(settings, "AI_HORDE_API_KEY", "") or "0000000000"

    def is_available(self) -> bool:
        """Kiểm tra xem API key đã được cấu hình hay chưa (không phải anonymous 0000000000)."""
        return bool(self.api_key and self.api_key != "0000000000")

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.api_key,
            "Client-Agent": CLIENT_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post(self, session: Any, endpoint: str, payload: dict) -> dict:
        url = f"{AI_HORDE_BASE_URL}/{endpoint}"
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status not in (200, 202):
                err_txt = await resp.text()
                raise RuntimeError(f"AI Horde submit error ({resp.status}): {err_txt}")
            return await resp.json()

    async def _get(self, session: Any, endpoint: str) -> dict:
        url = f"{AI_HORDE_BASE_URL}/{endpoint}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return {}
            return await resp.json()

    async def _execute_generate_image(
        self,
        session: Any,
        final_prompt: str,
        payload: dict,
        timeout_seconds: int,
        poll_interval: float = 4.0,
    ) -> Dict[str, Any]:
        data = await self._post(session, "generate/async", payload)
        req_id = data.get("id")
        if not req_id:
            raise RuntimeError("AI Horde không trả về Request ID hợp lệ.")

        logger.info(f"AI Horde Image Request [{req_id}] submitted. Polling...")

        elapsed = 0.0
        while elapsed < timeout_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            status_data = await self._get(session, f"generate/status/{req_id}")
            if status_data.get("done"):
                generations = status_data.get("generations", [])
                if not generations:
                    raise RuntimeError("AI Horde thông báo hoàn thành nhưng không có ảnh nào.")
                gen = generations[0]
                return {
                    "img_url": gen.get("img"),
                    "seed": gen.get("seed", ""),
                    "model": gen.get("model", ""),
                    "id": req_id,
                    "prompt": final_prompt,
                }

            if status_data.get("faulted"):
                raise RuntimeError(f"AI Horde Image Request [{req_id}] bị lỗi từ worker.")

        raise TimeoutError(f"AI Horde Image Request [{req_id}] vượt quá thời gian chờ ({timeout_seconds}s).")

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 512,
        height: int = 768,
        steps: int = 25,
        cfg_scale: float = 7.0,
        is_nsfw: bool = True,
        models: Optional[List[str]] = None,
        timeout_seconds: int = 120,
        session: Optional[Any] = None,
        poll_interval: float = 4.0,
    ) -> Dict[str, Any]:
        """
        Gửi yêu cầu sinh ảnh tới AI Horde và đợi hoàn thành (asynchronous polling).
        """
        clean_prompt = prompt.strip()
        if "neneka" in clean_prompt.lower():
            final_prompt = f"{NENEKA_PROMPT_TAGS}, {clean_prompt}"
        else:
            final_prompt = clean_prompt

        final_negative = negative_prompt or DEFAULT_NEGATIVE_PROMPT

        payload = {
            "prompt": f"{final_prompt} ### {final_negative}",
            "params": {
                "sampler_name": "k_euler_a",
                "cfg_scale": cfg_scale,
                "steps": steps,
                "width": width,
                "height": height,
                "karras": True,
                "post_processing": [],
            },
            "nsfw": is_nsfw,
            "censor_nsfw": not is_nsfw,
            "models": models or DEFAULT_ANIME_IMAGE_MODELS,
            "r2": True,
        }

        if session is not None:
            return await self._execute_generate_image(session, final_prompt, payload, timeout_seconds, poll_interval)

        async with aiohttp.ClientSession(headers=self._headers()) as sess:
            return await self._execute_generate_image(sess, final_prompt, payload, timeout_seconds, poll_interval)

    async def _execute_generate_text(
        self,
        session: Any,
        payload: dict,
        timeout_seconds: int,
        poll_interval: float = 3.0,
    ) -> str:
        data = await self._post(session, "generate/text/async", payload)
        req_id = data.get("id")
        if not req_id:
            raise RuntimeError("AI Horde Text không trả về Request ID.")

        elapsed = 0.0
        while elapsed < timeout_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            status_data = await self._get(session, f"generate/text/status/{req_id}")
            if status_data.get("done"):
                gens = status_data.get("generations", [])
                if not gens:
                    return ""
                return gens[0].get("text", "").strip()

            if status_data.get("faulted"):
                raise RuntimeError(f"AI Horde Text [{req_id}] bị lỗi worker.")

        raise TimeoutError(f"AI Horde Text [{req_id}] timeout ({timeout_seconds}s).")

    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.8,
        models: Optional[List[str]] = None,
        timeout_seconds: int = 90,
        session: Optional[Any] = None,
        poll_interval: float = 3.0,
    ) -> str:
        """
        Sinh văn bản qua KoboldAI Horde.
        """
        payload = {
            "prompt": prompt,
            "params": {
                "max_context_length": 2048,
                "max_length": max_tokens,
                "temperature": temperature,
                "rep_pen": 1.15,
                "top_p": 0.9,
            },
            "models": models or [],
        }

        if session is not None:
            return await self._execute_generate_text(session, payload, timeout_seconds, poll_interval)

        async with aiohttp.ClientSession(headers=self._headers()) as sess:
            return await self._execute_generate_text(sess, payload, timeout_seconds, poll_interval)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 300,
        temperature: float = 0.8,
        session: Optional[Any] = None,
        poll_interval: float = 3.0,
    ) -> str:
        """Chuyển đổi danh sách tin nhắn theo format chat rồi gọi generate_text."""
        formatted_prompt = ""
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                formatted_prompt += f"[Instruction: {content}]\n\n"
            elif role == "user":
                formatted_prompt += f"User: {content}\n"
            elif role == "assistant":
                formatted_prompt += f"Neneka: {content}\n"
        formatted_prompt += "Neneka:"
        return await self.generate_text(
            formatted_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            session=session,
            poll_interval=poll_interval
        )


horde_client = AIHordeClient()
