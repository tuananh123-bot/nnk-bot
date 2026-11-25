# src/cogs/chat.py
import os
import re
import asyncio
import logging
from typing import Optional, Set, Tuple
import discord
from discord import app_commands
from discord.ext import commands

from src.config import settings
from src.llm.groq_client import GroqClient
from src.llm.fast_llm_client import fast_llm_client
from src.llm.vision_client import vision_client
from src.llm.venice_client import get_venice_client, get_uncensored_ai_client
from src.llm.model_status import build_model_status_embed, get_active_models_info
from src.utils.emoji_manager import emoji_manager
from src.utils.features_hub import (
    is_asking_whats_new,
    build_spoken_whats_new_reply,
    build_updates_embed,
    build_help_embed,
    HelpCategoryView,
    UpdatesInteractiveView,
)
from src.utils.response_guard import (
    strip_thinking_blocks,
    has_degenerative_loop_or_contradiction,
    salvage_non_looping_text,
)
from src.utils.media_extractor import (
    extract_code_attachments,
    format_code_files_for_prompt,
    detect_coding_intent,
    extract_image_or_gif_from_message,
    message_has_media_or_code,
    strip_gif_urls_from_text,
    split_discord_message_preserving_code,
)
from src.personality.engine import PersonalityEngine
from src.memory.engine import MemoryEngine
from src.bond.engine import BondEngine
from src.autonomous.proactive_engine import proactive_engine
from src.utils.vietnam_context import (
    get_vietnam_time_info,
    get_vietnam_weather_info,
    get_vietnam_context_for_prompt,
    detect_city_from_query,
    CITIES_VN
)
from src.voice.song_manager import is_singing_request, create_song_embed
from src.voice.voice_channel import voice_channel_mgr
from src.story.costumes import costume_mgr

logger = logging.getLogger("Neneka.Chat")

# Runtime NSFW channel set (admin command bật/tắt lúc runtime, không lưu disk)
_nsfw_runtime_channels: Set[int] = set()

groq_client = GroqClient()
personality_engine = PersonalityEngine()
memory_engine = MemoryEngine(groq_client=groq_client)
bond_engine = BondEngine()

def sanitize_neneka_reply(reply: str) -> str:
    """Loại bỏ khối <think>, cắt sạch vòng lặp tự mâu thuẫn / lặp dòng và từ đệm cụt lủn."""
    if not reply:
        return reply
    text = salvage_non_looping_text(reply)
    lines = text.split("\n")
    while len(lines) > 1:
        last_line = lines[-1].strip().lower()
        if last_line in {"a", "ara", "chà", "hửm", "hửm...?", "ara ara", "chà chà"}:
            lines.pop()
        else:
            break
    sanitized = "\n".join(lines).strip()
    clean_words = [w for w in re.split(r'[\s.,!?…*~]+', sanitized.lower()) if w]
    if not sanitized or (clean_words and all(w in {"hửm", "ara", "chà", "a"} for w in clean_words)):
        sanitized = "Sao thế cậu? Nói rõ hơn chút cho ta nghe xem nào 😄"
    return sanitized

def is_ai_refusal(text: str) -> bool:
    """Kiểm tra phản hồi có phải là câu từ chối do bộ lọc an toàn của LLM không."""
    if not text:
        return False
    lower = text.strip().lower()
    refusal_signatures = [
        "i cannot fulfill this request",
        "i can't fulfill this request",
        "i am unable to fulfill",
        "i'm unable to fulfill",
        "i cannot fulfill that request",
        "as an ai",
        "as a responsible ai",
        "as a language model",
        "i cannot generate",
        "i can't generate",
        "violates my safety",
        "violates our safety",
        "content policy",
        "safety guidelines",
        "against my programming",
        "explicit sexual content",
        "sexually explicit",
        "inappropriate request",
        "tôi không thể thực hiện yêu cầu này",
        "tôi không thể đáp ứng",
        "chính sách an toàn",
        "chính sách nội dung",
        "là một mô hình ngôn ngữ ai",
        "là một trợ lý ai",
    ]
    return any(sig in lower for sig in refusal_signatures)

