# src/voice/sleep_manager.py
import os
import random
import logging
from typing import Dict, Any, List, Optional, Tuple
import discord

from src.voice.japanese_tts import japanese_tts
from src.voice.voice_channel import voice_channel_mgr

logger = logging.getLogger("Neneka.SleepManager")

SLEEP_LULLABIES: List[Dict[str, Any]] = [
    {
        "id": "moonlit_landosol",
        "title": "🌙 Ánh Trăng Dịu Êm Trên Thành Landosol",
        "theme": "Thì thầm đêm khuya & Thư giãn tâm trí",
        "japanese_whisper": "今夜はとても静かね、坊や。目を閉じて、私の声だけを聞いて…おやすみなさい。",
        "romaji": "Kon'ya wa totemo shizuka ne, bouya. Me wo tojite, watashi no koe dake wo kiite... Oyasuminasai.",
        "vietnamese_story": (
            "*Đêm nay ánh trăng ở Landosol sáng và yên tĩnh lạ kỳ. Cậu đã vất vả suốt cả ngày dài rồi...*\n"
            "*Hãy thả lỏng đôi vai, khép hờ đôi mi và chỉ lắng nghe thanh âm của ta thôi.*\n"
            "*Mọi âu lo của ngày hôm nay, hãy cứ gửi gắm lại cho ảo ảnh của ta che chở. Chúc cậu ngủ thật ngon.*"
        ),
        "bedtime_tip": "Hãy đặt điện thoại xuống, uống một ngụm nước ấm và hít thở thật sâu nhé."
    },
    {
        "id": "counting_sheep",
        "title": "🐑 Đếm Cừu Ảo Ảnh Bồng Bềnh",
        "theme": "Đếm cừu ru ngủ thư thái",
        "japanese_whisper": "一匹、二匹…ふふ、私の幻影の羊たちはふわふわで温かいでしょう？ 良い夢を見てね。",
        "romaji": "Ippiki, nihiki... fufu, watashi no gen'ei no hitsuji-tachi wa fuwafuwa de tatakai deshou? Yoi yume wo mite ne.",
        "vietnamese_story": (
            "*Một chú cừu bông trắng muốt, hai chú cừu bông lướt qua bầu trời ngàn sao tím...*\n"
            "*Fufu... Những chú cừu do ma thuật Metamorphose hóa ra có mềm mại và ấm áp không nào?*\n"
            "*Ba chú cừu, bốn chú cừu... Cứ chầm chậm chìm vào giấc ngủ êm đềm như đang tựa vào lòng ta nhé.*"
        ),
        "bedtime_tip": "Thả lỏng toàn bộ các cơ từ trán, mắt cho tới ngón chân để cơ thể chìm vào giấc ngủ."
    },
    {
        "id": "chamomile_tea",
        "title": "☕ Tách Trà Thảo Mộc Bên Lò Sưởi Ấm",
        "theme": "Sưởi ấm tâm hồn & Xua tan mệt mỏi",
        "japanese_whisper": "温かいハーブティーを用意したわ。心穏やかに、朝までぐっすりお休み…坊や。",
        "romaji": "Atatakai haabu tii wo youi shita wa. Kokoro odayaka ni, asa made gussuri oyasumi... bouya.",
        "vietnamese_story": (
            "*Ta đã đặt sẵn một tách trà hoa cúc mật ong ấm áp bên cạnh lò sưởi cho cậu rồi.*\n"
            "*Hương hoa dịu nhẹ sẽ xua tan đi tất cả những mỏi mệt trong tâm trí cậu.*\n"
            "*Đừng suy nghĩ thêm điều gì nữa, đêm đã sâu rồi. Cậu xứng đáng được nghỉ ngơi trọn vẹn.*"
        ),
        "bedtime_tip": "Nhiệt độ phòng mát mẻ cùng ánh đèn vàng ấm sẽ giúp giấc ngủ sâu hơn."
    },
    {
        "id": "purple_breeze",
        "title": "🍃 Ngọn Gió Đêm Qua Rặng Hoa Tử Đằng",
        "theme": "Bảo hộ giấc mơ của Thất Vương",
        "japanese_whisper": "優しい風があなたの夢を守ってくれるわ。心配はいらないのよ、おやすみ。",
        "romaji": "Yasashii kaze ga anata no yume wo mamotte kureru wa. Shinpai wa iranai no yo, oyasumi.",
        "vietnamese_story": (
            "*Làn gió đêm mang theo hương thơm thoang thoảng của những chùm hoa tử đằng vương nhẹ qua ô cửa sổ.*\n"
            "*Có ma thuật của Thất Vương ở đây, không có bất kỳ cơn ác mộng nào có thể quấy rầy cậu.*\n"
            "*Cứ yên tâm ngủ một giấc thật ngon lành, ta sẽ luôn thức canh giữ sự bình yên cho cậu.*"
        ),
        "bedtime_tip": "Tắt bớt các thiết bị phát sáng xanh để não bộ thư giãn tự nhiên."
    },
    {
        "id": "seven_crowns_blessing",
        "title": "👑 Lời Chúc Giấc Mơ Đẹp Của Thất Vương",
        "theme": "Lời chúc ngủ ngon ngọt ngào quý phái",
        "japanese_whisper": "明日もまた新しい現実が始まるわ。だから今は…静かに瞳を閉じて。おやすみなさい、坊や。",
        "romaji": "Ashita mo mata atarashii genjitsu ga hajimaru wa. Dakara ima wa... shizuka ni hitomi wo tojite. Oyasuminasai, bouya.",
        "vietnamese_story": (
            "*Fufu... Một ngày dài đầy nỗ lực của cậu đã khép lại rồi.*\n"
            "*Ngày mai, một thực tại tươi sáng và ngập tràn ma lực kỳ diệu lại sẽ mở ra chào đón cậu.*\n"
            "*Còn bây giờ... Hãy ngoan ngoãn ngủ đi nhé, bé con của ta. Oyasumi.*"
        ),
        "bedtime_tip": "Mỗi ngày đều là một hành trình mới, hãy để giấc ngủ phục hồi toàn bộ năng lượng cho cậu."
    }
]


