# discord_bot.py
import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

from state_manager import StateManager
from memory_system import MemorySystem
from cognitive_engine import CognitiveEngine
from config_persona import BOND_STORIES

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not DISCORD_TOKEN:
    raise RuntimeError("Chưa tìm thấy DISCORD_TOKEN trong file .env!")
if not GEMINI_API_KEY and not GROQ_API_KEY:
    raise RuntimeError("Cần ít nhất GEMINI_API_KEY hoặc GROQ_API_KEY trong file .env!")

# Khởi tạo các hệ thống
state_mgr = StateManager()
memory_sys = MemorySystem()
engine = CognitiveEngine(
    gemini_api_key=GEMINI_API_KEY,
    groq_api_key=GROQ_API_KEY,
    state_mgr=state_mgr,
    memory_sys=memory_sys
)

# Cấu hình Discord Bot
intents = discord.Intents.default()
intents.message_content = True

def get_prefix(bot, message):
    """Hỗ trợ các prefix: '!n ', '!n', 'n! ', 'n!'"""
    return commands.when_mentioned_or("!n ", "!n", "n! ", "n!")(bot, message)

bot = commands.Bot(
    command_prefix=get_prefix,
    intents=intents,
    help_command=None
)

# =========================================================
# KÊNH TỰ ĐỘNG TRẢ LỜI (không cần @mention)
#
# Thêm Channel ID vào danh sách này.
# Lấy Channel ID: Bật Developer Mode trong Discord Settings
# → Chuột phải vào kênh → "Copy Channel ID"
# =========================================================
AUTO_REPLY_CHANNEL_IDS: set[int] = set(
    int(cid.strip())
    for cid in os.getenv("AUTO_REPLY_CHANNELS", "").split(",")
    if cid.strip().isdigit()
)

# Cấu hình hiển thị Chain of Thought (mặc định tắt trên Discord để gọn gàng)
show_cot_global = False

@bot.event
async def on_ready():
    print(f"==================================================")
    print(f" Đã đăng nhập Discord thành công: {bot.user} (ID: {bot.user.id})")
    print(f" Trạng thái ban đầu:\n{state_mgr.render_affection_bar()}")
    print(f"==================================================")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="các biến số ma thuật | !n help"
        )
    )

@bot.command(name="status")
async def cmd_status(ctx):
    """Hiển thị trạng thái hảo cảm, cảm xúc hiện tại của Neneka"""
    tier = state_mgr.get_current_tier()
    pts = state_mgr.state.affection
    filled = int((pts / 1000) * 15)
    bar = "█" * filled + "░" * (15 - filled)

    embed = discord.Embed(
        title="👑 Bảng Trạng Thái - Utsushimi Neneka",
        color=0x9b59b6
    )
    embed.add_field(
        name="💜 Mức Hảo Cảm",
        value=f"[{bar}] **{pts}/1000**\nCấp {tier['tier_id']}: *{tier['name']}*",
        inline=False
    )
    embed.add_field(
        name="🎭 Cảm Xúc Hiện Tại",
        value=f"`{state_mgr.state.current_emotion}`",
        inline=True
    )
    embed.add_field(
        name="🛡️ Bản Năng Bảo Bọc",
        value=f"`{state_mgr.state.protective_instinct}%`",
        inline=True
    )
    embed.add_field(
        name="💬 Số Lượt Tương Tác",
        value=f"`{state_mgr.state.interaction_count}` lượt",
        inline=True
    )
    embed.set_footer(text="Princess Connect! Re:Dive | Seven Crowns")
    await ctx.reply(embed=embed)

@bot.command(name="cot")
async def cmd_cot(ctx):
    """Bật / Tắt hiển thị suy nghĩ nội tâm (Chain of Thought)"""
    global show_cot_global
    show_cot_global = not show_cot_global
    status_str = "BẬT" if show_cot_global else "TẮT"
    await ctx.reply(f"🧠 [Hệ thống] Chế độ hiển thị Chain of Thought hiện đang: **{status_str}**")

