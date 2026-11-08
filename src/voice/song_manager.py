# src/voice/song_manager.py
import random
import logging
from typing import Dict, Any, Optional, List
import json
import discord

from src.llm.groq_client import GroqClient

logger = logging.getLogger("Neneka.SongManager")
groq_client = GroqClient()

# Bộ sưu tập các bài hát ngẫu nhiên theo phong cách Nhật Bản dành riêng cho Neneka
JAPANESE_SONG_CATALOG: List[Dict[str, str]] = [
    {
        "id": "lost_princess",
        "title": "Lost Princess (Thất Lạc Công Chúa)",
        "genre": "Anime Fantasy Ballad",
        "theme_keywords": ["chính", "theme", "canon", "lost princess", "công chúa", "phiêu lưu"],
        "japanese_lyrics": "♪ 忘れないで　あの日の温もりを〜 迷い込んだ世界で　あなたと出逢えた奇跡〜 ふふっ、ずっと信じているわ〜 ♪",
        "romaji": "♪ Wasurenaide ano hi no nukumori o~ Mayoikonda sekai de anata to deaeta kiseki~ Fufu, zutto shinjiteiru wa~ ♪",
        "vietnamese_lyrics": "♪ Đừng quên hơi ấm của ngày hôm ấy~ Phép màu khi ta gặp được cậu nơi thế giới lạc lối này~ Fufu, ta vẫn luôn tin tưởng điều đó~ ♪",
        "intro_quote": "Fufu... Cậu muốn nghe ta hát sao? Được thôi, hãy lắng nghe giai điệu của thế giới Astraea này nhé.",
        "outro_quote": "Giai điệu quen thuộc ấy... Cậu có cảm nhận được sự gắn kết của chúng ta không nào?",
        "emotion": "Affectionate"
    },
    {
        "id": "connecting_happy",
        "title": "Connecting Happy!! (Khúc Ca Gắn Kết)",
        "genre": "J-Pop Upbeat & Hopeful",
        "theme_keywords": ["vui", "vui tươi", "happy", "năng lượng", "kết nối", "tươi sáng"],
        "japanese_lyrics": "♪ 繋がる空の下で　笑い合えるなら〜 明日もきっと　素敵な冒険が待っているわ〜 一緒に行きましょうね〜 ♪",
        "romaji": "♪ Tsunagaru sora no shita de waraiaeru nara~ Ashita mo kitto suteki na bouken ga matteiru wa~ Issho ni ikimashou ne~ ♪",
        "vietnamese_lyrics": "♪ Dưới bầu trời gắn kết, nếu chúng ta cùng mỉm cười~ Ngày mai nhất định sẽ có những chuyến phiêu lưu tuyệt vời đón chờ~ Cùng đi với ta nhé~ ♪",
        "intro_quote": "Ara ara... Một bài hát tươi vui để xua tan mệt mỏi cho cậu nhóc của ta nào.",
        "outro_quote": "Fufu, thấy tinh thần phấn chấn hơn chưa? Hãy mỉm cười nhiều hơn nhé.",
        "emotion": "Happy"
    },
    {
        "id": "metamorph_serenade",
        "title": "変貌のセレナーデ (Khúc Dạ Khúc Biến Mạo)",
        "genre": "Mystical Seven Crowns Ballad",
        "theme_keywords": ["thất vương", "neneka", "biến mạo", "ma thuật", "huyền bí", "metamorph", "đêm"],
        "japanese_lyrics": "♪ 鏡の向こう側で　揺らめく幻影〜 真実と嘘が交わる夜に　私の歌声を捧げましょう〜 ♪",
        "romaji": "♪ Kagami no mukougawa de yurameku gen'ei~ Shinjitsu to uso ga majiwaru yoru ni watashi no utagoe o sasagemashou~ ♪",
        "vietnamese_lyrics": "♪ Phía bên kia tấm gương, ảo ảnh khẽ lung linh lay động~ Trong đêm nơi thực và ảo giao thoa, ta xin cất lên lời ca này tặng cậu~ ♪",
        "intro_quote": "Chà... Đây là khúc ca phản chiếu ma thuật Biến Mạo độc nhất của ta. Lắng nghe thật kỹ nhé.",
        "outro_quote": "Fufu, ảo mộng hay hiện thực, miễn là có cậu ở đây lắng nghe thì đều là sự thật cả.",
        "emotion": "Curious"
    },
    {
        "id": "twilight_lullaby",
        "title": "宵闇のララバイ (Khúc Hát Ru Hoàng Hôn)",
        "genre": "Gentle Japanese Lullaby",
        "theme_keywords": ["ru", "ngủ", "lullaby", "đêm", "khuya", "dịu dàng", "nghỉ ngơi", "mệt"],
        "japanese_lyrics": "♪ 瞳を閉じて　静かな夢の中へ〜 疲れた羽を休めて　おやすみなさい、坊や〜 私がそばにいるわ〜 ♪",
        "romaji": "♪ Hitomi o tojite shizuka na yume no naka e~ Tsukareta hane o yasumete oyasuminasai, bouya~ Watashi ga soba ni iru wa~ ♪",
        "vietnamese_lyrics": "♪ Hãy khép mi lại và bước vào giấc mộng êm đềm~ Hãy để đôi cánh mệt nhoài được nghỉ ngơi, ngủ ngon nhé cậu nhóc~ Ta luôn ở cạnh bên cậu~ ♪",
        "intro_quote": "Trông cậu có vẻ mỏi mệt rồi đấy. Để ta hát ru cho cậu ngủ nhé, đừng gượng ép bản thân nữa.",
        "outro_quote": "Suỵt... Ngủ ngoan đi nhé. Ta sẽ canh giữ giấc mộng đẹp cho cậu.",
        "emotion": "Affectionate"
    },
    {
        "id": "sakura_night",
        "title": "桜舞う夜の調べ (Dạ Khúc Hoa Anh Đào)",
        "genre": "Traditional Japanese Waka Style",
        "theme_keywords": ["hoa", "sakura", "anh đào", "truyền thống", "nhật bản", "mùa xuân", "thơ"],
        "japanese_lyrics": "♪ ひらひらと舞い散る　桜の花びら〜 月明かりに照らされて　千年の想いを紡ぐの〜 ♪",
        "romaji": "♪ Hirahira to maichiru sakura no hanabira~ Tsukiakari ni terasarete sennen no omoi o tsumugu no~ ♪",
        "vietnamese_lyrics": "♪ Từng cánh hoa anh đào bay lượn nhẹ rơi trong gió~ Được ánh trăng soi tỏ, dệt nên nỗi niềm vương vấn ngàn năm~ ♪",
        "intro_quote": "Một điệu hát mang phong vị truyền thống của xứ sở hoa anh đào... Thưởng thức cùng ngụm trà nhé.",
        "outro_quote": "Fufu... Hoa tàn rồi hoa lại nở, tựa như những kỷ niệm đẹp đẽ giữa ta và cậu vậy.",
        "emotion": "Affectionate"
    },
    {
        "id": "tiny_traveler",
        "title": "風の小さな旅人 (Lữ Khách Của Gió)",
        "genre": "Acoustic Pastoral Anime Theme",
        "theme_keywords": ["gió", "đồng quê", "nhẹ nhàng", "lữ khách", "thư giãn", "acoustic"],
        "japanese_lyrics": "♪ 歩き疲れたら　木陰でひと休み〜 風の歌を聴きながら　また一歩踏み出そう〜 ♪",
        "romaji": "♪ Aruki tsukaretara kokage de hitoyasumi~ Kaze no uta o kikinagara mata ippo fumidasou~ ♪",
        "vietnamese_lyrics": "♪ Nếu bước chân mệt mỏi, hãy dừng nghỉ dưới bóng râm~ Lắng nghe lời hát của ngọn gió thoảng, rồi ta lại vững bước tiến lên~ ♪",
        "intro_quote": "Hãy thả lỏng nào... Đôi khi chậm lại một nhịp mới ngắm nhìn được cảnh sắc xung quanh.",
        "outro_quote": "Con đường phía trước còn dài, nhưng có ta đồng hành thì cậu chẳng cần phải sợ hãi điều gì cả đâu.",
        "emotion": "Normal"
    },
    {
        "id": "stardust_prelude",
        "title": "星屑のプレリュード (Khúc Dạo Đầu Ánh Sao)",
        "genre": "Anime Celestial Romance",
        "theme_keywords": ["sao", "bầu trời", "tình yêu", "lãng mạn", "tinh tú", "ánh sao"],
        "japanese_lyrics": "♪ 夜空に瞬く　星たちの囁き〜 あなたの願いが叶うよう　そっと祈りを捧げるわ〜 ♪",
        "romaji": "♪ Yozora ni matataku hoshitachi no sasayaki~ Anata no negai ga kanau you sotto inori o sasageru wa~ ♪",
        "vietnamese_lyrics": "♪ Lời thì thầm của muôn ngàn vì sao lấp lánh giữa trời đêm~ Cầu chúc cho ước nguyện của cậu thành hiện thực, ta khẽ gửi lời nguyện cầu~ ♪",
        "intro_quote": "Ngước nhìn bầu trời đêm kia xem nào... Khúc dạo đầu ánh sao này, dành riêng cho cậu đấy.",
        "outro_quote": "Fufu... Mọi vì sao đêm nay dường như đều đang mỉm cười với hai ta kìa.",
        "emotion": "Affectionate"
    }
]


