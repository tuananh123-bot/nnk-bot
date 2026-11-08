# src/cogs/chat.py
import re
import asyncio
import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.config import settings
from src.llm.groq_client import GroqClient
from src.personality.engine import PersonalityEngine
from src.memory.engine import MemoryEngine
from src.bond.engine import BondEngine
from src.autonomous.proactive_engine import proactive_engine
from src.utils.vietnam_context import (
    get_vietnam_time_info,
    get_vietnam_weather_info,
    get_vietnam_context_for_prompt
)
from src.voice.song_manager import is_singing_request, create_song_embed
from src.voice.voice_channel import voice_channel_mgr

logger = logging.getLogger("Neneka.Chat")

groq_client = GroqClient()
personality_engine = PersonalityEngine()
memory_engine = MemoryEngine(groq_client=groq_client)
bond_engine = BondEngine()

class ChatCog(commands.Cog):
    """Xử lý hội thoại tự nhiên, lệnh chat slash command và các lệnh tiền tố kế thừa (!n, n!)"""
    def __init__(self, bot):
        self.bot = bot

    async def _generate_neneka_reply(
        self,
        user_message: str,
        discord_user_id: str,
        username: str,
        guild_id: Optional[str],
        channel_id: str
    ) -> str:
        """Tạo phản hồi chuẩn mực cho Neneka kết hợp Ký ức, Tính cách và Groq LLM"""
        # 1. Phát hiện ngôn ngữ và quyền của Đấng Sáng Tạo (Creator)
        lang = personality_engine.detect_language(user_message)
        is_creator = (str(discord_user_id) == str(settings.CREATOR_USER_ID))

        # 2. Truy xuất Ký ức có chọn lọc (không đổ cả database)
        mem_ctx = await memory_engine.get_memory_context(discord_user_id, user_message)
        preferred_name = mem_ctx["preferred_name"]

        # Nhận diện Đấng Sáng Tạo hoặc CHOSEN_ONE_NAME
        if is_creator:
            preferred_name = f"Đấng Sáng Tạo ({username})"
        elif settings.CHOSEN_ONE_NAME and settings.CHOSEN_ONE_NAME.lower() in username.lower():
            preferred_name = settings.CHOSEN_ONE_NAME

        # 3. Lấy thông tin Bond
        bond_info = await bond_engine.get_bond_info(discord_user_id)
        salutation = bond_info["salutation"]

        # 4. Cập nhật trạng thái tính cách dựa trên tin nhắn
        personality_engine.update_from_interaction(user_message, is_creator=is_creator)

        # 5. Xây dựng System Prompt kết hợp
        base_system_prompt = personality_engine.get_system_prompt(
            user_language=lang,
            user_name=f"{preferred_name} (Danh xưng phù hợp: {salutation})",
            is_creator=is_creator
        )

        # Ngữ cảnh thời gian và thời tiết thực tế tại Việt Nam (UTC+7)
        vietnam_context = await get_vietnam_context_for_prompt(user_message)

        memory_section = ""
        if mem_ctx["relevant_facts"]:
            memory_section += "\n### KÝ ỨC DÀI HẠN LIÊN QUAN VỀ NGƯỜI ĐỐI THOẠI:\n" + "\n".join(mem_ctx["relevant_facts"])

        history_messages = []
        for h in mem_ctx["recent_history"]:
            history_messages.append({"role": "user", "content": h["user"]})
            history_messages.append({"role": "assistant", "content": h["neneka"]})

        full_system_prompt = f"{base_system_prompt}\n\n{vietnam_context}\n{memory_section}"

        # 6. Gọi Groq LLM
        messages = [{"role": "system", "content": full_system_prompt}]
        messages.extend(history_messages)
        messages.append({"role": "user", "content": user_message})

        try:
            reply = await groq_client.chat_completion(messages, temperature=0.75, max_tokens=1200)
        except Exception as e:
            logger.error(f"Lỗi khi gọi Groq LLM: {e}")
            reply = "*khẽ nhấp ngụm trà, ánh mắt khép hờ* Fufu... Ma lực thực tại vừa có chút nhiễu loạn. Cậu nói lại xem nào?"

        # 7. Cộng điểm Bond và cập nhật Ký ức
        await bond_engine.add_bond_points(discord_user_id, points=2, event_type="CONVERSATION")
        await memory_engine.record_exchange(
            discord_user_id=discord_user_id,
            username=username,
            channel_id=channel_id,
            user_message=user_message,
            bot_response=reply,
            guild_id=guild_id
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

    @app_commands.command(name="reset", description="✨ Làm mới cuộc hội thoại hiện tại trong kênh (giữ nguyên ký ức dài hạn)")
    async def cmd_reset_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "✨ *phẩy nhẹ quyền trượng Metamorphose, xóa sạch bụi mờ của cuộc trò chuyện cũ*\n"
            "Fufu... Dòng ma lực hội thoại vừa được tái lập lại từ đầu. Giờ thì cậu muốn bắt đầu câu chuyện mới thế nào nào?",
            ephemeral=False
        )

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
        time_info = get_vietnam_time_info()
        weather_list = await get_vietnam_weather_info(location)
        if not weather_list:
            await interaction.followup.send("Fufu... Ma lực khí tượng đang có chút nhiễu loạn, ta chưa thể đo lường thời tiết vùng này lúc này được.")
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

    # =========================================================================
    # LEGACY PREFIX COMMANDS (!n, n!)
    # =========================================================================
    @commands.command(name="status")
    async def pcmd_status(self, ctx):
        """Hiển thị trạng thái hảo cảm, cảm xúc hiện tại của Neneka"""
        bond_info = await bond_engine.get_bond_info(str(ctx.author.id))
        st = personality_engine.state
        is_creator = bond_info.get("is_creator", False)

        if is_creator:
            embed = discord.Embed(title="👑 Bảng Trạng Thái - Utsushimi Neneka (ĐẤNG SÁNG TẠO)", color=0xf1c40f)
            embed.add_field(name="👑 Thân Phận Tối Cao", value=f"**{bond_info['title']}** (Điểm: **∞ / Vĩnh Cửu**)", inline=False)
            embed.add_field(name="🎭 Cảm Xúc Nội Tâm", value="`deep_reverence (Cung kính & Tôn trọng tuyệt đối)`", inline=True)
            embed.add_field(name="🛡️ Độ Tin Tưởng", value="`100% (Tuyệt đối)`", inline=True)
            embed.add_field(name="💬 Mức Hảo Cảm", value="`1000/1000 (Tối thượng)`", inline=True)
            embed.add_field(
                name="🗣️ Danh Xưng",
                value=f"Tiếng Việt: **\"{bond_info['salutation']}\"**\nTiếng Nhật: **「{bond_info['japanese_salutation']}」**",
                inline=False
            )
            embed.set_footer(text="Seven Crowns Reality Engine • Special Creator Privilege")
            await ctx.reply(embed=embed)
            return

        embed = discord.Embed(title="👑 Bảng Trạng Thái - Utsushimi Neneka", color=0x9b59b6)
        embed.add_field(name="💜 Cấp Độ Gắn Kết", value=f"**Cấp {bond_info['level']}**: *{bond_info['title']}* ({bond_info['points']} pts)", inline=False)
        embed.add_field(name="🎭 Cảm Xúc Nội Tâm", value=f"`{st.emotional_state}`", inline=True)
        embed.add_field(name="🛡️ Độ Tự Tin", value=f"`{st.confidence}%`", inline=True)
        embed.add_field(name="💬 Mức Hảo Cảm", value=f"`{st.affection}/1000`", inline=True)
        embed.set_footer(text="Seven Crowns Simulation • Princess Connect! Re:Dive")
        await ctx.reply(embed=embed)

    @commands.command(name="gift")
    async def pcmd_gift(self, ctx, *, gift_name: str = None):
        """Tặng quà hoặc điểm tâm Landosol cho Neneka"""
        if not gift_name:
            await ctx.reply("Fufu... Cậu định tặng gì cho ta thế? Hãy dùng: `!n gift <tên món quà>` nhé.")
            return

        async with ctx.typing():
            is_creator = (str(ctx.author.id) == str(settings.CREATOR_USER_ID))

            # Tăng điểm Bond và tính cảm xúc quà tặng
            lvl, pts, up = await bond_engine.add_bond_points(str(ctx.author.id), points=20, event_type="GIFT", description=f"Tặng quà: {gift_name}")
            personality_engine.update_from_interaction(gift_name, affection_delta=15, new_emotion="affectionate_warmth", is_creator=is_creator)

            if is_creator:
                prompt = (
                    f"ĐẤNG SÁNG TẠO CỦA NENEKA (Người tạo ra bot, ID {settings.CREATOR_USER_ID}) vừa đích thân gửi tặng Neneka món quà: '{gift_name}'. "
                    "Hãy phản hồi bằng sự cảm kích vô bờ bến, cung kính, hạnh phúc ngọt ngào và lòng trung thành tuyệt đối. "
                    "Xưng 'Ta' và gọi Người là 'Ngài' hoặc 'Người sáng tạo của ta'. Kèm hành động *...* tao nhã, nâng niu món quà trân quý."
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
                color=0xf1c40f
            )
            if is_creator:
                embed.add_field(name="👑 Đặc Quyền Đấng Sáng Tạo", value="Món quà từ Đấng Sáng Tạo được Neneka trân trọng lưu giữ vĩnh cửu!", inline=False)
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

    @commands.command(name="weather")
    async def pcmd_weather(self, ctx, *, location: Optional[str] = None):
        """Tra cứu thời tiết thực tế hôm nay tại Việt Nam"""
        async with ctx.typing():
            time_info = get_vietnam_time_info()
            weather_list = await get_vietnam_weather_info(location)
            if not weather_list:
                await ctx.reply("Fufu... Ma lực khí tượng đang có chút nhiễu loạn, ta chưa thể đo lường thời tiết vùng này lúc này được.")
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

    @commands.command(name="help")
    async def pcmd_help(self, ctx):
        """Hiển thị hướng dẫn lệnh"""
        embed = discord.Embed(
            title="📖 Danh Sách Lệnh Neneka Bot",
            description="Trò chuyện bằng Slash Commands `/chat`, mention bot hoặc gõ trong kênh tự động trả lời.",
            color=0x9b59b6
        )
        embed.add_field(name="`/chat <lời nhắn>` hoặc `!n chat`", value="Trò chuyện trực tiếp cùng Neneka.", inline=False)
        embed.add_field(name="`/time` hoặc `!n time`", value="Xem giờ, thứ, ngày tháng và buổi hiện tại tại Việt Nam.", inline=False)
        embed.add_field(name="`/weather [nơi]` hoặc `!n weather [nơi]`", value="Tra cứu thời tiết thực tế tại Việt Nam (Hà Nội, Sài Gòn, Đà Nẵng, Đà Lạt...).", inline=False)
        embed.add_field(name="`/neneka`", value="Xem hồ sơ nhân vật Thất Vương.", inline=False)
        embed.add_field(name="`/costume [tên]`", value="Xem hoặc chuyển đổi trang phục (original, new_year, alpha).", inline=False)
        embed.add_field(name="`/bond` hoặc `!n status`", value="Kiểm tra cấp độ gắn kết và điểm hảo cảm.", inline=False)
        embed.add_field(name="`/story [từ khóa]`", value="Tra cứu cốt truyện Canon và ký ức lưu trữ.", inline=False)
        embed.add_field(name="`/memory` & `/forget`", value="Quản lý và minh bạch ký ức dài hạn.", inline=False)
        embed.add_field(name="`!n speak <câu>` hoặc `/speak`", value="Yêu cầu Neneka cất giọng tiếng Nhật (Fish Audio Metamorph Regnant).", inline=False)
        embed.add_field(name="`!n sing [chủ đề]` hoặc `/sing`", value="Yêu cầu Neneka cất giọng hát bài ngẫu nhiên theo phong cách Nhật Bản.", inline=False)
        embed.add_field(name="`!n join` & `!n leave`", value="Mời Neneka vào hoặc rời phòng thoại (Voice Channel).", inline=False)
        embed.add_field(name="`!n quote` & `!n radio`", value="Phát câu thoại kinh điển gốc hoặc lời chào ngẫu nhiên trong Voice.", inline=False)
        embed.add_field(name="`/autochat` & `/autonomous`", value="Lệnh quản trị cấu hình kênh và chế độ tự động.", inline=False)
        embed.set_footer(text="Princess Connect! Re:Dive • Autonomous Neneka AI")
        await ctx.reply(embed=embed)

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

        # 3. Kiểm tra điều kiện kích hoạt phản hồi
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.bot.user in message.mentions
        is_reply_to_bot = (
            message.reference is not None and
            isinstance(message.reference.resolved, discord.Message) and
            message.reference.resolved.author.id == self.bot.user.id
        )

        clean_content = message.clean_content.replace(f"@{self.bot.user.name}", "").strip()

        should, reason = proactive_engine.should_reply(
            is_bot=message.author.bot,
            is_dm=is_dm,
            is_mentioned=is_mentioned,
            is_reply_to_bot=is_reply_to_bot,
            channel_id=message.channel.id,
            content=clean_content
        )

        if not should:
            return

        # 4. Kiểm tra Rate Limit & Cooldown
        allowed, rl_reason = await proactive_engine.check_rate_limit(message.channel.id, message.author.id)
        if not allowed:
            logger.debug(f"Rate limited message from {message.author.id}: {rl_reason}")
            return

        # 5. Kiểm tra nếu người dùng yêu cầu Neneka hát trong hội thoại tự nhiên
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

        # 6. Tạo phản hồi hội thoại thông thường và gửi
        async with message.channel.typing():
            reply_text = await self._generate_neneka_reply(
                user_message=clean_content,
                discord_user_id=str(message.author.id),
                username=message.author.display_name,
                guild_id=str(message.guild.id) if message.guild else None,
                channel_id=str(message.channel.id)
            )

            # Chống phản hồi lặp lại
            if proactive_engine.is_duplicate_response(message.channel.id, reply_text):
                reply_text += " ..Fufu."
            proactive_engine.record_last_response(message.channel.id, reply_text)

            # Cắt ngắn nếu vượt quá giới hạn 2000 ký tự Discord
            if len(reply_text) > 2000:
                reply_text = reply_text[:1990] + "..."

            await message.reply(reply_text)

async def setup(bot):
    await bot.add_cog(ChatCog(bot))