@bot.command(name="reset")
async def cmd_reset(ctx):
    """Đặt lại hảo cảm và ký ức của Neneka"""
    if os.path.exists(state_mgr.filepath):
        try:
            os.remove(state_mgr.filepath)
        except Exception:
            pass
    if os.path.exists(memory_sys.filepath):
        try:
            os.remove(memory_sys.filepath)
        except Exception:
            pass

    state_mgr.state = state_mgr._load_state()
    memory_sys.long_term_facts = []
    memory_sys.short_term_history = []
    await ctx.reply("✨ [Hệ thống] Đã đặt lại toàn bộ hảo cảm và ký ức của Neneka về mặc định!")

@bot.command(name="addchannel")
@commands.has_permissions(manage_channels=True)
async def cmd_addchannel(ctx, channel: discord.TextChannel = None):
    """Thêm kênh vào danh sách tự động trả lời (không cần @mention)"""
    target = channel or ctx.channel
    AUTO_REPLY_CHANNEL_IDS.add(target.id)
    await ctx.reply(
        f"✅ Kênh {target.mention} đã được thêm vào danh sách tự động trả lời!\n"
        f"Neneka sẽ trả lời **mọi tin nhắn** trong kênh này mà không cần tag."
    )

@bot.command(name="removechannel")
@commands.has_permissions(manage_channels=True)
async def cmd_removechannel(ctx, channel: discord.TextChannel = None):
    """Xóa kênh khỏi danh sách tự động trả lời"""
    target = channel or ctx.channel
    AUTO_REPLY_CHANNEL_IDS.discard(target.id)
    await ctx.reply(
        f"❎ Kênh {target.mention} đã bị xóa khỏi danh sách tự động trả lời.\n"
        f"Neneka sẽ chỉ phản hồi khi được @mention hoặc reply trong kênh này."
    )

@bot.command(name="listchannels")
async def cmd_listchannels(ctx):
    """Xem danh sách kênh đang bật tự động trả lời"""
    if not AUTO_REPLY_CHANNEL_IDS:
        await ctx.reply("📋 Hiện chưa có kênh nào được bật tự động trả lời.")
        return
    lines = []
    for cid in AUTO_REPLY_CHANNEL_IDS:
        ch = bot.get_channel(cid)
        lines.append(f"• {ch.mention if ch else f'ID: {cid}'}")
    await ctx.reply("📋 **Các kênh đang bật tự động trả lời:**\n" + "\n".join(lines))

def make_bond_embed(bond_id: int) -> discord.Embed:
    info = BOND_STORIES.get(bond_id)
    if not info:
        return None
    embed = discord.Embed(
        title=f"✨ {info['title']}",
        description=info["story"],
        color=0xff79c6
    )
    embed.set_footer(text="Ký ức liên kết Neneka • Princess Connect! Re:Dive")
    return embed

