# src/cogs/memory.py
import re
from typing import Optional, Dict, Any
import discord
from discord import app_commands
from discord.ext import commands

from src.memory.engine import MemoryEngine

memory_engine = MemoryEngine()

def parse_timeframe_to_minutes(timeframe: Optional[str]) -> Optional[int]:
    """
    Chuyển đổi chuỗi timeframe ('30m', '1h', '30p', '1 tiếng', '30 phút', '60') thành số phút (int).
    Trả về:
      - số phút (ví dụ 30, 60)
      - -1 nếu là 'all' / 'toanbo'
      - None nếu không hợp lệ
    """
    if not timeframe:
        return 30
    t = timeframe.strip().lower()
    if t in ("all", "toanbo", "toàn bộ", "all_context", "tatca", "tất cả"):
        return -1
    if any(k in t for k in ["1h", "1 tiếng", "1 tieng", "1 giờ", "1 gio", "60m", "60p", "60"]):
        return 60
    if any(k in t for k in ["30m", "30p", "30 phút", "30 phut", "30"]):
        return 30
    if any(k in t for k in ["15m", "15p", "15 phút", "15 phut", "15"]):
        return 15
    if any(k in t for k in ["2h", "2 tiếng", "2 tieng", "2 giờ", "120"]):
        return 120
    match = re.search(r'(\d+)', t)
    if match:
        val = int(match.group(1))
        if "h" in t or "tiếng" in t or "giờ" in t:
            return val * 60
        return val
    return None

def build_forget_embed(user: discord.abc.User, res: Dict[str, int], time_str: str) -> discord.Embed:
    embed = discord.Embed(
        title="🧹 Ma Lực Metamorphose • Xóa Nhòa Ký Ức",
        description=(
            f"✨ *thu hồi làn sóng ma lực thực tại, ánh mắt tím điềm đạm khẽ nhìn {user.mention}*\n"
            f"Fufu... Ta đã xóa sạch toàn bộ **{res['total']}** dữ liệu tin nhắn và ngữ cảnh trò chuyện "
            f"trong vòng **{time_str}** vừa qua.\n"
            f"Dấu vết hội thoại đã được tái thiết lập tinh khôi, chúng ta có thể tiếp tục như chưa từng có chuyện gì xảy ra nhé."
        ),
        color=0x9b59b6
    )
    embed.add_field(name="💬 Tin nhắn đã xóa", value=f"`{res['messages']}` tin nhắn", inline=True)
    embed.add_field(name="🧠 Ngữ cảnh ngắn hạn", value=f"`{res['short_term']}` lượt", inline=True)
    if res.get("long_term", 0) > 0:
        embed.add_field(name="📜 Ký ức phát sinh", value=f"`{res['long_term']}` ghi chú", inline=True)
    embed.set_footer(text="Seven Crowns Reality Engine • Memory Erasure System")
    return embed