class SleepManager:
    """Quản lý tính năng Chế độ ru ngủ ban đêm của Neneka"""
    def __init__(self):
        pass

    def get_sleep_lullaby(self, theme_query: Optional[str] = None) -> Dict[str, Any]:
        """Chọn bài ru ngủ theo chủ đề hoặc ngẫu nhiên"""
        if theme_query:
            q = theme_query.lower()
            for l in SLEEP_LULLABIES:
                if any(k in q for k in [l["id"], l["title"].lower(), l["theme"].lower()]):
                    return l
                if "cừu" in q or "dem cuu" in q:
                    return SLEEP_LULLABIES[1]
                if "trà" in q or "tra" in q:
                    return SLEEP_LULLABIES[2]
                if "gió" in q or "gio" in q:
                    return SLEEP_LULLABIES[3]

        return random.choice(SLEEP_LULLABIES)

    async def generate_lullaby_audio(self, lullaby: Dict[str, Any]) -> Optional[str]:
        """Tạo file âm thanh giọng nói thì thầm tiếng Nhật của Neneka (cảm xúc Affectionate/dịu dàng)"""
        try:
            audio_path = await japanese_tts.generate_speech(
                lullaby["japanese_whisper"],
                emotion="Affectionate"
            )
            if audio_path and os.path.exists(audio_path):
                return audio_path
        except Exception as e:
            logger.error(f"Lỗi khi tạo audio ru ngủ: {e}")
        return None

    def create_sleep_embed(self, lullaby: Dict[str, Any], user_mention: str) -> discord.Embed:
        """Tạo Discord Embed sang trọng, êm dịu cho giấc ngủ ban đêm"""
        embed = discord.Embed(
            title=f"🌌 Chế Độ Ru Ngủ Đêm Khuya • {lullaby['title']}",
            description=f"*{lullaby['vietnamese_story']}*",
            color=0x2c3e50  # Xanh đen màn đêm huyền ảo
        )

        embed.add_field(
            name="🗣️ Lời Thì Thầm Tiếng Nhật (Japanese Whisper)",
            value=f"🇯🇵 **「{lullaby['japanese_whisper']}」**\n*({lullaby['romaji']})*",
            inline=False
        )

        embed.add_field(
            name="💜 Lời Dặn Của Thất Vương",
            value=f"*{lullaby['bedtime_tip']}*",
            inline=False
        )

        embed.set_footer(text="Seven Crowns Midnight Lullaby • Chúc bạn có một giấc ngủ thật ngon")
        return embed

    async def execute_sleep(
        self,
        user: discord.User | discord.Member,
        theme: Optional[str] = None,
        guild: Optional[discord.Guild] = None
    ) -> Tuple[discord.Embed, Optional[str], str]:
        """
        Thực hiện toàn bộ quy trình ru ngủ:
        - Chọn kịch bản ru ngủ
        - Sinh âm thanh tiếng Nhật thì thầm
        - Tự động phát trong Voice Channel nếu user đang ở trong Voice
        - Trả về (embed, audio_file, status_note)
        """
        lullaby = self.get_sleep_lullaby(theme)
        embed = self.create_sleep_embed(lullaby, user.mention)
        audio_file = await self.generate_lullaby_audio(lullaby)

        status_note = ""
        # Nếu user đang trong phòng thoại của guild
        if guild and isinstance(user, discord.Member) and user.voice and user.voice.channel:
            channel = user.voice.channel
            vc = voice_channel_mgr.get_voice_client(guild.id)
            if not vc or not vc.is_connected():
                success, msg, _ = await voice_channel_mgr.join_channel(channel)
                if success:
                    status_note = f"🔊 Neneka đã nhẹ nhàng ghé vào phòng thoại **{channel.name}** để thì thầm ru ngủ cùng cậu."
            else:
                status_note = f"🔊 Đang phát lời ru thì thầm trong phòng thoại **{channel.name}**."

            if audio_file:
                await voice_channel_mgr.enqueue_audio(guild.id, audio_file)

        return embed, audio_file, status_note


sleep_manager = SleepManager()