@bot.command(name="gift", aliases=["tangqua"])
async def cmd_gift(ctx, *, gift_name: str = None):
    """Tặng quà/điểm tâm Landosol cho Neneka để tăng hảo cảm"""
    if not gift_name:
        await ctx.reply("Fufu... Cậu định tặng gì cho ta thế? Hãy dùng lệnh: `!n gift <tên món quà>` nhé.")
        return

    async with ctx.typing():
        try:
            result = await asyncio.to_thread(engine.process_gift, gift_name)

            tier = state_mgr.get_current_tier()
            pts = state_mgr.state.affection
            filled = int((pts / 1000) * 12)
            bar = "█" * filled + "░" * (12 - filled)

            embed = discord.Embed(
                title=f"🎁 Quà Tặng Landosol: {gift_name}",
                description=f"{result.action_gesture} {result.spoken_response}",
                color=0xf1c40f
            )
            embed.add_field(
                name="💜 Hảo cảm nhận được",
                value=f"+{result.affection_delta} điểm | Trạng thái: `{result.selected_emotion}`",
                inline=False
            )
            embed.add_field(
                name="📊 Tiến độ hảo cảm",
                value=f"[{bar}] **{pts}/1000** (Cấp {tier['tier_id']}: *{tier['name']}*)",
                inline=False
            )
            await ctx.reply(embed=embed)

            # Nếu có Bond Story mới mở khóa
            if getattr(result, "newly_unlocked_bonds", None):
                for bid in result.newly_unlocked_bonds:
                    b_embed = make_bond_embed(bid)
                    if b_embed:
                        await ctx.send(
                            content="🎉 **CHÚC MỪNG!** Cậu vừa mở khóa một mẩu ký ức mới với Neneka!",
                            embed=b_embed
                        )

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[Error processing gift]: {e}")
            await ctx.reply("Fufu... Có chút ma lực nhiễu loạn khi nhận món quà này. Cậu thử lại sau nhé.")

@bot.command(name="bond", aliases=["story", "kiniem"])
async def cmd_bond(ctx, bond_num: int = None):
    """Xem hoặc đọc lại các mẩu truyện Ký ức Liên kết (Bond Stories)"""
    unlocked = state_mgr.state.unlocked_bonds
    current_pts = state_mgr.state.affection

    if bond_num is None:
        embed = discord.Embed(
            title="📖 Ký Ức Liên Kết - Utsushimi Neneka (Bond Stories)",
            description="Tăng hảo cảm thông qua trò chuyện và tặng quà để mở khóa các mẩu truyện riêng tư với Neneka!",
            color=0x9b59b6
        )
        for bid, info in BOND_STORIES.items():
            if bid in unlocked:
                status_icon = "✅ ĐÃ MỞ KHÓA"
                val = f"*{info['summary']}*\n👉 Gõ `!n bond {bid}` để đọc lại"
            else:
                status_icon = f"🔒 KHÓA (Cần {info['req_affection']} Hảo cảm)"
                val = f"*{info['summary']}* (Hiện tại: {current_pts}/{info['req_affection']})"

            embed.add_field(
                name=f"[{status_icon}] {info['title']}",
                value=val,
                inline=False
            )
        embed.set_footer(text="Dùng lệnh '!n bond <1-5>' để đọc mẩu truyện tương ứng.")
        await ctx.reply(embed=embed)
        return

    if bond_num not in BOND_STORIES:
        await ctx.reply("❌ Neneka hiện chỉ có từ **Bond 1** đến **Bond 5** thôi nhé cậu hiệp sĩ.")
        return

    if bond_num not in unlocked:
        req = BOND_STORIES[bond_num]['req_affection']
        await ctx.reply(
            f"🔒 **Mẩu truyện này chưa được mở khóa!**\n"
            f"Neneka yêu cầu **{req} điểm hảo cảm** (Hiện tại của cậu: **{current_pts}/1000**).\n"
            f"Hãy trò chuyện thêm hoặc dùng `!n gift <món quà>` để gia tăng hảo cảm nhé!"
        )
        return

    b_embed = make_bond_embed(bond_num)
    await ctx.reply(embed=b_embed)