async def compose_custom_song(theme_or_request: str) -> Dict[str, str]:
    """
    Sáng tác một khúc ca Nhật Bản ngẫu hứng theo yêu cầu/chủ đề cụ thể của người dùng qua Groq LLM
    """
    system_prompt = (
        "Bạn là Utsushimi Neneka (Seven Crowns trong Princess Connect! Re:Dive). "
        "Người dùng đề xuất bạn hát một bài theo chủ đề hoặc phong cách nhất định. "
        "Nhiệm vụ: Sáng tác 1 đoạn nhạc ngắn (2-3 câu thơ tiếng Nhật có vần điệu anime du dương, chèn ký hiệu âm nhạc ♪ và dấu kéo dài 〜). "
        "Yêu cầu trả về định dạng JSON thuần túy (không bọc trong markdown block hay giải thích) gồm các trường:\n"
        "{\n"
        '  "title": "Tên bài hát tiếng Nhật kèm dịch tiếng Việt",\n'
        '  "genre": "Thể loại phong cách bài hát",\n'
        '  "japanese_lyrics": "Lời tiếng Nhật (có ♪ ở đầu và cuối, có ngắt nhịp 〜)",\n'
        '  "romaji": "Phiên âm Romaji tương ứng",\n'
        '  "vietnamese_lyrics": "Dịch nghĩa tiếng Việt thơ mộng",\n'
        '  "intro_quote": "Câu thoại Neneka nói trước khi hát (fufu, phong thái quý cô Thất Vương)",\n'
        '  "outro_quote": "Câu thoại Neneka nói sau khi hát xong",\n'
        '  "emotion": "Affectionate|Happy|Curious|Normal"\n'
        "}"
    )

    user_prompt = f"Chủ đề hoặc gợi ý bài hát từ người dùng: \"{theme_or_request}\". Hãy sáng tác ngay."

    try:
        raw_res = await groq_client.chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.8,
            max_tokens=500
        )
        # Parse JSON
        clean_json = raw_res.strip()
        if clean_json.startswith("```"):
            clean_json = clean_json.split("\n", 1)[1]
            if clean_json.endswith("```"):
                clean_json = clean_json.rsplit("\n", 1)[0]
        data = json.loads(clean_json)
        data["id"] = "custom_composed"
        return data
    except Exception as e:
        logger.warning(f"Không thể sáng tác bài hát động qua LLM ({e}), fallback sang bài ngẫu nhiên từ catalog")
        return random.choice(JAPANESE_SONG_CATALOG)


