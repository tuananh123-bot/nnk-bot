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
        # 1. Phát hiện ngôn ngữ
        lang = personality_engine.detect_language(user_message)

        # 2. Truy xuất Ký ức có chọn lọc (không đổ cả database)
        mem_ctx = await memory_engine.get_memory_context(discord_user_id, user_message)
        preferred_name = mem_ctx["preferred_name"]

        # Nhận diện CHOSEN_ONE_NAME nếu có cấu hình
        if settings.CHOSEN_ONE_NAME and settings.CHOSEN_ONE_NAME.lower() in username.lower():
            preferred_name = settings.CHOSEN_ONE_NAME

        # 3. Lấy thông tin Bond
        bond_info = await bond_engine.get_bond_info(discord_user_id)
        salutation = bond_info["salutation"]

        # 4. Cập nhật trạng thái tính cách dựa trên tin nhắn
        personality_engine.update_from_interaction(user_message)

        # 5. Xây dựng System Prompt kết hợp
        base_system_prompt = personality_engine.get_system_prompt(
            user_language=lang,
            user_name=f"{preferred_name} (Danh xưng phù hợp: {salutation})"
        )

        memory_section = ""
        if mem_ctx["relevant_facts"]:
            memory_section += "\n### KÝ ỨC DÀI HẠN LIÊN QUAN VỀ NGƯỜI ĐỐI THOẠI:\n" + "\n".join(mem_ctx["relevant_facts"])

        history_messages = []
        for h in mem_ctx["recent_history"]:
            history_messages.append({"role": "user", "content": h["user"]})
            history_messages.append({"role": "assistant", "content": h["neneka"]})

        full_system_prompt = f"{base_system_prompt}\n{memory_section}"

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

    # =========================================================================
    # LEGACY PREFIX COMMANDS (!n, n!)
    # =========================================================================
    @commands.command(name="status")
    async def pcmd_status(self, ctx):
        """Hiển thị trạng thái hảo cảm, cảm xúc hiện tại của Neneka"""
        bond_info = await bond_engine.get_bond_info(str(ctx.author.id))
        st = personality_engine.state

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
            # Tăng điểm Bond và tính cảm xúc quà tặng
            lvl, pts, up = await bond_engine.add_bond_points(str(ctx.author.id), points=20, event_type="GIFT", description=f"Tặng quà: {gift_name}")
            personality_engine.update_from_interaction(gift_name, affection_delta=15, new_emotion="affectionate_warmth")

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
            embed.add_field(name="💜 Điểm Gắn Kết Nhận Được", value=f"+20 điểm (Tổng: **{pts}** pts - Cấp {lvl})", inline=False)
            if up:
                embed.add_field(name="🎉 THĂNG CẤP BOND!", value=f"Chúc mừng! Cậu vừa đạt tới **Cấp {up}** trong quan hệ với Neneka!", inline=False)

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
        embed.add_field(name="`/neneka`", value="Xem hồ sơ nhân vật Thất Vương.", inline=False)
        embed.add_field(name="`/costume [tên]`", value="Xem hoặc chuyển đổi trang phục (original, new_year, alpha).", inline=False)
        embed.add_field(name="`/bond` hoặc `!n status`", value="Kiểm tra cấp độ gắn kết và điểm hảo cảm.", inline=False)
        embed.add_field(name="`/story [từ khóa]`", value="Tra cứu cốt truyện Canon và ký ức lưu trữ.", inline=False)
        embed.add_field(name="`/memory` & `/forget`", value="Quản lý và minh bạch ký ức dài hạn.", inline=False)
        embed.add_field(name="`/speak <câu>`", value="Yêu cầu Neneka cất giọng tiếng Nhật chuẩn.", inline=False)
        embed.add_field(name="`/join` & `/leave`", value="Mời Neneka vào hoặc rời phòng thoại (Voice Channel).", inline=False)
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

        # 2. BẮT BUỘC: bot.process_commands(message) vẫn được gọi khi dùng on_message
        if message.content.startswith(("!n", "n!")):
            await self.bot.process_commands(message)
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

        # 5. Tạo phản hồi và gửi
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