class MemoryCog(commands.Cog):
    """Quản lý và minh bạch ký ức dài hạn theo quy chuẩn bảo mật riêng tư"""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="memory", description="🧠 Xem những ký ức mà Neneka đã ghi nhớ về bạn")
    async def cmd_memory(self, interaction: discord.Interaction):
        mems = await memory_engine.get_user_memories(str(interaction.user.id))
        if not mems:
            await interaction.response.send_message(
                "Fufu... Ta chưa ghi nhận ký ức dài hạn đặc biệt nào về cậu cả. Hãy chia sẻ thêm sở thích hoặc câu chuyện của cậu nhé.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🧠 Ký Ức Dài Hạn Của Neneka Về {interaction.user.display_name}",
            description=f"Neneka đang lưu giữ **{len(mems)}** dữ kiện quan trọng về cậu:",
            color=0x3498db
        )
        for m in mems[:8]:
            embed.add_field(
                name=f"[{m['category'].upper()}] (ID: `{m['id'][:8]}` - {m['created_at']})",
                value=f"• *{m['fact']}*",
                inline=False
            )
        embed.set_footer(text="Dùng lệnh /forget <id> để yêu cầu xóa một ký ức nếu bạn muốn.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="nickname", description="🏷️ Đặt biệt danh để Neneka gọi bạn hoặc một thành viên khác")
    @app_commands.describe(
        name="Tên biệt danh mới (nhập 'reset' để xóa biệt danh trở về mặc định)",
        target="Thành viên cần đặt biệt danh (bỏ trống để đặt cho chính bạn)"
    )
    async def cmd_nickname(
        self,
        interaction: discord.Interaction,
        name: str,
        target: Optional[discord.Member] = None
    ):
        target_user = target or interaction.user
        clean_name = name.strip().strip("'\"")

        if clean_name.lower() in ["reset", "xóa", "huy", "clear", "mặc định"]:
            await memory_engine.set_preferred_name(str(target_user.id), None, target_user.name)
            await interaction.response.send_message(
                f"✨ Đã xóa biệt danh của {target_user.mention}. Kể từ giờ Neneka sẽ gọi lại bằng tên hiển thị mặc định.",
                ephemeral=False
            )
            return

        await memory_engine.set_preferred_name(str(target_user.id), clean_name, target_user.name)
        embed = discord.Embed(
            title="🏷️ Đã Ghi Nhận Biệt Danh Mới!",
            description=(
                f"Fufu... Kể từ giờ ta sẽ gọi {target_user.mention} là **'{clean_name}'**.\n"
                f"Ký ức này đã được khắc sâu vào ma thuật nhận diện thực tại của ta rồi nhé."
            ),
            color=0x9b59b6
        )
        embed.set_footer(text="Seven Crowns Identity Registry • Princess Connect! Re:Dive")
        await interaction.response.send_message(embed=embed)

    @commands.command(name="nickname", aliases=["setname", "bietdanh", "name"])
    async def pcmd_nickname(self, ctx: commands.Context, *, args: Optional[str] = None):
        """Lệnh !n nickname [@user] <tên> để đặt biệt danh cho người khác hoặc bản thân"""
        if not args or not args.strip():
            await ctx.reply(
                "❌ Cú pháp: `!n nickname [@user] <tên biệt danh>`\n"
                "• *Đặt cho người khác:* `!n nickname @TuanAnh Bé ngoan`\n"
                "• *Đặt cho bản thân:* `!n nickname Bé ngoan`\n"
                "• *Xóa biệt danh:* `!n nickname [@user] reset`"
            )
            return

        clean_text = args.strip()
        if ctx.message.mentions:
            target_user = ctx.message.mentions[0]
            clean_text = clean_text.replace(f"<@{target_user.id}>", "").replace(f"<@!{target_user.id}>", "").strip()
        else:
            target_user = ctx.author

        clean_name = clean_text.strip().strip("'\"")
        if not clean_name:
            await ctx.reply("❌ Hãy nhập tên biệt danh bạn muốn đặt! Ví dụ: `!n nickname @user Mèo con`")
            return

        if clean_name.lower() in ["reset", "xóa", "huy", "clear", "mặc định"]:
            await memory_engine.set_preferred_name(str(target_user.id), None, target_user.name)
            await ctx.reply(f"✨ Đã xóa biệt danh của {target_user.mention}. Neneka sẽ gọi lại bằng tên mặc định.")
            return

        await memory_engine.set_preferred_name(str(target_user.id), clean_name, target_user.name)
        embed = discord.Embed(
            title="🏷️ Đã Ghi Nhận Biệt Danh Mới!",
            description=(
                f"Fufu... Kể từ giờ ta sẽ gọi {target_user.mention} là **'{clean_name}'**.\n"
                f"Ký ức này đã được khắc sâu vào ma thuật nhận diện thực tại của ta rồi nhé."
            ),
            color=0x9b59b6
        )
        embed.set_footer(text="Seven Crowns Identity Registry • Princess Connect! Re:Dive")
        await ctx.reply(embed=embed)

    @app_commands.command(
        name="forget",
        description="🗑️ Yêu cầu Neneka quên tin nhắn gần đây (30m, 1h) hoặc xóa ký ức"
    )
    @app_commands.describe(
        timeframe="Khoảng thời gian cần quên: 30m (30 phút), 1h (1 tiếng), hoặc all (toàn bộ ngữ cảnh)",
        memory_id="ID ký ức dài hạn cụ thể cần xóa (tùy chọn)"
    )
    @app_commands.choices(
        timeframe=[
            app_commands.Choice(name="⏱️ 30 phút gần nhất (30m)", value="30m"),
            app_commands.Choice(name="⏳ 1 tiếng gần nhất (1h)", value="1h"),
            app_commands.Choice(name="🧹 Toàn bộ ngữ cảnh tin nhắn (All messages)", value="all"),
            app_commands.Choice(name="🧠 Toàn bộ ký ức dài hạn (All long-term)", value="all_ltm"),
        ]
    )
    async def cmd_forget(
        self,
        interaction: discord.Interaction,
        timeframe: Optional[str] = "30m",
        memory_id: Optional[str] = None
    ):
        if memory_id or timeframe == "all_ltm":
            deleted = await memory_engine.delete_user_memory(str(interaction.user.id), memory_id)
            if deleted > 0:
                target_str = f"ký ức mang ID `{memory_id}`" if memory_id else "toàn bộ ký ức dài hạn"
                await interaction.response.send_message(
                    f"✨ Đã xóa thành công **{deleted}** {target_str} khỏi cơ sở dữ liệu của Neneka.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message("❌ Không tìm thấy ký ức nào phù hợp để xóa.", ephemeral=True)
            return

        mins = parse_timeframe_to_minutes(timeframe)
        if mins == -1:
            res = await memory_engine.forget_recent_messages(str(interaction.user.id), minutes=None)
            time_label = "toàn bộ lịch sử tin nhắn"
        elif mins is not None:
            res = await memory_engine.forget_recent_messages(str(interaction.user.id), minutes=mins)
            time_label = f"{mins} phút" if mins < 60 else f"{mins // 60} tiếng"
        else:
            res = await memory_engine.forget_recent_messages(str(interaction.user.id), minutes=30)
            time_label = "30 phút"

        embed = build_forget_embed(interaction.user, res, time_label)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="forget", aliases=["quen", "xoa", "forgetmsg"])
    async def pcmd_forget(self, ctx: commands.Context, timeframe_or_id: Optional[str] = "30m"):
        """
        Lệnh !n forget [30m | 1h | all | <memory_id>]
        Ví dụ:
          !n forget 30m   (quên tin nhắn trong 30 phút gần nhất)
          !n forget 1h    (quên tin nhắn trong 1 tiếng gần nhất)
          !n forget all   (xóa sạch toàn bộ tin nhắn & ngữ cảnh)
        """
        # Nếu là ID uuid (dài hoặc có ký tự uuid)
        if timeframe_or_id and len(timeframe_or_id) > 15 and "-" in timeframe_or_id:
            deleted = await memory_engine.delete_user_memory(str(ctx.author.id), timeframe_or_id)
            if deleted > 0:
                await ctx.reply(f"✨ Đã xóa thành công ký ức mang ID `{timeframe_or_id}`.")
            else:
                await ctx.reply("❌ Không tìm thấy ký ức nào phù hợp để xóa.")
            return

        mins = parse_timeframe_to_minutes(timeframe_or_id)
        if mins == -1:
            res = await memory_engine.forget_recent_messages(str(ctx.author.id), minutes=None)
            time_label = "toàn bộ lịch sử tin nhắn"
        elif mins is not None:
            res = await memory_engine.forget_recent_messages(str(ctx.author.id), minutes=mins)
            time_label = f"{mins} phút" if mins < 60 else f"{mins // 60} tiếng"
        else:
            res = await memory_engine.forget_recent_messages(str(ctx.author.id), minutes=30)
            time_label = "30 phút"

        embed = build_forget_embed(ctx.author, res, time_label)
        await ctx.reply(embed=embed)

    @app_commands.command(name="reset", description="🧹 Làm mới ngữ cảnh hội thoại gần đây (xóa sạch ký ức ngắn hạn)")
    async def cmd_reset(self, interaction: discord.Interaction):
        deleted = await memory_engine.clear_short_term_memory(str(interaction.user.id))
        embed = discord.Embed(
            title="🧹 Đã Làm Mới Ngữ Cảnh Hội Thoại",
            description=(
                f"✨ *thu hồi quyền trượng Metamorphose, khẽ mỉm cười điềm đạm*\n"
                f"Fufu... Ta đã làm sạch **{deleted}** lượt ngữ cảnh trò chuyện ngắn hạn gần đây của {interaction.user.mention}.\n"
                f"Ký ức dài hạn và mức hảo cảm vẫn được giữ nguyên vẹn. Chúng ta có thể bắt đầu lại chủ đề mới rồi nhé."
            ),
            color=0x9b59b6
        )
        embed.set_footer(text="Seven Crowns Memory Management • Princess Connect! Re:Dive")
        await interaction.response.send_message(embed=embed)

    @commands.command(name="reset", aliases=["clear", "lammoi", "clean"])
    async def pcmd_reset(self, ctx: commands.Context):
        """Lệnh !n reset hoặc !n clear để làm mới ngữ cảnh trò chuyện ngắn hạn"""
        deleted = await memory_engine.clear_short_term_memory(str(ctx.author.id))
        embed = discord.Embed(
            title="🧹 Đã Làm Mới Ngữ Cảnh Hội Thoại",
            description=(
                f"✨ *thu hồi quyền trượng Metamorphose, khẽ mỉm cười điềm đạm*\n"
                f"Fufu... Ta đã làm sạch **{deleted}** lượt ngữ cảnh trò chuyện ngắn hạn gần đây của {ctx.author.mention}.\n"
                f"Ký ức dài hạn và mức hảo cảm vẫn được giữ nguyên vẹn. Chúng ta có thể bắt đầu một câu chuyện mới rồi nhé."
            ),
            color=0x9b59b6
        )
        embed.set_footer(text="Seven Crowns Memory Management • Princess Connect! Re:Dive")
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(MemoryCog(bot))