@bot.command(name="help")
async def cmd_help(ctx):
    """Hiển thị hướng dẫn các lệnh"""
    embed = discord.Embed(
        title="📖 Danh Sách Lệnh Neneka Bot",
        description="Nói chuyện với Neneka bằng cách **@mention**, **reply** tin nhắn của cô ấy, hoặc trong **kênh tự động trả lời**.",
        color=0x9b59b6
    )
    embed.add_field(name="`!n status`", value="Xem chỉ số hảo cảm, cảm xúc, bảo bọc hiện tại.", inline=False)
    embed.add_field(name="`!n gift <món quà>`", value="Tặng điểm tâm/quà Landosol cho Neneka để tăng hảo cảm.", inline=False)
    embed.add_field(name="`!n bond [1-5]`", value="Xem danh sách hoặc đọc các mẩu truyện Ký ức Liên kết đã mở khóa.", inline=False)
    embed.add_field(name="`!n cot`", value="Bật/Tắt hiển thị luồng suy nghĩ nội tâm của Neneka.", inline=False)
    embed.add_field(name="`!n reset`", value="Reset điểm hảo cảm và ký ức về trạng thái ban đầu.", inline=False)
    embed.add_field(name="`!n addchannel [#kênh]`", value="Thêm kênh vào danh sách tự động trả lời (không cần @mention).\nBỏ trống để chọn kênh hiện tại.", inline=False)
    embed.add_field(name="`!n removechannel [#kênh]`", value="Xóa kênh khỏi danh sách tự động trả lời.", inline=False)
    embed.add_field(name="`!n listchannels`", value="Xem danh sách các kênh đang bật tự động trả lời.", inline=False)
    await ctx.reply(embed=embed)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Xử lý các command có tiền tố !n hoặc n!
    if message.content.startswith(("!n", "n!")):
        await bot.process_commands(message)
        return

    # Kiểm tra xem bot có được tag hoặc reply không
    is_mentioned = bot.user in message.mentions
    is_reply_to_bot = (
        message.reference is not None and
        isinstance(message.reference.resolved, discord.Message) and
        message.reference.resolved.author.id == bot.user.id
    )
    is_dm = isinstance(message.channel, discord.DMChannel)
    # Kênh nằm trong danh sách tự động trả lời (không cần @mention)
    is_auto_channel = message.channel.id in AUTO_REPLY_CHANNEL_IDS

    # Chỉ phản hồi khi được tag, reply, DM hoặc trong kênh tự động
    if not (is_mentioned or is_reply_to_bot or is_dm or is_auto_channel):
        return

    # Làm sạch nội dung tin nhắn (bỏ mention bot)
    clean_content = message.clean_content.replace(f"@{bot.user.name}", "").strip()
    if not clean_content:
        await message.reply("Fufu... Cậu gọi ta có việc gì sao?")
        return

    async with message.channel.typing():
        try:
            # Chạy qua thread pool để không block asyncio loop
            result = await asyncio.to_thread(engine.process_message, clean_content)

            reply_text = f"{result.action_gesture} {result.spoken_response}"

            if show_cot_global:
                cot_text = (
                    f"\n\n> 🧠 **Suy nghĩ nội tâm:**\n"
                    f"> *Quan sát:* {result.user_state_observation}\n"
                    f"> *Lý trí:* {result.logical_analysis}\n"
                    f"> *Che chở:* {result.sisterly_impulse}\n"
                    f"> *Cảm xúc:* `{result.selected_emotion}` | *Hảo cảm:* `{result.affection_delta:+d}`"
                )
                if len(reply_text) + len(cot_text) <= 1900:
                    reply_text += cot_text

            # Cắt ngắn nếu quá 2000 ký tự (giới hạn Discord)
            if len(reply_text) > 2000:
                reply_text = reply_text[:1990] + "..."

            await message.reply(reply_text)

            # Nếu cuộc trò chuyện kích hoạt mở khóa Bond Story mới
            if getattr(result, "newly_unlocked_bonds", None):
                for bid in result.newly_unlocked_bonds:
                    b_embed = make_bond_embed(bid)
                    if b_embed:
                        await message.channel.send(
                            content="🎉 **CHÚC MỪNG!** Cậu vừa mở khóa một mẩu ký ức mới với Neneka!",
                            embed=b_embed
                        )

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[Error processing message]: {e}")
            await message.reply("Fufu... Có một chút nhiễu loạn trong luồng ma lực của ta vừa xảy ra. Cậu nói lại được không?")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)