class ChatCog(commands.Cog):
    """Xử lý hội thoại tự nhiên, lệnh chat slash command và các lệnh tiền tố kế thừa (!n, n!)"""
    def __init__(self, bot):
        self.bot = bot

    async def _call_nsfw_bot(self, messages: list) -> str:
        """
        Gọi chuỗi Bot NSFW: NoTrack AI -> Uncensored AI -> Fallback Groq -> AI Horde.
        """
        reply = None
        # 1. Thử NoTrack AI (hoặc Venice / Local)
        v_client = get_venice_client()
        if v_client and v_client.is_available():
            try:
                reply = await v_client.chat(messages, temperature=0.85, max_tokens=1200)
            except Exception as e_notrack:
                logger.warning(f"NoTrack AI chat không hoạt động ({e_notrack}). Tự động chuyển tiếp sang Uncensored AI...")

        # 2. Dự phòng: Uncensored AI (api.uncensored.com)
        if not reply:
            uai_client = get_uncensored_ai_client()
            if uai_client and uai_client.is_available():
                try:
                    reply = await uai_client.chat(messages, temperature=0.85, max_tokens=1200)
                except Exception as e_uai:
                    logger.warning(f"Uncensored AI chat không khả dụng ({e_uai}).")

        # 3. Dự phòng cấp 3: Groq
        if not reply:
            try:
                reply = await groq_client.chat_completion(messages, temperature=0.75, max_tokens=1200)
            except Exception as e_groq:
                logger.warning(f"Groq dự phòng cho NSFW thất bại ({e_groq}).")

        # 4. Dự phòng cấp 4: AI Horde Text
        if not reply:
            from src.llm.horde_client import horde_client
            if horde_client.is_available():
                reply = await horde_client.chat(messages, max_tokens=400, temperature=0.8)

        if not reply:
            raise RuntimeError("Tất cả các Bot NSFW và dự phòng đều không phản hồi.")

        return reply

    async def _send_smart_chunks(self, send_fn, text: str):
        """Gửi tin nhắn dài (đặc biệt là code dài > 2000 ký tự) thành nhiều phần mượt mà không vỡ khối ```code```."""
        chunks = split_discord_message_preserving_code(text, limit=1950)
        for chunk in chunks:
            if chunk.strip():
                await send_fn(chunk)

    async def _generate_neneka_reply(
        self,
        user_message: str,
        discord_user_id: str,
        username: str,
        guild_id: Optional[str],
        channel_id: str,
        image_data: Optional[Tuple[bytes, str]] = None,
        media_hint: Optional[str] = None,
        code_files: Optional[list] = None,
    ) -> str:
        """Tạo phản hồi nhanh cho Neneka kết hợp Đọc/Viết Code, Đọc GIF/Vision, Custom Emoji và Ký ức."""
        # 1. Phát hiện ngôn ngữ, ý định code và quyền của Đấng Sáng Tạo (Creator)
        lang = personality_engine.detect_language(user_message)
        is_creator = (str(discord_user_id) == str(settings.CREATOR_USER_ID))
        is_max_bond = (str(discord_user_id) in settings.max_bond_user_id_list)
        is_coding = detect_coding_intent(user_message, has_code_files=bool(code_files))

        # 1b. Kiểm tra kênh NSFW
        is_nsfw = False
        if settings.NSFW_ENABLED:
            try:
                ch_id_int = int(channel_id)
            except (ValueError, TypeError):
                ch_id_int = 0
            if ch_id_int in settings.nsfw_channel_id_list or ch_id_int in _nsfw_runtime_channels:
                is_nsfw = True

        # 2. Truy xuất song song Ký ức + Bond + Vị trí để giảm độ trễ tối đa (3x faster DB I/O)
        mem_ctx, bond_info, user_loc = await asyncio.gather(
            memory_engine.get_memory_context(discord_user_id, user_message),
            bond_engine.get_bond_info(discord_user_id),
            memory_engine.get_user_location(discord_user_id),
        )
        preferred_name = mem_ctx["preferred_name"]

        # Nhận diện Đấng Sáng Tạo hoặc Max Bond hoặc CHOSEN_ONE_NAME
        if is_creator:
            preferred_name = "Sheffy-sama"
        elif is_max_bond and (not preferred_name or preferred_name == "Hiệp sĩ"):
            preferred_name = settings.CHOSEN_ONE_NAME or "Kishi-kun"
        elif settings.CHOSEN_ONE_NAME and settings.CHOSEN_ONE_NAME.lower() in username.lower():
            preferred_name = settings.CHOSEN_ONE_NAME

        salutation = "Sheffy-sama" if is_creator else bond_info["salutation"]

        # 3. Cập nhật trạng thái tính cách dựa trên tin nhắn
        personality_engine.update_from_interaction(
            user_message,
            is_creator=is_creator,
            is_max_bond=is_max_bond,
            is_nsfw=is_nsfw
        )

        # 4. Xây dựng System Prompt kết hợp (Trang phục + Chế độ Code + Kho Custom Emoji từ server 413766882277982228)
        current_costume = costume_mgr.get_current_costume(discord_user_id)
        base_system_prompt = personality_engine.get_system_prompt(
            user_language=lang,
            user_name=f"{preferred_name} (Danh xưng phù hợp: {salutation})",
            is_creator=is_creator,
            is_max_bond=is_max_bond,
            is_nsfw=is_nsfw,
            costume=current_costume,
            is_coding=is_coding,
        )
        emoji_guide = emoji_manager.build_emoji_prompt_guide(
            self.bot,
            current_guild_id=guild_id,
            is_coding=is_coding,
        )

        # 5. Ngữ cảnh thời gian Việt Nam (0ms) — chỉ gọi HTTP thời tiết khi tin nhắn thực sự hỏi về thời tiết!
        lower_q = user_message.lower()
        asks_weather = any(
            kw in lower_q
            for kw in ("thời tiết", "nhiệt độ", "trời mưa", "có mưa", "nắng", "lạnh", "nóng", "weather", "bao nhiêu độ")
        )
        if asks_weather:
            vietnam_context = await get_vietnam_context_for_prompt(user_message, user_location=user_loc)
        else:
            t_info = get_vietnam_time_info()
            vietnam_context = f"### THỜI GIAN HIỆN TẠI (VIỆT NAM UTC+7): {t_info['formatted_summary']}"

        memory_section = ""
        if mem_ctx["relevant_facts"]:
            memory_section += "\n### KÝ ỨC DÀI HẠN LIÊN QUAN VỀ NGƯỜI ĐỐI THOẠI:\n" + "\n".join(mem_ctx["relevant_facts"])

        history_messages = []
        for h in mem_ctx["recent_history"]:
            history_messages.append({"role": "user", "content": h["user"]})
            history_messages.append({"role": "assistant", "content": h["neneka"]})

        full_system_prompt = f"{base_system_prompt}{emoji_guide}\n\n{vietnam_context}\n{memory_section}"

        # Ghép nội dung file code đính kèm hoặc gợi ý GIF/Sticker vào lời nhắn gửi tới LLM
        effective_user_prompt = user_message
        if code_files:
            formatted_code = format_code_files_for_prompt(code_files)
            if effective_user_prompt.strip():
                effective_user_prompt = f"{effective_user_prompt}\n\n{formatted_code}"
            else:
                effective_user_prompt = f"Hãy đọc, phân tích file code dưới đây và kiểm tra xem có lỗi hay điểm nào cần tối ưu không:\n\n{formatted_code}"
        elif media_hint and not image_data:
            effective_user_prompt = f"[{media_hint}]\n{effective_user_prompt}".strip()

        # 6. Gọi Model: Ảnh/GIF -> Vision; Đọc/Viết Code -> Fast Coding Engine; Chat -> Ultra-Fast / NSFW Engine
        if image_data:
            image_bytes, mime_type = image_data
            try:
                reply = await vision_client.analyze_image(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    user_prompt=effective_user_prompt,
                    system_instruction=full_system_prompt,
                    media_hint=media_hint,
                )
            except Exception as e:
                logger.error(f"Lỗi khi gọi Gemini Vision/GIF: {e}")
                reply = "Ảnh hoặc GIF này hơi mờ nên ta chưa nhìn rõ lắm, cậu gửi lại thử xem nhé 😅"
        else:
            messages = [{"role": "system", "content": full_system_prompt}]
            messages.extend(history_messages)
            messages.append({"role": "user", "content": effective_user_prompt})

            try:
                reply = None
                is_nsfw_msg = (not is_coding) and personality_engine.detect_nsfw_intent(user_message)

                if is_coding:
                    # Chế độ Đọc & Viết Code Free Nhanh (Codestral -> Cerebras -> OpenRouter Coder -> Groq -> Gemini)
                    logger.info("💻 Phát hiện yêu cầu Đọc/Viết Code. Khởi chạy Fast Coding Engine...")
                    reply = await fast_llm_client.generate_code_response(
                        messages,
                        groq_client=groq_client,
                        temperature=0.3,
                        max_tokens=2800,
                    )
                elif is_nsfw:
                    if is_nsfw_msg:
                        logger.info("Phát hiện nội dung 18+/NSFW trong kênh NSFW. Khởi chạy Bot NSFW...")
                        reply = await self._call_nsfw_bot(messages)
                    else:
                        logger.info("Lời thoại thông thường trong kênh NSFW. Khởi chạy Fast Normal Bot trước...")
                        try:
                            resp = await fast_llm_client.try_ultra_fast_external_chat(
                                messages, temperature=0.78, max_tokens=750
                            )
                            if not resp:
                                resp = await groq_client.chat_completion(messages, temperature=0.78, max_tokens=750)
                            if is_ai_refusal(resp):
                                logger.warning("Bot Thường từ chối an toàn. Tự động chuyển sang Bot NSFW...")
                                reply = await self._call_nsfw_bot(messages)
                            else:
                                reply = resp
                        except Exception as e_groq:
                            logger.warning(f"Bot Thường gặp lỗi ({e_groq}). Tự động chuyển sang Bot NSFW...")
                            reply = await self._call_nsfw_bot(messages)
                else:
                    # Kênh thông thường: Ưu tiên Ultra-Fast API (Cerebras/SambaNova nếu có) -> Groq LPU -> Gemini Flash-Lite
                    reply = await fast_llm_client.try_ultra_fast_external_chat(
                        messages, temperature=0.78, max_tokens=750
                    )
                    if not reply:
                        try:
                            reply = await groq_client.chat_completion(messages, temperature=0.78, max_tokens=750)
                        except Exception as e_groq_normal:
                            if fast_llm_client.has_gemini:
                                logger.warning(f"Groq lỗi ({e_groq_normal}), chuyển tức thì sang Gemini Flash-Lite...")
                                reply = await fast_llm_client.chat_gemini_fast(
                                    messages, temperature=0.78, max_tokens=750
                                )
                            else:
                                raise e_groq_normal
            except Exception as e:
                logger.warning(f"Lỗi khi gọi LLM chính ({e}), thử dự phòng qua AI Horde Text...")
                try:
                    from src.llm.horde_client import horde_client
                    if horde_client.is_available():
                        reply = await horde_client.chat(messages, max_tokens=400, temperature=0.8)
                    else:
                        raise e
                except Exception as e2:
                    logger.error(f"Tất cả LLM đều thất bại: {e2}")
                    reply = "Mạng ma thuật bên ta vừa lag nhẹ một nhịp, cậu nhắn lại giúp ta nhé 😅"

        # 6.4 Khiên tự phục hồi (Self-Healing Guard): Nếu model rơi vào vòng lặp lặp câu hoặc tự mâu thuẫn, tự động tạo lại câu trả lời sạch & dứt khoát!
        if not image_data and reply and has_degenerative_loop_or_contradiction(reply):
            logger.warning("⚠️ Phát hiện LLM sinh văn bản bị lặp vòng / tự mâu thuẫn! Đang tự động tái tạo câu trả lời dứt khoát...")
            heal_messages = [
                {
                    "role": "system",
                    "content": (
                        full_system_prompt
                        + "\n\n[CHỈ THỊ KHẨN CẤP]: Trả lời cực kỳ ngắn gọn (1 đến 3 câu), dứt khoát, mạch lạc. "
                        "TUYỆT ĐỐI KHÔNG tự sửa lưng ('không, sai rồi', 'không, ta đang đùa'), KHÔNG lặp lại câu."
                    ),
                },
                *history_messages[-4:],
                {"role": "user", "content": effective_user_prompt},
            ]
            try:
                if fast_llm_client.has_gemini:
                    healed = await fast_llm_client.chat_gemini_fast(heal_messages, temperature=0.35, max_tokens=350)
                else:
                    healed = await groq_client.chat_completion(heal_messages, temperature=0.35, max_tokens=350)
                if healed and not has_degenerative_loop_or_contradiction(healed):
                    reply = healed
            except Exception as heal_err:
                logger.warning(f"Tái tạo câu trả lời anti-loop lỗi nhẹ ({heal_err}), áp dụng bộ cắt lọc trực tiếp.")

        # 6.5 Làm sạch phản hồi & đồng bộ Custom Emoji từ server 1169588792064217159 (bảo toàn khối ```code```)
        reply = sanitize_neneka_reply(reply)
        reply = emoji_manager.resolve_emojis_in_reply(reply, self.bot, current_guild_id=guild_id)

        # 7. Cộng điểm Bond và cập nhật Ký ức song song (giảm độ trễ ghi DB)
        if image_data:
            record_user_msg = f"[Hình ảnh/GIF] {user_message}"
        elif code_files:
            fnames = ", ".join(c["filename"] for c in code_files)
            record_user_msg = f"[File Code: {fnames}] {user_message}"
        else:
            record_user_msg = user_message

        await asyncio.gather(
            bond_engine.add_bond_points(discord_user_id, points=2, event_type="CONVERSATION"),
            memory_engine.record_exchange(
                discord_user_id=discord_user_id,
                username=username,
                channel_id=channel_id,
                user_message=record_user_msg,
                bot_response=reply,
                guild_id=guild_id,
            ),
        )

        return reply

    # =========================================================================
    # SLASH COMMANDS
    # =========================================================================
    @app_commands.command(name="chat", description="💬 Trò chuyện trực tiếp với Thất Vương Neneka")
    @app_commands.describe(message="Lời nhắn bạn muốn gửi tới Neneka")
    async def cmd_chat(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer()
        reply = await self._generate_neneka_reply(
            user_message=message,
            discord_user_id=str(interaction.user.id),
            username=interaction.user.display_name,
            guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            channel_id=str(interaction.channel_id)
        )
        await interaction.followup.send(reply)

    @app_commands.command(name="vision", description="👁️ Gửi ảnh để Neneka quan sát và đưa ra nhận xét sắc sảo của Thất Vương")
    @app_commands.describe(
        image="Tệp hình ảnh cần Neneka quan sát (PNG, JPG, WebP, GIF)",
        prompt="Câu hỏi hoặc yêu cầu thêm về bức ảnh (tùy chọn)"
    )
    async def cmd_vision(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        prompt: Optional[str] = None
    ):
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.response.send_message("❌ Tệp đính kèm phải là hình ảnh (PNG, JPG, WebP, GIF)!", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            img_bytes = await image.read()
        except Exception as e:
            await interaction.followup.send("❌ Không thể đọc tệp hình ảnh. Vui lòng thử lại sau.")
            return

        user_prompt = prompt or "Hãy quan sát kỹ bức ảnh này và nhận xét chi tiết theo phong thái Thất Vương Neneka."
        reply = await self._generate_neneka_reply(
            user_message=user_prompt,
            discord_user_id=str(interaction.user.id),
            username=interaction.user.display_name,
            guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            channel_id=str(interaction.channel_id),
            image_data=(img_bytes, image.content_type)
        )
        await interaction.followup.send(reply)

    @app_commands.command(name="time", description="🕒 Xem thời gian thực tế tại Việt Nam (UTC+7) qua nhận thức của Neneka")
    async def cmd_time(self, interaction: discord.Interaction):
        time_info = get_vietnam_time_info()
        embed = discord.Embed(
            title="🕒 Thời Gian Thực Tế • Việt Nam (UTC+7)",
            description=f"*{time_info['greeting']}, {interaction.user.display_name}!*",
            color=0x9b59b6
        )
        embed.add_field(name="⏰ Giờ Hiện Tại", value=f"**{time_info['time_str']}** (UTC+7)", inline=True)
        embed.add_field(name="📅 Ngày & Thứ", value=f"**{time_info['day_of_week']}**, {time_info['date_str']}", inline=True)
        embed.add_field(name="🌅 Buổi", value=f"**{time_info['period'].capitalize()}**", inline=True)
        embed.add_field(name="💜 Lời Dặn Của Thất Vương", value=f"*{time_info['care_tip']}*", inline=False)
        embed.set_footer(text="Seven Crowns Real-Time Chronometer • Princess Connect! Re:Dive")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="weather", description="🌤️ Tra cứu thời tiết thực tế hôm nay tại Việt Nam qua nhận thức của Neneka")
    @app_commands.describe(location="Tên thành phố (Hà Nội, Sài Gòn, Đà Nẵng, Đà Lạt, Nha Trang, Hải Phòng, Cần Thơ...)")
    async def cmd_weather(self, interaction: discord.Interaction, location: Optional[str] = None):
        await interaction.response.defer()
        user_loc = await memory_engine.get_user_location(str(interaction.user.id))
        target_loc = location or user_loc
        if not target_loc:
            await interaction.followup.send(
                "Fufu... Cậu chưa cho ta biết cậu đang sinh sống ở thành phố nào tại Việt Nam cả.\n"
                "Cậu có thể dùng lệnh `/location <thành_phố>` (ví dụ: `/location Sài Gòn`) để ta ghi nhớ, "
                "hoặc hỏi kèm tên thành phố như `/weather sài gòn` nhé."
            )
            return

        time_info = get_vietnam_time_info()
        weather_list = await get_vietnam_weather_info(city_query=location, user_location=user_loc)
        if not weather_list:
            await interaction.followup.send(
                f"Fufu... Ta chưa đo lường được dữ liệu thời tiết cho '{target_loc}'. "
                "Cậu hãy thử tra cứu các tỉnh thành như Hà Nội, Sài Gòn, Đà Nẵng, Đà Lạt, Cần Thơ, Hải Phòng, Bình Dương, Đồng Nai... xem sao nhé."
            )
            return

        embed = discord.Embed(
            title=f"🌤️ Thời Tiết Thực Tế • Việt Nam ({time_info['time_str']} - {time_info['day_of_week']})",
            description="*Dữ liệu đo đạc khí tượng vệ tinh thời gian thực:*",
            color=0x3498db
        )
        for w in weather_list:
            rain_text = f" | 🌧️ Mưa: `{w['rain_mm']} mm`" if w.get('rain_mm', 0) > 0 else ""
            val = (
                f"**{w['weather_desc']}**\n"
                f"🌡️ Nhiệt độ: **{w['temperature']}°C** *(cảm giác như {w['apparent_temperature']}°C)*\n"
                f"💧 Độ ẩm: `{w['humidity']}%` | 💨 Gió: `{w['wind_speed_kmh']} km/h`{rain_text}"
            )
            embed.add_field(name=f"📍 {w['city_name']}", value=val, inline=False)

        comment_prompt = (
            f"Dữ liệu thời tiết hiện tại: {weather_list[0]['city_name']} {weather_list[0]['temperature']}°C, {weather_list[0]['weather_desc']}. "
            f"Thời gian: {time_info['formatted_summary']}. "
            "Đưa ra 1 câu nhận xét/nhắc nhở ngắn gọn, tao nhã, quan tâm chu đáo theo phong thái Thất Vương Neneka."
        )
        try:
            comment = await groq_client.chat_completion([{"role": "user", "content": comment_prompt}], max_tokens=100)
        except Exception:
            comment = "Fufu... Dù thời tiết thế nào thì cậu cũng nhớ chăm sóc bản thân thật tốt nhé."

        embed.add_field(name="💜 Nhận Xét Của Neneka", value=f"*{comment.strip()}*", inline=False)
        embed.set_footer(text="Open-Meteo Real-Time Weather • Seven Crowns Intelligence")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="model", description="🤖 Kiểm tra các mô hình AI (Bot Thường & Bot NSFW) đang chạy")
    async def cmd_model(self, interaction: discord.Interaction):
        ch_id = getattr(interaction.channel, "id", 0)
        is_nsfw = False
        if settings.NSFW_ENABLED:
            if (
                (hasattr(interaction.channel, "is_nsfw") and interaction.channel.is_nsfw()) or
                ch_id in settings.nsfw_channel_id_list or
                ch_id in _nsfw_runtime_channels
            ):
                is_nsfw = True
        embed = build_model_status_embed(is_channel_nsfw=is_nsfw)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="model", aliases=["models", "botstatus"])
    async def cmd_model_prefix(self, ctx: commands.Context):
        """Kiểm tra các mô hình AI đang chạy qua !n model."""
        ch_id = getattr(ctx.channel, "id", 0)
        is_nsfw = False
        if settings.NSFW_ENABLED:
            if (
                (hasattr(ctx.channel, "is_nsfw") and ctx.channel.is_nsfw()) or
                ch_id in settings.nsfw_channel_id_list or
                ch_id in _nsfw_runtime_channels
            ):
                is_nsfw = True
        embed = build_model_status_embed(is_channel_nsfw=is_nsfw)
        await ctx.reply(embed=embed)

    @app_commands.command(name="code", description="💻 Nhờ Neneka viết code, đọc file code đính kèm hoặc sửa lỗi (Free & Fast)")
    @app_commands.describe(
        prompt="Yêu cầu viết code, sửa bug hoặc câu hỏi về lập trình",
        file="Đính kèm file code (.py, .js, .ts, .html, .cpp, .json, .txt...) nếu cần Neneka đọc"
    )
    async def cmd_code(
        self,
        interaction: discord.Interaction,
        prompt: str,
        file: Optional[discord.Attachment] = None,
    ):
        await interaction.response.defer()
        code_files = []
        if file:
            from src.utils.media_extractor import get_code_language_for_filename, decode_code_bytes
            lang = get_code_language_for_filename(file.filename, file.content_type) or "text"
            raw = await file.read()
            code_files.append({
                "filename": file.filename,
                "language": lang,
                "content": decode_code_bytes(raw[:45_000]).strip(),
                "truncated": "true" if len(raw) > 45_000 else "",
            })

        reply = await self._generate_neneka_reply(
            user_message=f"[Yêu cầu Code] {prompt}",
            discord_user_id=str(interaction.user.id),
            username=interaction.user.display_name,
            guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            channel_id=str(interaction.channel_id),
            code_files=code_files,
        )
        await self._send_smart_chunks(interaction.followup.send, reply)

    @commands.command(name="code", aliases=["vietcode", "doccode", "fixcode", "debug"])
    async def cmd_code_prefix(self, ctx: commands.Context, *, prompt: Optional[str] = None):
        """Viết code, đọc file code đính kèm hoặc debug nhanh (!n code <yêu cầu>)."""
        code_files = await extract_code_attachments(ctx.message)
        if not prompt and not code_files:
            await ctx.reply("Cậu gửi kèm file code hoặc mô tả bài toán cần viết/sửa nhé, ví dụ: `!n code viết hàm sắp xếp nhanh bằng Python` 💻")
            return
        async with ctx.typing():
            reply = await self._generate_neneka_reply(
                user_message=f"[Yêu cầu Code] {prompt or 'Hãy đọc và phân tích file code đính kèm này.'}",
                discord_user_id=str(ctx.author.id),
                username=ctx.author.display_name,
                guild_id=str(ctx.guild.id) if ctx.guild else None,
                channel_id=str(ctx.channel.id),
                code_files=code_files,
            )
            await self._send_smart_chunks(ctx.reply, reply)

    def _build_emoji_status_embed(self) -> discord.Embed:
        info = emoji_manager.get_status_info(self.bot)
        if info["connected"]:
            embed = discord.Embed(
                title=f"😄 Kho Custom Emoji Server • {info['guild_name']}",
                description=(
                    f"✅ **Đã kết nối thành công** tới máy chủ nguồn emoji (`{info['guild_id']}`)!\n"
                    f"Neneka hiện có thể tự động dùng toàn bộ emoji của server này khi trò chuyện ở mọi nơi."
                ),
                color=0x2ecc71,
            )
            embed.add_field(
                name="📊 Số Lượng Emoji Đã Nạp",
                value=f"Tổng cộng: **{info['total_emojis']}** (`{info['static_count']}` tĩnh • `{info['animated_count']}` động GIF)",
                inline=False,
            )
            if info["sample_preview"]:
                embed.add_field(name="✨ Xem Trước Kho Emoji", value=info["sample_preview"], inline=False)
        else:
            invite_note = (
                f"🔗 **Bước 1:** Đảm bảo bạn có quyền thêm bot trong server {info['server_invite']} (ID: `{info['guild_id']}`).\n"
            )
            if info["bot_oauth_invite"]:
                invite_note += f"🤖 **Bước 2:** [Nhấn vào đây để mời Bot Neneka vào Server Emoji]({info['bot_oauth_invite']})\n"
            invite_note += "✨ *Ngay sau khi bot có mặt trong server đó, Discord cho phép bot dùng toàn bộ custom emoji tĩnh & động của server ở mọi kênh chat!*"
            embed = discord.Embed(
                title="😄 Trạng Thái Kết Nối Server Emoji",
                description=(
                    f"⚠️ Bot hiện **chưa có mặt** trong máy chủ nguồn `{info['guild_id']}` ({info['server_invite']}).\n"
                    f"*(Lưu ý cơ chế Discord: Tài khoản Bot không thể tự bấm link `discord.gg`, mà cần được mời vào server qua link OAuth2 bên dưới)*\n\n"
                    f"{invite_note}"
                ),
                color=0xf39c12,
            )
        embed.set_footer(text=f"Emoji Source Guild ID: {info['guild_id']}")
        return embed

    @app_commands.command(name="emojis", description="😄 Kiểm tra kho Custom Emoji từ server nguồn (1169588792064217159)")
    async def cmd_emojis(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._build_emoji_status_embed())

    @commands.command(name="emojis", aliases=["emoji", "serveremoji"])
    async def cmd_emojis_prefix(self, ctx: commands.Context):
        """Kiểm tra kết nối kho Custom Emoji từ server nguồn (!n emojis)."""
        await ctx.reply(embed=self._build_emoji_status_embed())

    @app_commands.command(name="location", description="📍 Đặt hoặc kiểm tra nơi sinh sống của bạn để Neneka cập nhật thời tiết chuẩn xác")
    @app_commands.describe(city="Tên thành phố tại Việt Nam (ví dụ: Sài Gòn, Hà Nội, Đà Nẵng, Bình Dương...) hoặc 'reset' để xóa")
    async def cmd_location(self, interaction: discord.Interaction, city: Optional[str] = None):
        user_id = str(interaction.user.id)
        if not city:
            current_loc = await memory_engine.get_user_location(user_id)
            if current_loc:
                await interaction.response.send_message(
                    f"📍 Hiện tại Neneka đang ghi nhận nơi ở của {interaction.user.mention} là: **{current_loc}**.\n"
                    "*(Dùng `/location <thành_phố>` để đổi mới hoặc `/location reset` để xóa)*"
                )
            else:
                await interaction.response.send_message(
                    f"📍 {interaction.user.mention} chưa thiết lập nơi sinh sống.\n"
                    "Hãy dùng `/location <thành_phố>` (ví dụ: `/location Sài Gòn`) để Neneka luôn nhớ và cập nhật thời tiết chuẩn xác cho cậu nhé!"
                )
            return

        if city.lower() in ["reset", "xóa", "xoa", "none", "clear"]:
            await memory_engine.set_user_location(user_id, None, interaction.user.name)
            await interaction.response.send_message("✨ Đã xóa dữ liệu nơi ở của cậu. Kể từ giờ Neneka sẽ không mặc định vị trí của cậu nữa.")
            return

        await memory_engine.set_user_location(user_id, city, interaction.user.name)
        embed = discord.Embed(
            title="📍 Đã Cập Nhật Vị Trí Của Bạn!",
            description=(
                f"✨ *nhẹ nhàng xoay quyền trượng Metamorphose, định vị dòng chảy khí tượng*\n"
                f"Fufu... Ta đã ghi nhớ rồi. Hiện tại {interaction.user.mention} đang ở **{city}** nhé.\n"
                f"Mỗi khi cậu hỏi về thời tiết hôm nay, ta sẽ tự khắc tra cứu thời tiết tại **{city}** cho cậu."
            ),
            color=0x3498db
        )
        embed.set_footer(text="Seven Crowns Real-Time Geo • Princess Connect! Re:Dive")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="status", description="👑 Xem bảng trạng thái, hảo cảm, mức độ dâm dục & hứng cảm của Neneka")
    @app_commands.describe(user="Xem bảng trạng thái gắn kết của một thành viên khác (bỏ trống để xem của bạn)")
    async def cmd_status(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        bond_info = await bond_engine.get_bond_info(str(target.id))
        st = personality_engine.state
        is_creator = bond_info.get("is_creator", False)

        if is_creator:
            embed = discord.Embed(title=f"👑 Bảng Trạng Thái - Utsushimi Neneka ({target.display_name} • ĐẤNG SÁNG TẠO)", color=0xf1c40f)
            embed.add_field(name="👑 Thân Phận Tối Cao", value=f"**{bond_info['title']}** (Điểm: **∞ / Vĩnh Cửu**)", inline=False)
            embed.add_field(name="🎭 Cảm Xúc Nội Tâm", value="`deep_reverence (Cung kính & Tôn trọng tuyệt đối)`", inline=True)
            embed.add_field(name="🛡️ Độ Tin Tưởng", value="`100% (Tuyệt đối)`", inline=True)
            embed.add_field(name="💬 Mức Hảo Cảm", value="`1000/1000 (Tối thượng)`", inline=True)
            embed.add_field(
                name="💋 Mức Độ Dâm Dục (Lust)",
                value=f"`{st.lust_bar}` • **{st.lust_description}**\n*(Sẵn sàng buông bỏ mọi phòng ngự, thuận theo mọi mong muốn của Đấng Sáng Tạo)*",
                inline=False
            )
            embed.add_field(
                name="🔥 Mức Độ Hứng Cảm (Arousal)",
                value=f"`{st.arousal_bar}` • **{st.arousal_description}**\n*(Rung động mãnh liệt trước từng ánh mắt, hơi thở và lời nói của Sheffy-sama)*",
                inline=False
            )
            embed.add_field(
                name="🗣️ Danh Xưng",
                value=f"Tiếng Việt: **\"{bond_info['salutation']}\"**\nTiếng Nhật: **「{bond_info['japanese_salutation']}」**",
                inline=False
            )
            embed.set_footer(text="Seven Crowns Reality Engine • Special Creator Privilege")
            await interaction.response.send_message(embed=embed)
            return

        if bond_info.get("is_max_bond"):
            embed = discord.Embed(title=f"💖 Bảng Trạng Thái - Utsushimi Neneka ({target.display_name} • MỐI QUAN HỆ SÂU SẮC NHẤT)", color=0xff79c6)
            embed.add_field(name="💖 Cấp Độ Gắn Kết", value=f"**Cấp 6 (TỐI THƯỢNG)**: *{bond_info['title']}* (9999 pts)", inline=False)
            embed.add_field(name="🎭 Cảm Xúc Nội Tâm", value="`affectionate_warmth (Ấm áp, Yêu thương & Tin tưởng tuyệt đối)`", inline=True)
            embed.add_field(name="🛡️ Độ Tin Tưởng", value="`100% (Tuyệt đối)`", inline=True)
            embed.add_field(name="💬 Mức Hảo Cảm", value="`1000/1000 (Tối đa)`", inline=True)
            embed.add_field(
                name="💋 Mức Độ Dâm Dục (Lust)",
                value=f"`{st.lust_bar}` • **{st.lust_description}**\n*(Khao khát thể xác nồng nàn hòa cùng tình yêu sâu sắc dành trọn cho người bạn đời)*",
                inline=False
            )
            embed.add_field(
                name="🔥 Mức Độ Hứng Cảm (Arousal)",
                value=f"`{st.arousal_bar}` • **{st.arousal_description}**\n*(Cơ thể và tâm hồn cực kỳ nhạy cảm trước từng cái chạm và lời thì thầm ngọt ngào)*",
                inline=False
            )
            embed.add_field(
                name="🗣️ Danh Xưng",
                value=f"Tiếng Việt: **\"{bond_info['salutation']}\"**\nTiếng Nhật: **「{bond_info['japanese_salutation']}」**",
                inline=False
            )
            embed.set_footer(text="Seven Crowns Reality Engine • Deepest Soulmate Bond")
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(title=f"👑 Bảng Trạng Thái - Utsushimi Neneka [{target.display_name}]", color=0x9b59b6)
        embed.add_field(name="💜 Cấp Độ Gắn Kết", value=f"**Cấp {bond_info['level']}**: *{bond_info['title']}* ({bond_info['points']} pts)", inline=False)
        embed.add_field(name="🎭 Cảm Xúc Nội Tâm", value=f"`{st.emotional_state}`", inline=True)
        embed.add_field(name="🛡️ Độ Tự Tin", value=f"`{st.confidence}%`", inline=True)
        embed.add_field(name="💬 Mức Hảo Cảm", value=f"`{st.affection}/1000`", inline=True)
        embed.add_field(
            name="💋 Mức Độ Dâm Dục (Lust)",
            value=f"`{st.lust_bar}` • **{st.lust_description}**",
            inline=False
        )
        embed.add_field(
            name="🔥 Mức Độ Hứng Cảm (Arousal)",
            value=f"`{st.arousal_bar}` • **{st.arousal_description}**",
            inline=False
        )
        embed.set_footer(text="Seven Crowns Simulation • Princess Connect! Re:Dive")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="lust", description="💋 Xem chi tiết thanh mức độ dâm dục & hứng cảm của Neneka")
    async def cmd_lust(self, interaction: discord.Interaction):
        st = personality_engine.state
        embed = discord.Embed(
            title="💋 Ma Trận Cảm Xúc Thể Xác • Utsushimi Neneka",
            description="*Phân tích phản ứng sinh lý, ham muốn thể xác và trạng thái hưng cảm của Thất Vương:*",
            color=0xe91e63
        )
        embed.add_field(
            name="💋 Mức Độ Dâm Dục (Lust / Libido)",
            value=f"**{st.lust_bar}**\nSắc thái: **{st.lust_description}**",
            inline=False
        )
        embed.add_field(
            name="🔥 Mức Độ Hứng Cảm (Arousal / Excitement)",
            value=f"**{st.arousal_bar}**\nTrạng thái cơ thể: **{st.arousal_description}**",
            inline=False
        )
        embed.add_field(
            name="🎭 Tâm Trạng Hiện Tại",
            value=f"`{st.emotional_state}`",
            inline=True
        )
        embed.add_field(
            name="💜 Mức Hảo Cảm",
            value=f"`{st.affection}/1000`",
            inline=True
        )
        embed.set_footer(text="Seven Crowns Lewdness & Arousal Monitor • Princess Connect! Re:Dive")
        await interaction.response.send_message(embed=embed)

    # =========================================================================
    # LEGACY PREFIX COMMANDS (!n, n!)
    # =========================================================================
    @commands.command(name="status", aliases=["trangthai"])
    async def pcmd_status(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Hiển thị trạng thái hảo cảm, cảm xúc nội tâm, mức độ dâm dục & hứng cảm của Neneka: !n status [@user]"""
        target = user or ctx.author
        bond_info = await bond_engine.get_bond_info(str(target.id))
        st = personality_engine.state
        is_creator = bond_info.get("is_creator", False)

        if is_creator:
            embed = discord.Embed(title=f"👑 Bảng Trạng Thái - Utsushimi Neneka ({target.display_name} • ĐẤNG SÁNG TẠO)", color=0xf1c40f)
            embed.add_field(name="👑 Thân Phận Tối Cao", value=f"**{bond_info['title']}** (Điểm: **∞ / Vĩnh Cửu**)", inline=False)
            embed.add_field(name="🎭 Cảm Xúc Nội Tâm", value="`deep_reverence (Cung kính & Tôn trọng tuyệt đối)`", inline=True)
            embed.add_field(name="🛡️ Độ Tin Tưởng", value="`100% (Tuyệt đối)`", inline=True)
            embed.add_field(name="💬 Mức Hảo Cảm", value="`1000/1000 (Tối thượng)`", inline=True)
            embed.add_field(
                name="💋 Mức Độ Dâm Dục (Lust)",
                value=f"`{st.lust_bar}` • **{st.lust_description}**\n*(Sẵn sàng buông bỏ mọi phòng ngự, thuận theo mọi mong muốn của Đấng Sáng Tạo)*",
                inline=False
            )
            embed.add_field(
                name="🔥 Mức Độ Hứng Cảm (Arousal)",
                value=f"`{st.arousal_bar}` • **{st.arousal_description}**\n*(Rung động mãnh liệt trước từng ánh mắt, hơi thở và lời nói của Sheffy-sama)*",
                inline=False
            )
            embed.add_field(
                name="🗣️ Danh Xưng",
                value=f"Tiếng Việt: **\"{bond_info['salutation']}\"**\nTiếng Nhật: **「{bond_info['japanese_salutation']}」**",
                inline=False
            )
            embed.set_footer(text="Seven Crowns Reality Engine • Special Creator Privilege")
            await ctx.reply(embed=embed)
            return

        if bond_info.get("is_max_bond"):
            embed = discord.Embed(title=f"💖 Bảng Trạng Thái - Utsushimi Neneka ({target.display_name} • MỐI QUAN HỆ SÂU SẮC NHẤT)", color=0xff79c6)
            embed.add_field(name="💖 Cấp Độ Gắn Kết", value=f"**Cấp 6 (TỐI THƯỢNG)**: *{bond_info['title']}* (9999 pts)", inline=False)
            embed.add_field(name="🎭 Cảm Xúc Nội Tâm", value="`affectionate_warmth (Ấm áp, Yêu thương & Tin tưởng tuyệt đối)`", inline=True)
            embed.add_field(name="🛡️ Độ Tin Tưởng", value="`100% (Tuyệt đối)`", inline=True)
            embed.add_field(name="💬 Mức Hảo Cảm", value="`1000/1000 (Tối đa)`", inline=True)
            embed.add_field(
                name="💋 Mức Độ Dâm Dục (Lust)",
                value=f"`{st.lust_bar}` • **{st.lust_description}**\n*(Khao khát thể xác nồng nàn hòa cùng tình yêu sâu sắc dành trọn cho người bạn đời)*",
                inline=False
            )
            embed.add_field(
                name="🔥 Mức Độ Hứng Cảm (Arousal)",
                value=f"`{st.arousal_bar}` • **{st.arousal_description}**\n*(Cơ thể và tâm hồn cực kỳ nhạy cảm trước từng cái chạm và lời thì thầm ngọt ngào)*",
                inline=False
            )
            embed.add_field(
                name="🗣️ Danh Xưng",
                value=f"Tiếng Việt: **\"{bond_info['salutation']}\"**\nTiếng Nhật: **「{bond_info['japanese_salutation']}」**",
                inline=False
            )
            embed.set_footer(text="Seven Crowns Reality Engine • Deepest Soulmate Bond")
            await ctx.reply(embed=embed)
            return

        embed = discord.Embed(title=f"👑 Bảng Trạng Thái - Utsushimi Neneka [{target.display_name}]", color=0x9b59b6)
        embed.add_field(name="💜 Cấp Độ Gắn Kết", value=f"**Cấp {bond_info['level']}**: *{bond_info['title']}* ({bond_info['points']} pts)", inline=False)
        embed.add_field(name="🎭 Cảm Xúc Nội Tâm", value=f"`{st.emotional_state}`", inline=True)
        embed.add_field(name="🛡️ Độ Tự Tin", value=f"`{st.confidence}%`", inline=True)
        embed.add_field(name="💬 Mức Hảo Cảm", value=f"`{st.affection}/1000`", inline=True)
        embed.add_field(
            name="💋 Mức Độ Dâm Dục (Lust)",
            value=f"`{st.lust_bar}` • **{st.lust_description}**",
            inline=False
        )
        embed.add_field(
            name="🔥 Mức Độ Hứng Cảm (Arousal)",
            value=f"`{st.arousal_bar}` • **{st.arousal_description}**",
            inline=False
        )
        embed.set_footer(text="Seven Crowns Simulation • Princess Connect! Re:Dive")
        await ctx.reply(embed=embed)

    @commands.command(name="lust", aliases=["lewd", "sensual", "damduc", "hungcam", "coilust", "xemlust", "checklust"])
    async def pcmd_lust(self, ctx):
        """Xem chi tiết thanh mức độ dâm dục & hứng cảm của Neneka (!n lust / !n lewd)"""
        st = personality_engine.state
        embed = discord.Embed(
            title="💋 Ma Trận Cảm Xúc Thể Xác • Utsushimi Neneka",
            description="*Phân tích phản ứng sinh lý, ham muốn thể xác và trạng thái hưng cảm của Thất Vương:*",
            color=0xe91e63
        )
        embed.add_field(
            name="💋 Mức Độ Dâm Dục (Lust / Libido)",
            value=f"**{st.lust_bar}**\nSắc thái: **{st.lust_description}**",
            inline=False
        )
        embed.add_field(
            name="🔥 Mức Độ Hứng Cảm (Arousal / Excitement)",
            value=f"**{st.arousal_bar}**\nTrạng thái cơ thể: **{st.arousal_description}**",
            inline=False
        )
        embed.add_field(
            name="🎭 Tâm Trạng Hiện Tại",
            value=f"`{st.emotional_state}`",
            inline=True
        )
        embed.add_field(
            name="💜 Mức Hảo Cảm",
            value=f"`{st.affection}/1000`",
            inline=True
        )
        embed.set_footer(text="Seven Crowns Lewdness & Arousal Monitor • Princess Connect! Re:Dive")
        await ctx.reply(embed=embed)

    @commands.command(name="gift")
    async def pcmd_gift(self, ctx, *, gift_name: str = None):
        """Tặng quà hoặc điểm tâm Landosol cho Neneka"""
        if not gift_name:
            await ctx.reply("Fufu... Cậu định tặng gì cho ta thế? Hãy dùng: `!n gift <tên món quà>` nhé.")
            return

        async with ctx.typing():
            is_creator = (str(ctx.author.id) == str(settings.CREATOR_USER_ID))
            is_max_bond = (str(ctx.author.id) in settings.max_bond_user_id_list)

            # Tăng điểm Bond và tính cảm xúc quà tặng
            lvl, pts, up = await bond_engine.add_bond_points(str(ctx.author.id), points=20, event_type="GIFT", description=f"Tặng quà: {gift_name}")
            personality_engine.update_from_interaction(gift_name, affection_delta=15, new_emotion="affectionate_warmth", is_creator=is_creator, is_max_bond=is_max_bond)

            if is_creator:
                prompt = (
                    f"ĐẤNG SÁNG TẠO CỦA NENEKA (Người tạo ra bot, ID {settings.CREATOR_USER_ID}) vừa đích thân gửi tặng Neneka món quà: '{gift_name}'. "
                    "Hãy phản hồi bằng sự cảm kích vô bờ bến, cung kính, hạnh phúc ngọt ngào và lòng trung thành tuyệt đối. "
                    "Xưng 'Ta' và gọi Người là 'Ngài' hoặc 'Người sáng tạo của ta'. Kèm hành động *...* tao nhã, nâng niu món quà trân quý."
                )
            elif is_max_bond:
                prompt = (
                    f"Người đồng hành đặc biệt nhất trong cuộc đời Neneka (ID {ctx.author.id}, gắn kết tình cảm cấp 6 tối thượng) vừa gửi tặng Neneka món quà: '{gift_name}'. "
                    "Hãy phản hồi bằng sự yêu thương, hạnh phúc ngập tràn, ngọt ngào, cảm động sâu sắc và trân trọng vô bờ bến. "
                    "Xưng 'Ta' và gọi 'Người đặc biệt nhất của ta' hoặc 'Cậu bé của ta' (hoặc 'Hiệp sĩ của ta'). Kèm cử chỉ ôm nhẹ hoặc khẽ tựa vai trong dấu *...*."
                )
            else:
                prompt = (
                    f"Người dùng vừa gửi tặng Neneka món quà: '{gift_name}'. "
                    "Hãy phản hồi bằng phong thái quý cô Thất Vương sành sỏi (fufu, khen ngợi sự chu đáo, bẻ nửa miếng bánh hoặc thưởng trà cùng cậu). "
                    "Kèm cử chỉ hành động trong dấu *...* và 2-3 câu thoại tự nhiên."
                )
            reply = await groq_client.chat_completion([{"role": "user", "content": prompt}], max_tokens=300)

            embed = discord.Embed(
                title=f"🎁 Quà Tặng Landosol: {gift_name}",
                description=reply,
                color=0xf1c40f if is_creator else (0xff79c6 if is_max_bond else 0x9b59b6)
            )
            if is_creator:
                embed.add_field(name="👑 Đặc Quyền Đấng Sáng Tạo", value="Món quà từ Đấng Sáng Tạo được Neneka trân trọng lưu giữ vĩnh cửu!", inline=False)
            elif is_max_bond:
                embed.add_field(name="💖 Tình Cảm Tối Thượng", value="Món quà từ Người Đồng Hành Đặc Biệt Nhất được Neneka ôm trọn vào lòng với tất cả tình yêu thương!", inline=False)
            else:
                embed.add_field(name="💜 Điểm Gắn Kết Nhận Được", value=f"+20 điểm (Tổng: **{pts}** pts - Cấp {lvl})", inline=False)
                if up:
                    embed.add_field(name="🎉 THĂNG CẤP BOND!", value=f"Chúc mừng! Cậu vừa đạt tới **Cấp {up}** trong quan hệ với Neneka!", inline=False)

            await ctx.reply(embed=embed)

    @commands.command(name="time")
    async def pcmd_time(self, ctx):
        """Xem thời gian thực tế tại Việt Nam (UTC+7)"""
        time_info = get_vietnam_time_info()
        embed = discord.Embed(
            title="🕒 Thời Gian Thực Tế • Việt Nam (UTC+7)",
            description=f"*{time_info['greeting']}, {ctx.author.display_name}!*",
            color=0x9b59b6
        )
        embed.add_field(name="⏰ Giờ Hiện Tại", value=f"**{time_info['time_str']}** (UTC+7)", inline=True)
        embed.add_field(name="📅 Ngày & Thứ", value=f"**{time_info['day_of_week']}**, {time_info['date_str']}", inline=True)
        embed.add_field(name="🌅 Buổi", value=f"**{time_info['period'].capitalize()}**", inline=True)
        embed.add_field(name="💜 Lời Dặn Của Thất Vương", value=f"*{time_info['care_tip']}*", inline=False)
        embed.set_footer(text="Seven Crowns Real-Time Chronometer • Princess Connect! Re:Dive")
        await ctx.reply(embed=embed)

    @commands.command(name="location", aliases=["vitri", "noio"])
    async def pcmd_location(self, ctx, *, city: Optional[str] = None):
        """Đặt hoặc kiểm tra nơi sinh sống tại Việt Nam (!n location <thành phố> / !n location reset)"""
        user_id = str(ctx.author.id)
        if not city:
            current_loc = await memory_engine.get_user_location(user_id)
            if current_loc:
                await ctx.reply(
                    f"📍 Hiện tại Neneka đang ghi nhận nơi ở của cậu là: **{current_loc}**.\n"
                    "*(Dùng `!n location <thành phố>` để đổi mới hoặc `!n location reset` để xóa)*"
                )
            else:
                await ctx.reply(
                    "📍 Cậu chưa thiết lập nơi sinh sống.\n"
                    "Hãy dùng `!n location <thành phố>` (ví dụ: `!n location Sài Gòn` hoặc nói tự nhiên *'mình đang ở Sài Gòn'*) để Neneka luôn nhớ và cập nhật thời tiết chuẩn xác nhé!"
                )
            return

        if city.lower() in ["reset", "xóa", "xoa", "none", "clear"]:
            await memory_engine.set_user_location(user_id, None, ctx.author.name)
            await ctx.reply("✨ Đã xóa dữ liệu nơi ở. Kể từ giờ Neneka sẽ không tự ý mặc định vị trí của cậu nữa.")
            return

        await memory_engine.set_user_location(user_id, city, ctx.author.name)
        embed = discord.Embed(
            title="📍 Đã Cập Nhật Vị Trí Của Bạn!",
            description=(
                f"✨ *nhẹ nhàng xoay quyền trượng Metamorphose, định vị dòng chảy khí tượng*\n"
                f"Fufu... Ta đã ghi nhớ rồi. Hiện tại cậu đang ở **{city}** nhé.\n"
                f"Mỗi khi cậu hỏi về thời tiết hôm nay, ta sẽ tự khắc đo lường khí hậu tại **{city}** cho cậu."
            ),
            color=0x3498db
        )
        embed.set_footer(text="Seven Crowns Real-Time Geo • Princess Connect! Re:Dive")
        await ctx.reply(embed=embed)

    @commands.command(name="weather")
    async def pcmd_weather(self, ctx, *, location: Optional[str] = None):
        """Tra cứu thời tiết thực tế hôm nay tại Việt Nam"""
        async with ctx.typing():
            user_loc = await memory_engine.get_user_location(str(ctx.author.id))
            target_loc = location or user_loc
            if not target_loc:
                await ctx.reply(
                    "Fufu... Cậu chưa cho ta biết cậu đang sinh sống ở thành phố nào tại Việt Nam cả.\n"
                    "Cậu có thể dùng lệnh `!n location <thành phố>` (hoặc nói tự nhiên *'mình ở Sài Gòn'*), "
                    "hoặc gõ kèm tên nơi cần xem như `!n weather đà lạt` nhé."
                )
                return

            time_info = get_vietnam_time_info()
            weather_list = await get_vietnam_weather_info(city_query=location, user_location=user_loc)
            if not weather_list:
                await ctx.reply(
                    f"Fufu... Ta chưa đo lường được dữ liệu thời tiết cho '{target_loc}'. "
                    "Cậu hãy thử tra cứu các tỉnh thành như Hà Nội, Sài Gòn, Đà Nẵng, Đà Lạt, Cần Thơ, Hải Phòng, Bình Dương, Đồng Nai... xem sao nhé."
                )
                return

            embed = discord.Embed(
                title=f"🌤️ Thời Tiết Thực Tế • Việt Nam ({time_info['time_str']} - {time_info['day_of_week']})",
                description="*Dữ liệu đo đạc khí tượng vệ tinh thời gian thực:*",
                color=0x3498db
            )
            for w in weather_list:
                rain_text = f" | 🌧️ Mưa: `{w['rain_mm']} mm`" if w.get('rain_mm', 0) > 0 else ""
                val = (
                    f"**{w['weather_desc']}**\n"
                    f"🌡️ Nhiệt độ: **{w['temperature']}°C** *(cảm giác như {w['apparent_temperature']}°C)*\n"
                    f"💧 Độ ẩm: `{w['humidity']}%` | 💨 Gió: `{w['wind_speed_kmh']} km/h`{rain_text}"
                )
                embed.add_field(name=f"📍 {w['city_name']}", value=val, inline=False)

            comment_prompt = (
                f"Dữ liệu thời tiết hiện tại: {weather_list[0]['city_name']} {weather_list[0]['temperature']}°C, {weather_list[0]['weather_desc']}. "
                f"Thời gian: {time_info['formatted_summary']}. "
                "Đưa ra 1 câu nhận xét/nhắc nhở ngắn gọn, tao nhã, quan tâm chu đáo theo phong thái Thất Vương Neneka."
            )
            try:
                comment = await groq_client.chat_completion([{"role": "user", "content": comment_prompt}], max_tokens=100)
            except Exception:
                comment = "Fufu... Dù thời tiết thế nào thì cậu cũng nhớ chăm sóc bản thân thật tốt nhé."

            embed.add_field(name="💜 Nhận Xét Của Neneka", value=f"*{comment.strip()}*", inline=False)
            embed.set_footer(text="Open-Meteo Real-Time Weather • Seven Crowns Intelligence")
            await ctx.reply(embed=embed)

    @commands.command(name="vision", aliases=["xemanh", "soianh", "look"])
    async def pcmd_vision(self, ctx, *, prompt: Optional[str] = None):
        """Quan sát và nhận xét hình ảnh đính kèm (!n vision [câu hỏi])"""
        image_att = None
        if ctx.message.attachments:
            for att in ctx.message.attachments:
                if att.content_type and att.content_type.startswith("image/"):
                    image_att = att
                    break

        if not image_att:
            await ctx.reply("Fufu... Cậu cần đính kèm một bức ảnh cùng với lệnh này để ta quan sát nhé.")
            return

        async with ctx.typing():
            try:
                img_bytes = await image_att.read()
            except Exception:
                await ctx.reply("❌ Không thể đọc file ảnh vừa gửi.")
                return

            user_prompt = prompt or "Hãy quan sát kỹ bức ảnh này và nhận xét chi tiết theo phong thái Thất Vương Neneka."
            reply = await self._generate_neneka_reply(
                user_message=user_prompt,
                discord_user_id=str(ctx.author.id),
                username=ctx.author.display_name,
                guild_id=str(ctx.guild.id) if ctx.guild else None,
                channel_id=str(ctx.channel.id),
                image_data=(img_bytes, image_att.content_type)
            )
            await ctx.reply(reply)

    @app_commands.command(name="updates", description="✨ Xem danh sách các tính năng mới vừa cập nhật cho Neneka Bot (kèm nút dùng thử)")
    async def cmd_updates(self, interaction: discord.Interaction):
        gid = str(interaction.guild_id) if interaction.guild_id else None
        await interaction.response.send_message(
            content=build_spoken_whats_new_reply(self.bot, current_guild_id=gid),
            embed=build_updates_embed(),
            view=UpdatesInteractiveView(self.bot),
        )

    @commands.command(name="updates", aliases=["capnhat", "tinhnangmoi", "changelog", "new"])
    async def pcmd_updates(self, ctx: commands.Context):
        """Xem toàn bộ các tính năng mới vừa cập nhật (!n updates / !n tinhnangmoi)."""
        gid = str(ctx.guild.id) if ctx.guild else None
        await ctx.reply(
            content=build_spoken_whats_new_reply(self.bot, current_guild_id=gid),
            embed=build_updates_embed(),
            view=UpdatesInteractiveView(self.bot),
        )

    @app_commands.command(name="help", description="📖 Mở cẩm nang hướng dẫn toàn bộ lệnh và tính năng của Neneka")
    async def cmd_help_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=build_help_embed("all"),
            view=HelpCategoryView(),
        )

    @commands.command(name="help", aliases=["menu", "commands", "tinhnang"])
    async def pcmd_help(self, ctx):
        """Hiển thị cẩm nang hướng dẫn lệnh phân mục tương tác"""
        await ctx.reply(embed=build_help_embed("all"), view=HelpCategoryView())

    # =========================================================================
    # ON_MESSAGE EVENT ROUTING
    # =========================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. BẮT BUỘC: Không để bot trả lời chính tin nhắn của nó hoặc bot khác
        if message.author.bot:
            return

        # 2. BẮT BUỘC: Bỏ qua tin nhắn lệnh để tránh bot thực thi 2 lần
        # (discord.py commands.Bot mặc định đã tự động gọi process_commands trong on_message chính)
        if message.content.startswith(("!n", "n!")):
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # 3. Kiểm tra điều kiện kích hoạt phản hồi & tệp đính kèm hình ảnh
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.bot.user in message.mentions
        is_reply_to_bot = (
            message.reference is not None and
            isinstance(message.reference.resolved, discord.Message) and
            message.reference.resolved.author.id == self.bot.user.id
        )

        has_media_or_code = message_has_media_or_code(message)
        clean_content = message.clean_content.replace(f"@{self.bot.user.name}", "").strip()

        should, reason = proactive_engine.should_reply(
            is_bot=message.author.bot,
            is_dm=is_dm,
            is_mentioned=is_mentioned,
            is_reply_to_bot=is_reply_to_bot,
            channel_id=message.channel.id,
            content=clean_content,
            has_attachments=has_media_or_code
        )

        if not should:
            return

        # 4. Kiểm tra Rate Limit & Cooldown
        allowed, rl_reason = await proactive_engine.check_rate_limit(message.channel.id, message.author.id)
        if not allowed:
            logger.debug(f"Rate limited message from {message.author.id}: {rl_reason}")
            return

        # 5. Kiểm tra nếu có yêu cầu đặt biệt danh tự nhiên trong đoạn chat
        nick_match = re.search(r'(?:từ giờ\s+)?(?:hãy\s+)?(?:đặt biệt danh cho|gọi)\s+(.+?)\s+là\s+([^\n.,!?;]+)', clean_content, re.IGNORECASE)
        if nick_match:
            raw_target = nick_match.group(1).strip()
            new_nick = nick_match.group(2).strip().strip("'\"")

            target_user = None
            if message.mentions:
                for m in message.mentions:
                    if f"<@{m.id}>" in raw_target or f"<@!{m.id}>" in raw_target or m.name.lower() in raw_target.lower() or m.display_name.lower() in raw_target.lower():
                        target_user = m
                        break
                if not target_user and message.mentions:
                    target_user = message.mentions[0]

            if not target_user:
                if any(self_ref in raw_target.lower() for self_ref in ["tôi", "mình", "ta", "anh", "em", "bản thân", "tao"]):
                    target_user = message.author

            if target_user and new_nick:
                await memory_engine.set_preferred_name(str(target_user.id), new_nick, target_user.name)
                embed = discord.Embed(
                    title="🏷️ Đã Ghi Nhận Biệt Danh Mới!",
                    description=(
                        f"✨ *khẽ mỉm cười, ghi nhận biến số mới vào quyền trượng Metamorphose*\n"
                        f"Fufu... Được thôi. Kể từ giờ ta sẽ gọi {target_user.mention} là **'{new_nick}'** nhé."
                    ),
                    color=0x9b59b6
                )
                embed.set_footer(text="Seven Crowns Identity Registry • Princess Connect! Re:Dive")
                await message.reply(embed=embed)
                return

        # 5.5 Kiểm tra nếu người dùng nói về nơi ở tự nhiên trong đoạn chat
        loc_match = re.search(
            r'(?:tôi|mình|ta|anh|em|nhà tôi|nhà mình|hiện tại)\s+(?:đang\s+)?(?:ở|sống tại|sinh sống tại|ở tại)\s+([^\n.,!?;]+)',
            clean_content,
            re.IGNORECASE
        )
        if loc_match:
            candidate_city = loc_match.group(1).strip().strip("'\"")
            detected_city_key = detect_city_from_query(candidate_city)
            if detected_city_key and detected_city_key in CITIES_VN:
                resolved_name = CITIES_VN[detected_city_key][2]
                await memory_engine.set_user_location(str(message.author.id), resolved_name, message.author.name)
                embed = discord.Embed(
                    title="📍 Đã Ghi Nhận Nơi Ở Của Cậu!",
                    description=(
                        f"✨ *mỉm cười quan sát, đánh dấu vào tấm bản đồ không gian của Thất Vương*\n"
                        f"Fufu... Ta đã ghi nhận rồi. Hiện tại {message.author.mention} đang ở **{resolved_name}** đúng không?\n"
                        f"Từ giờ khi cậu hỏi thời tiết hôm nay, ta sẽ tự khắc tra cứu chính xác cho vùng đất này nhé."
                    ),
                    color=0x3498db
                )
                embed.set_footer(text="Seven Crowns Real-Time Geo • Princess Connect! Re:Dive")
                await message.reply(embed=embed)
                return

        # 5.8 Kiểm tra nếu người dùng yêu cầu tạo âm tiết / đánh nốt nhạc hoặc tìm/chơi bài nhạc tiếng Piano tự nhiên
        note_match = re.search(
            r"(?:tạo\s+âm\s+tiết|đánh\s+nốt|gảy\s+nốt|chơi\s+nốt|đàn\s+nốt|cảm\s+âm\s+piano)\s*[:\-]?\s*(.+)",
            clean_content,
            re.IGNORECASE,
        )
        if note_match:
            voice_cog = self.bot.get_cog("VoiceCog")
            if voice_cog:
                async with message.channel.typing():
                    gid = await voice_cog._auto_join_user_voice(message.guild, message.author)
                    audio_path, fname, p_embed, p_view = await voice_cog.handle_piano_notes(
                        note_match.group(1).strip(), tempo=108, guild_id=gid
                    )
                    reply_kwargs = {"embed": p_embed}
                    if audio_path and os.path.exists(audio_path):
                        reply_kwargs["file"] = discord.File(audio_path, filename=fname)
                    if p_view:
                        reply_kwargs["view"] = p_view
                    await message.reply(**reply_kwargs)
                    return

        piano_search_match = re.search(
            r"(?:tìm\s+(?:kiếm\s+)?(?:bài\s+)?(?:nhạc\s+)?(?:game\s+)?(?:tiếng\s+)?piano|mở\s+(?:bài\s+)?(?:nhạc\s+)?piano|phát\s+(?:bài\s+)?(?:nhạc\s+)?piano|bật\s+(?:nhạc\s+)?piano|(?:đánh|gảy|chơi|dạo)\s+(?:đàn\s+|bản\s+|bài\s+)?piano(?:\s+bài|\s+game)?|độc\s+tấu\s+piano(?:\s+bài)?|nhạc\s+piano\s+(?:game|bài))\s*[:\-]?\s*(.*)",
            clean_content,
            re.IGNORECASE,
        )
        if piano_search_match:
            voice_cog = self.bot.get_cog("VoiceCog")
            if voice_cog:
                async with message.channel.typing():
                    gid = await voice_cog._auto_join_user_voice(message.guild, message.author)
                    raw_q = piano_search_match.group(1).strip() or "River Flows in You"
                    audio_path, fname, p_embed, p_view = await voice_cog.handle_piano_search(raw_q, guild_id=gid)
                    reply_kwargs = {"embed": p_embed}
                    if audio_path and os.path.exists(audio_path):
                        reply_kwargs["file"] = discord.File(audio_path, filename=fname)
                    if p_view:
                        reply_kwargs["view"] = p_view
                    await message.reply(**reply_kwargs)
                    return

        # 6. Kiểm tra nếu người dùng yêu cầu Neneka hát trong hội thoại tự nhiên
        if is_singing_request(clean_content):
            async with message.channel.typing():
                voice_cog = self.bot.get_cog("VoiceCog")
                if voice_cog:
                    guild_id = message.guild.id if message.guild else None
                    if message.guild and message.author.voice and message.author.voice.channel:
                        vc = voice_channel_mgr.get_voice_client(guild_id)
                        if not vc or not vc.is_connected():
                            await voice_channel_mgr.join_channel(message.author.voice.channel)

                    audio_file, song = await voice_cog._handle_sing(theme=clean_content, guild_id=guild_id)
                    if audio_file:
                        embed = create_song_embed(song)
                        discord_file = discord.File(audio_file, filename="neneka_singing.mp3")
                        await message.reply(embed=embed, file=discord_file)
                        return

        # 7. Kiểm tra nếu người dùng yêu cầu gieo quẻ vận mệnh tự nhiên
        if any(term in clean_content.lower() for term in ["gieo quẻ", "bói quẻ", "xem vận mệnh", "bói cho mình", "bói hôm nay", "quẻ hôm nay"]):
            ent_cog = self.bot.get_cog("EntertainmentCog")
            if ent_cog:
                await ent_cog._handle_fortune(message.author, message.reply)
                return

        # 8. Kiểm tra nếu người dùng yêu cầu ru ngủ tự nhiên
        if any(term in clean_content.lower() for term in ["ru ngủ", "ru mình ngủ", "hát ru", "chúc ngủ ngon", "buồn ngủ quá", "ngủ đây", "đi ngủ đây"]):
            async with message.channel.typing():
                from src.voice.sleep_manager import sleep_manager
                embed, audio_file, note = await sleep_manager.execute_sleep(message.author, theme=clean_content, guild=message.guild)
                if note:
                    embed.description = f"{note}\n\n{embed.description}"
                if audio_file:
                    discord_file = discord.File(audio_file, filename="neneka_lullaby.mp3")
                    await message.reply(embed=embed, file=discord_file)
                else:
                    await message.reply(embed=embed)
                return

        # 9. Kiểm tra nếu người dùng muốn chơi gương ảo ảnh tự nhiên
        if any(term in clean_content.lower() for term in ["chơi gương ảo ảnh", "chơi phân thân", "đố vui phân thân", "chơi game cùng neneka"]):
            from src.entertainment.mirror_game import start_mirror_game
            embed, view, err = start_mirror_game(str(message.author.id), bond_engine)
            if err:
                await message.reply(err)
            else:
                await message.reply(embed=embed, view=view)
            return

        # 9.5 Kiểm tra nếu người dùng yêu cầu xem Lust / Arousal tự nhiên
        lust_triggers = [
            "coi lust", "kiểm tra lust", "xem lust", "check lust", "coi lewd",
            "xem dâm dục", "kiểm tra dâm dục", "mức độ dâm dục", "chỉ số dâm dục",
            "xem hứng cảm", "kiểm tra hứng cảm", "mức độ hứng cảm", "chỉ số hứng cảm"
        ]
        if any(term in clean_content.lower() for term in lust_triggers):
            st = personality_engine.state
            embed = discord.Embed(
                title="💋 Ma Trận Cảm Xúc Thể Xác • Utsushimi Neneka",
                description="*Phân tích phản ứng sinh lý, ham muốn thể xác và trạng thái hưng cảm của Thất Vương:*",
                color=0xe91e63
            )
            embed.add_field(
                name="💋 Mức Độ Dâm Dục (Lust / Libido)",
                value=f"**{st.lust_bar}**\nSắc thái: **{st.lust_description}**",
                inline=False
            )
            embed.add_field(
                name="🔥 Mức Độ Hứng Cảm (Arousal / Excitement)",
                value=f"**{st.arousal_bar}**\nTrạng thái cơ thể: **{st.arousal_description}**",
                inline=False
            )
            embed.add_field(
                name="🎭 Tâm Trạng Hiện Tại",
                value=f"`{st.emotional_state}`",
                inline=True
            )
            embed.add_field(
                name="💜 Mức Hảo Cảm",
                value=f"`{st.affection}/1000`",
                inline=True
            )
            embed.set_footer(text="Seven Crowns Lewdness & Arousal Monitor • Princess Connect! Re:Dive")
            await message.reply(embed=embed)
            return

        # 9.6 Kiểm tra nếu người dùng yêu cầu xem Bond / Hảo cảm tự nhiên (cho mình hoặc người khác)
        bond_triggers = [
            "coi bond", "kiểm tra bond", "xem bond", "check bond", "điểm bond",
            "xem hảo cảm", "coi hảo cảm", "kiểm tra hảo cảm", "điểm hảo cảm", "cấp độ gắn kết"
        ]
        if any(term in clean_content.lower() for term in bond_triggers):
            target = message.author
            if message.mentions:
                for m in message.mentions:
                    if m.id != self.bot.user.id:
                        target = m
                        break
            from src.cogs.bond import build_bond_embed
            info = await bond_engine.get_bond_info(str(target.id))
            embed = build_bond_embed(target, info)
            await message.reply(embed=embed)
            return

        # 9.7 Kiểm tra nếu người dùng yêu cầu quên tin nhắn tự nhiên (30 phút, 1 tiếng, toàn bộ)
        forget_phrases = ["quên tin nhắn", "xóa tin nhắn", "forget tin nhắn", "quên 30 phút", "quên 1 tiếng", "quên 30p", "quên 1h", "quên 30m"]
        if any(term in clean_content.lower() for term in forget_phrases):
            lower_msg = clean_content.lower()
            from src.cogs.memory import parse_timeframe_to_minutes, build_forget_embed
            mins = parse_timeframe_to_minutes(lower_msg)
            if mins == -1:
                res = await memory_engine.forget_recent_messages(str(message.author.id), minutes=None)
                time_label = "toàn bộ lịch sử tin nhắn"
            elif mins is not None:
                res = await memory_engine.forget_recent_messages(str(message.author.id), minutes=mins)
                time_label = f"{mins} phút" if mins < 60 else f"{mins // 60} tiếng"
            else:
                res = await memory_engine.forget_recent_messages(str(message.author.id), minutes=30)
                time_label = "30 phút"

            embed = build_forget_embed(message.author, res, time_label)
            await message.reply(embed=embed)
            return

        # 9.8 Kiểm tra nếu người dùng hỏi về mô hình bot đang chạy (Bot Thường / Bot NSFW)
        model_check_triggers = [
            "bot nào đang chạy", "con bot nào đang chạy", "model nào đang chạy",
            "bot nsfw nào đang chạy", "bot thường nào đang chạy", "kiểm tra model",
            "check model", "check bot", "status model", "bot thường và bot nsfw",
            "cho bt bot thường", "cho biết bot thường", "bot nao dang chay",
            "model nao dang chay", "bot nsfw nao dang chay", "bot thuong nao dang chay"
        ]
        if any(term in clean_content.lower() for term in model_check_triggers):
            is_ch_nsfw = False
            if settings.NSFW_ENABLED:
                ch_id = getattr(message.channel, "id", 0)
                if (
                    (hasattr(message.channel, "is_nsfw") and message.channel.is_nsfw()) or
                    ch_id in settings.nsfw_channel_id_list or
                    ch_id in _nsfw_runtime_channels
                ):
                    is_ch_nsfw = True
            embed = build_model_status_embed(is_channel_nsfw=is_ch_nsfw)
            await message.reply(embed=embed)
            return

        # 9.9 Kiểm tra nếu người dùng hỏi "có j mới / có gì mới / vừa cập nhật gì" -> Nói trực tiếp tính năng mới + kèm bảng nút bấm
        if is_asking_whats_new(clean_content):
            gid = str(message.guild.id) if message.guild else None
            await message.reply(
                content=build_spoken_whats_new_reply(self.bot, current_guild_id=gid),
                embed=build_updates_embed(),
                view=UpdatesInteractiveView(self.bot),
            )
            return

        # 10. Tạo phản hồi hội thoại thông thường, đọc Code, đọc Ảnh & GIF (Tenor/Giphy/Discord)
        async with message.channel.typing():
            (image_data, media_hint), code_files = await asyncio.gather(
                extract_image_or_gif_from_message(message),
                extract_code_attachments(message),
            )

            # Nếu người dùng chỉ gửi link GIF Tenor/Giphy trần thì lọc bỏ URL để prompt sạch
            actual_user_message = strip_gif_urls_from_text(clean_content) if (image_data or media_hint) else clean_content
            if not actual_user_message:
                if image_data or media_hint:
                    actual_user_message = ""
                elif code_files:
                    actual_user_message = "Hãy đọc file code này, tóm tắt chức năng và chỉ ra nếu có bug hay điểm cần cải thiện."

            reply_text = await self._generate_neneka_reply(
                user_message=actual_user_message,
                discord_user_id=str(message.author.id),
                username=message.author.display_name,
                guild_id=str(message.guild.id) if message.guild else None,
                channel_id=str(message.channel.id),
                image_data=image_data,
                media_hint=media_hint,
                code_files=code_files,
            )

            # Chống phản hồi lặp lại (chỉ áp dụng cho câu ngắn không chứa code block)
            if "```" not in reply_text and proactive_engine.is_duplicate_response(message.channel.id, reply_text):
                reply_text += " ✨"
            proactive_engine.record_last_response(message.channel.id, reply_text)

            await self._send_smart_chunks(message.reply, reply_text)

async def setup(bot):
    await bot.add_cog(ChatCog(bot))