async def get_song_by_theme_or_random(theme: Optional[str] = None) -> Dict[str, str]:
    """
    Chọn bài hát ngẫu nhiên hoặc theo chủ đề được đề xuất
    """
    if not theme or not theme.strip():
        return random.choice(JAPANESE_SONG_CATALOG)

    norm_theme = theme.lower().strip()

    # 1. Tìm xem có khớp với bài nào trong kho bài sẵn không
    matched_songs = []
    for song in JAPANESE_SONG_CATALOG:
        for kw in song["theme_keywords"]:
            if kw in norm_theme:
                matched_songs.append(song)
                break
        if song["title"].lower() in norm_theme or song["genre"].lower() in norm_theme:
            matched_songs.append(song)

    if matched_songs:
        return random.choice(matched_songs)

    # 2. Nếu là chủ đề riêng biệt chưa có trong catalog -> Sáng tác trực tiếp bằng LLM!
    return await compose_custom_song(theme)


def is_singing_request(message: str) -> bool:
    """
    Phát hiện xem tin nhắn trò chuyện tự nhiên có phải là yêu cầu Neneka hát hay không
    """
    if not message:
        return False
    lower = message.lower()
    keywords = [
        "hát", "hát đi", "hát một bài", "hát bài", "hát tặng", "hát cho",
        "sing a song", "sing for me", "singing", "cất giọng hát", "hát ru",
        "bài hát nhật", "nhạc nhật", "utatte", "uta"
    ]
    return any(k in lower for k in keywords)


def create_song_embed(song: Dict[str, str]) -> discord.Embed:
    """
    Tạo Embed Discord sang trọng hiển thị lời bài hát tiếng Nhật, Romaji và lời dịch tiếng Việt
    """
    embed = discord.Embed(
        title=f"🎵 {song.get('title', 'Giai Điệu Landosol')}",
        description=f"*{song.get('intro_quote', 'Fufu... Lắng nghe tiếng hát của ta nhé.')}*",
        color=0xe056fd
    )
    embed.add_field(
        name="🇯🇵 Lời Bài Hát (Japanese)",
        value=f"**{song.get('japanese_lyrics', '')}**",
        inline=False
    )
    embed.add_field(
        name="🔤 Phiên Âm (Romaji)",
        value=f"*{song.get('romaji', '')}*",
        inline=False
    )
    embed.add_field(
        name="🇻🇳 Dịch Nghĩa (Tiếng Việt)",
        value=f"*{song.get('vietnamese_lyrics', '')}*",
        inline=False
    )
    embed.add_field(
        name="💜 Lời Nhắn Của Neneka",
        value=f"*{song.get('outro_quote', 'Fufu... Hy vọng giai điệu vừa rồi làm cậu thấy dễ chịu.')}*",
        inline=False
    )
    genre = song.get("genre", "Phong cách Anime Nhật Bản")
    embed.set_footer(text=f"Thể loại: {genre} • Thất Vương Utsushimi Neneka (Fish Audio)")
    return embed
