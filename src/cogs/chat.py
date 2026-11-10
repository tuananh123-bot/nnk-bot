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
    get_vietnam_context_for_prompt,
    detect_city_from_query,
    CITIES_VN
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
        is_max_bond = (str(discord_user_id) in settings.max_bond_user_id_list)

        # 2. Truy xuất Ký ức có chọn lọc (không đổ cả database)
        mem_ctx = await memory_engine.get_memory_context(discord_user_id, user_message)
        preferred_name = mem_ctx["preferred_name"]

        # Nhận diện Đấng Sáng Tạo hoặc Max Bond hoặc CHOSEN_ONE_NAME
        if is_creator:
            preferred_name = "Sheffy-sama"
        elif is_max_bond and (not preferred_name or preferred_name == "Hiệp sĩ"):
            preferred_name = settings.CHOSEN_ONE_NAME or "Kishi-kun"
        elif settings.CHOSEN_ONE_NAME and settings.CHOSEN_ONE_NAME.lower() in username.lower():
            preferred_name = settings.CHOSEN_ONE_NAME

        # 3. Lấy thông tin Bond
        bond_info = await bond_engine.get_bond_info(discord_user_id)
        salutation = "Sheffy-sama" if is_creator else bond_info["salutation"]

        # 4. Cập nhật trạng thái tính cách dựa trên tin nhắn
        personality_engine.update_from_interaction(user_message, is_creator=is_creator, is_max_bond=is_max_bond)

        # 5. Xây dựng System Prompt kết hợp
        base_system_prompt = personality_engine.get_system_prompt(
            user_language=lang,
            user_name=f"{preferred_name} (Danh xưng phù hợp: {salutation})",
            is_creator=is_creator,
            is_max_bond=is_max_bond
        )

        # Ngữ cảnh thời gian và thời tiết thực tế tại Việt Nam (UTC+7)
        user_loc = await memory_engine.get_user_location(discord_user_id)
        vietnam_context = await get_vietnam_context_for_prompt(user_message, user_location=user_loc)

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

        if bond_info.get("is_max_bond"):
            embed = discord.Embed(title="💖 Bảng Trạng Thái - Utsushimi Neneka (MỐI QUAN HỆ SÂU SẮC NHẤT)", color=0xff79c6)
            embed.add_field(name="💖 Cấp Độ Gắn Kết", value=f"**Cấp 6 (TỐI THƯỢNG)**: *{bond_info['title']}* (9999 pts)", inline=False)
            embed.add_field(name="🎭 Cảm Xúc Nội Tâm", value="`affectionate_warmth (Ấm áp, Yêu thương & Tin tưởng tuyệt đối)`", inline=True)
            embed.add_field(name="🛡️ Độ Tin Tưởng", value="`100% (Tuyệt đối)`", inline=True)
            embed.add_field(name="💬 Mức Hảo Cảm", value="`1000/1000 (Tối đa)`", inline=True)
            embed.add_field(
                name="🗣️ Danh Xưng",
                value=f"Tiếng Việt: **\"{bond_info['salutation']}\"**\nTiếng Nhật: **「{bond_info['japanese_salutation']}」**",
                inline=False
            )
            embed.set_footer(text="Seven Crowns Reality Engine • Deepest Soulmate Bond")
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
        embed.add_field(name="`/weather [nơi]` hoặc `!n weather [nơi]`", value="Tra cứu thời tiết thực tế tại Việt Nam (theo nơi ở của bạn hoặc thành phố chỉ định).", inline=False)
        embed.add_field(name="`/location [nơi]` hoặc `!n location [nơi]`", value="Đặt nơi ở để Neneka cập nhật thời tiết chuẩn xác mà không cần hỏi lại.", inline=False)
        embed.add_field(name="`/neneka`", value="Xem hồ sơ nhân vật Thất Vương.", inline=False)
        embed.add_field(name="`/costume [tên]`", value="Xem hoặc chuyển đổi trang phục (original, new_year, alpha).", inline=False)
        embed.add_field(name="`/bond` hoặc `!n status`", value="Kiểm tra cấp độ gắn kết và điểm hảo cảm.", inline=False)
        embed.add_field(name="`/story [từ khóa]`", value="Tra cứu cốt truyện Canon và ký ức lưu trữ.", inline=False)
        embed.add_field(name="`/memory` & `/forget`", value="Quản lý và minh bạch ký ức dài hạn.", inline=False)
        embed.add_field(name="`!n nickname [@user] <tên>` hoặc `/nickname`", value="Đặt biệt danh để Neneka gọi bạn hoặc người khác.", inline=False)
        embed.add_field(name="`!n fortune` hoặc `/fortune` / `!n daily`", value="Gieo quẻ vận mệnh mỗi ngày, bói vận thế & nhận điểm gắn kết.", inline=False)
        embed.add_field(name="`!n mirror` hoặc `/mirror`", value="Mini-game Gương Ảo Ảnh: Thử tài tinh mắt đoán bản thể thật của Neneka qua nút bấm.", inline=False)
        embed.add_field(name="`!n sleep [chủ đề]` hoặc `/sleep`", value="Chế độ ru ngủ ban đêm: Neneka kể chuyện và thì thầm lời ru tiếng Nhật êm đềm.", inline=False)
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

        # 10. Tạo phản hồi hội thoại thông thường và gửi
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

