# src/voice/piano_search.py
"""
Hệ Thống Tìm Kiếm & Tải Bản Nhạc Piano Đầy Đủ (Full-Length Game OST & Song Piano Search Engine):
Giải quyết triệt để 3 vấn đề:
1. Ưu tiên tuyệt đối đúng TÊN BÀI HÁT hoặc NHẠC GAME / ANIME OST phiên bản Solo Piano / Piano Cover
   (không lấy nhầm bài khác chỉ trùng 1 từ rời rạc như 'Lost Princess' -> 'The Lost People').
2. Tải TRỌN VẸN BÀI NHẠC ĐẦY ĐỦ (Full-Length MP3 128kbps từ YouTube Piano qua `yt-dlp` + `imageio-ffmpeg`,
   dài 1:30 – 8:00 phút) thay vì đoạn preview cụt 30 giây hay link hết hạn 892 bytes của Deezer!
3. Kiểm tra nghiêm ngặt chữ ký âm thanh thật (`is_valid_playable_audio_file`: kích thước >= 40KB, đúng header MP3/M4A/WAV,
   chặn tuyệt đối các file lỗi XML/HTML 892 bytes không phát ra tiếng).
"""

import asyncio
import hashlib
import logging
import os
import re
import subprocess
from typing import Dict, List, Optional, Any
from urllib.parse import quote_plus

import aiohttp

from src.voice.voice_channel import resolve_ffmpeg_executable

logger = logging.getLogger("Neneka.PianoSearch")

AUDIO_CACHE_DIR = os.path.abspath("audio_cache")
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

MIN_VALID_AUDIO_BYTES = 40_960           # Tối thiểu 40KB (chặn triệt để file lỗi XML/HTML 892 bytes!)
MAX_AUDIO_DOWNLOAD_BYTES = 16 * 1024 * 1024  # Tối đa 16MB để gửi mượt qua Discord Attachment
MIN_TRACK_DURATION_SEC = 35              # Bỏ qua các đoạn cắt quá ngắn (< 35s)
MAX_TRACK_DURATION_SEC = 660             # Bỏ qua các video gộp 1 tiếng (> 11 phút) để tải nhanh & vừa giới hạn MB Discord

PIANO_POSITIVE_KEYWORDS = (
    "piano", "ピアノ", "피아노", "dương cầm", "steinway", "synthesia",
    "animenz", "fonzi", "riyandi", "yiruma", "hisaishi", "chopin",
    "debussy", "beethoven", "mozart", "liszt", "satie", "rousseau", "kassia",
    "theishter", "marasy", "ru's piano", "pan piano", "halcyonmusic", "doopiano",
    "jnundead", "sudachi piano", "moripiano", "frank tedesco", "cateen",
)

GAME_AND_SONG_OST_KEYWORDS = (
    "ost", "soundtrack", "bgm", "theme", "op", "ed", "opening", "ending",
    "game", "anime", "genshin", "honkai", "star rail", "blue archive", "nikke",
    "princess connect", "priconne", "プリコネ", "arknights", "wuthering waves",
    "undertale", "zelda", "final fantasy", "nier", "persona", "touhou", "valorant", "lol",
)

NON_PIANO_NEGATIVE_KEYWORDS = (
    "1 hour", "10 hours", "3 hours", "2 hours", "compilation", "medley",
    "reaction", "gameplay", "walkthrough", "tutorial slow", "nightcore",
    "karaoke vocal", "podcast", "interview", "remix bass boosted",
)


def is_valid_playable_audio_file(file_path: Optional[str]) -> bool:
    """
    Kiểm tra nghiêm ngặt xem tệp âm thanh có thực sự phát được tiếng không:
    - Tồn tại và dung lượng >= 40KB (loại bỏ hoàn toàn lỗi file 892 bytes 0:00/0:00).
    - Không phải trang báo lỗi XML / HTML / JSON giả danh đuôi .mp3.
    - Có chữ ký định dạng âm thanh hợp lệ (ID3, MPEG frame sync, RIFF/WAV, ftyp/M4A, OggS).
    """
    if not file_path or not os.path.exists(file_path):
        return False
    try:
        size = os.path.getsize(file_path)
        if size < MIN_VALID_AUDIO_BYTES or size > MAX_AUDIO_DOWNLOAD_BYTES + 2 * 1024 * 1024:
            return False

        with open(file_path, "rb") as f:
            head = f.read(64)

        if len(head) < 16:
            return False

        # Chặn các trang báo lỗi XML / HTML / Access Denied bị lưu nhầm thành .mp3
        head_lower = head.lstrip().lower()
        for bad_prefix in (b"<?xml", b"<!doctype", b"<html", b"<error", b"<accessdenied", b'{"error'):
            if head_lower.startswith(bad_prefix):
                return False

        # Kiểm tra Magic Bytes chuẩn của các định dạng Audio
        if head.startswith(b"ID3"):
            return True
        if head.startswith(b"RIFF") and b"WAVE" in head[:16]:
            return True
        if b"ftyp" in head[:16]:  # M4A / MP4 audio
            return True
        if head.startswith((b"OggS", b"fLaC")) or head[:4] == b"\x1a\x45\xdf\xa3":
            return True
        # MPEG Audio Frame Sync (0xFF 0xE0..0xFF)
        if head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
            return True

        # Quét sâu thêm 4KB đầu nếu file MP3 có padding ở đầu
        with open(file_path, "rb") as f:
            chunk = f.read(4096)
        if b"ID3" in chunk or b"WAVEfmt" in chunk or b"ftyp" in chunk:
            return True
        for i in range(len(chunk) - 2):
            if chunk[i] == 0xFF and (chunk[i + 1] & 0xE0) == 0xE0:
                return True
    except Exception as e:
        logger.debug(f"Lỗi kiểm tra file audio '{file_path}': {e}")
    return False


def purge_corrupt_cached_audio():
    """Tự động dọn sạch các file cache hỏng (< 40KB, ví dụ file 892 bytes cũ) trong audio_cache."""
    try:
        for fname in os.listdir(AUDIO_CACHE_DIR):
            if fname.startswith(("piano_track_", "neneka_piano_", "yt_piano_")):
                fpath = os.path.join(AUDIO_CACHE_DIR, fname)
                if os.path.isfile(fpath) and not is_valid_playable_audio_file(fpath):
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass
    except Exception:
        pass


def clean_core_song_or_game_query(raw_query: str) -> str:
    """Trích xuất tên bài hát hoặc tên game gốc sạch sẽ từ câu lệnh của người dùng."""
    q = (raw_query or "").strip()
    q = re.sub(
        r"^(?:tìm\s+kiếm|tìm\s+bài\s+nhạc|tìm\s+nhạc|tìm\s+bài|mở\s+nhạc|mở\s+bài|phát\s+nhạc|phát\s+bài|bật\s+nhạc|cho\s+nghe|đánh\s+bài|chơi\s+bài|nhạc\s+piano\s+game|nhạc\s+game|bài\s+hát)\s+",
        "",
        q,
        flags=re.IGNORECASE,
    ).strip()
    q = re.sub(r"\b(?:tiếng\s+piano|bản\s+piano|bằng\s+piano|dương\s+cầm)\b", "", q, flags=re.IGNORECASE).strip()
    q = re.sub(r"\s+", " ", q).strip()
    return q


def build_piano_search_query(raw_query: str) -> str:
    """Xây dựng truy vấn tìm đúng bản Solo Piano / Piano Cover của tên bài hát hoặc nhạc Game."""
    core = clean_core_song_or_game_query(raw_query)
    if not core:
        return "anime game ost piano solo cover"
    if "piano" not in core.lower():
        return f"{core} piano"
    return core


def _is_genuine_piano_result(track: Dict[str, Any]) -> bool:
    """Đảm bảo kết quả thực sự là nhạc tiếng Piano và không phải video gộp 1-10 tiếng hay tạp âm."""
    title_l = (track.get("title") or "").lower()
    artist_l = (track.get("artist") or "").lower()
    album_l = (track.get("album") or "").lower()
    combined = f"{title_l} {artist_l} {album_l}"

    if any(bad in title_l for bad in NON_PIANO_NEGATIVE_KEYWORDS):
        return False

    dur = int(track.get("duration_sec") or 0)
    if dur and (dur < MIN_TRACK_DURATION_SEC or dur > MAX_TRACK_DURATION_SEC):
        return False

    return any(pk in combined for pk in PIANO_POSITIVE_KEYWORDS)


def _score_piano_relevance(track: Dict[str, Any], original_query: str) -> int:
    """
    Chấm điểm độ chuẩn xác:
    - Ưu tiên TUYỆT ĐỐI khớp cụm tên bài hát / tên game liền mạch (VD: 'Lost Princess' thắng tuyệt đối 'The Lost People ... Princess Mononoke').
    - Ưu tiên bản Full-Length (YouTube / Archive Full MP3) hơn đoạn cắt ngắn 30s.
    - Ưu tiên nhạc Game OST / Anime / Piano Solo Cover.
    """
    score = 0
    title_l = (track.get("title") or "").lower()
    artist_l = (track.get("artist") or "").lower()
    album_l = (track.get("album") or "").lower()
    combined = f"{title_l} {artist_l} {album_l}"

    # 1. Phải là tiếng đàn Piano thực sự
    if any(k in title_l for k in ("piano", "ピアノ", "피아노")):
        score += 40
    if any(k in title_l for k in ("piano solo", "solo piano", "piano cover", "piano arrangement", "piano ver")):
        score += 28
    if any(p in artist_l for p in PIANO_ARTIST_NAMES_LOWER):
        score += 22

    # 2. So khớp CHÍNH XÁC cụm tên bài hát / tên Game của người dùng
    core = re.sub(r"\bpiano\b", "", clean_core_song_or_game_query(original_query).lower()).strip()
    core_norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", core)).strip()
    title_norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title_l)).strip()
    combined_norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", combined)).strip()

    if core_norm:
        # Khớp nguyên cụm từ liền nhau trong tiêu đề bài hát -> Cộng điểm cực lớn (+130)!
        if core_norm in title_norm:
            score += 130
            if title_norm.startswith(core_norm):
                score += 25
        elif core_norm in combined_norm:
            score += 75
        else:
            # Kiểm tra tỷ lệ từ khóa có mặt (phạt nặng nếu thiếu từ chính của tên bài!)
            q_words = [w for w in core_norm.split() if len(w) >= 2]
            if q_words:
                matched_in_title = sum(1 for w in q_words if w in title_norm.split())
                matched_anywhere = sum(1 for w in q_words if w in combined_norm)
                if matched_in_title == len(q_words):
                    score += 65
                elif matched_anywhere == len(q_words):
                    score += 35
                else:
                    # Thiếu từ khóa trong tên bài -> trừ điểm nặng để không lấy nhầm bài khác!
                    score -= 60

    # 3. Ưu tiên nhạc Game OST / Anime OST / Bản Full
    if any(gk in combined for gk in GAME_AND_SONG_OST_KEYWORDS):
        score += 20
    if "full" in title_l:
        score += 15
    if track.get("is_full_track"):
        score += 55  # Ưu tiên bản Full bài (2-5 phút) vượt trội hoàn toàn so với preview 30s!

    if any(bad in title_l for bad in NON_PIANO_NEGATIVE_KEYWORDS):
        score -= 120

    return score


PIANO_ARTIST_NAMES_LOWER = (
    "piano", "animenz", "fonzi", "riyandi", "yiruma", "hisaishi", "chopin",
    "debussy", "beethoven", "mozart", "liszt", "satie", "rousseau", "kassia",
    "theishter", "marasy", "ru's piano", "pan piano", "halcyon", "doopiano",
    "jnundead", "sudachi", "moripiano", "frank tedesco", "cateen",
)


async def _search_youtube_full_piano(raw_query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Tìm kiếm các bản nhạc Piano ĐẦY ĐỦ (Full-Length) chuẩn xác cho mọi bài hát & nhạc Game trên YouTube qua `yt-dlp`.
    """
    core = clean_core_song_or_game_query(raw_query)
    search_term = f"{core} piano cover" if "piano" not in core.lower() else f"{core} solo"

    def _sync_yt_search() -> List[Dict[str, Any]]:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{search_term}", download=False)
            entries = (info or {}).get("entries") or []
            out: List[Dict[str, Any]] = []
            for e in entries:
                if not e or not e.get("id"):
                    continue
                vid = e["id"]
                dur = int(e.get("duration") or 0)
                if dur and (dur < MIN_TRACK_DURATION_SEC or dur > MAX_TRACK_DURATION_SEC):
                    continue
                title = e.get("title") or "Piano Arrangement"
                uploader = e.get("uploader") or e.get("channel") or "Piano Artist"
                thumbs = e.get("thumbnails") or []
                thumb_url = thumbs[-1].get("url") if thumbs else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                watch_url = f"https://www.youtube.com/watch?v={vid}"
                out.append({
                    "source": "YouTube Piano (Full Track)",
                    "yt_id": vid,
                    "title": title,
                    "artist": uploader,
                    "album": "Full Solo Piano Performance",
                    "duration_sec": dur,
                    "audio_url": watch_url,
                    "audio_ext": "mp3",
                    "page_url": watch_url,
                    "youtube_url": watch_url,
                    "artwork_url": thumb_url,
                    "is_full_track": True,
                })
            return out

    try:
        return await asyncio.wait_for(asyncio.to_thread(_sync_yt_search), timeout=10.0)
    except Exception as e:
        logger.warning(f"YouTube Piano search lỗi nhẹ ({e}), dùng kho dự phòng.")
        return []


async def _search_itunes(session: aiohttp.ClientSession, query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Kho dự phòng Apple Music / iTunes (chỉ dùng khi YouTube không truy cập được)."""
    url = f"https://itunes.apple.com/search?term={quote_plus(query)}&media=music&entity=song&limit={limit}"
    results: List[Dict[str, Any]] = []
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            for item in data.get("results", []):
                preview = item.get("previewUrl")
                if not preview:
                    continue
                title = item.get("trackName") or "Piano Piece"
                artist = item.get("artistName") or "Unknown Pianist"
                art = (item.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
                ext = "mp3" if preview.lower().endswith(".mp3") else "m4a"
                dur_ms = int(item.get("trackTimeMillis") or 0)
                results.append({
                    "source": "Apple Music Piano",
                    "title": title,
                    "artist": artist,
                    "album": item.get("collectionName") or "",
                    "duration_sec": dur_ms // 1000 if dur_ms else 0,
                    "audio_url": preview,
                    "audio_ext": ext,
                    "page_url": item.get("trackViewUrl") or f"https://www.youtube.com/results?search_query={quote_plus(title + ' ' + artist + ' piano')}",
                    "youtube_url": f"https://www.youtube.com/results?search_query={quote_plus(title + ' ' + artist + ' piano')}",
                    "artwork_url": art,
                    "is_full_track": False,
                })
    except Exception as e:
        logger.debug(f"iTunes piano search lỗi nhẹ: {e}")
    return results


async def _search_deezer(session: aiohttp.ClientSession, query: str, limit: int = 6) -> List[Dict[str, Any]]:
    """Kho phụ trợ Deezer (đã gắn kiểm tra chống file 892 bytes hết hạn khi tải)."""
    url = f"https://api.deezer.com/search?q={quote_plus(query)}&limit={limit}"
    results: List[Dict[str, Any]] = []
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            for item in data.get("data", []):
                preview = item.get("preview")
                if not preview:
                    continue
                title = item.get("title") or "Piano Track"
                artist = (item.get("artist") or {}).get("name") or "Unknown Pianist"
                album_obj = item.get("album") or {}
                results.append({
                    "source": "Deezer Piano",
                    "title": title,
                    "artist": artist,
                    "album": album_obj.get("title") or "",
                    "duration_sec": int(item.get("duration") or 0),
                    "audio_url": preview,
                    "audio_ext": "mp3",
                    "page_url": item.get("link") or "",
                    "youtube_url": f"https://www.youtube.com/results?search_query={quote_plus(title + ' ' + artist + ' piano')}",
                    "artwork_url": album_obj.get("cover_big") or album_obj.get("cover_medium") or "",
                    "is_full_track": False,
                })
    except Exception as e:
        logger.debug(f"Deezer piano search lỗi nhẹ: {e}")
    return results


async def _search_internet_archive_full_piano(
    session: aiohttp.ClientSession, query: str, limit: int = 3
) -> List[Dict[str, Any]]:
    """Kho nhạc Piano cổ điển Full-Length từ Internet Archive."""
    clean_q = re.sub(r'["\'()]', " ", query).strip()
    ia_q = f"mediatype:(audio) AND format:(VBR MP3) AND (piano) AND ({clean_q})"
    url = (
        f"https://archive.org/advancedsearch.php?q={quote_plus(ia_q)}"
        f"&fl[]=identifier,title,creator&rows={limit}&page=1&output=json"
    )
    results: List[Dict[str, Any]] = []
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            docs = (data.get("response") or {}).get("docs") or []
            for doc in docs[:2]:
                ident = doc.get("identifier")
                if not ident:
                    continue
                meta_url = f"https://archive.org/metadata/{ident}"
                async with session.get(meta_url) as m_resp:
                    if m_resp.status != 200:
                        continue
                    m_data = await m_resp.json(content_type=None)
                    files = m_data.get("files") or []
                    mp3_file = None
                    for f in files:
                        fname = f.get("name") or ""
                        fsize = int(f.get("size") or 0)
                        if fname.lower().endswith(".mp3") and MIN_VALID_AUDIO_BYTES < fsize <= MAX_AUDIO_DOWNLOAD_BYTES:
                            mp3_file = f
                            break
                    if not mp3_file:
                        continue
                    fname = mp3_file["name"]
                    title = mp3_file.get("title") or doc.get("title") or fname
                    creator = doc.get("creator")
                    if isinstance(creator, list):
                        creator = ", ".join(creator)
                    artist = creator or "Solo Piano Archive"
                    try:
                        dur_sec = int(float(mp3_file.get("length") or "0"))
                    except ValueError:
                        dur_sec = 0
                    results.append({
                        "source": "Internet Archive (Full Piano MP3)",
                        "title": str(title),
                        "artist": str(artist),
                        "album": str(doc.get("title") or "Open Piano Collection"),
                        "duration_sec": dur_sec,
                        "audio_url": f"https://archive.org/download/{ident}/{quote_plus(fname).replace('+', '%20')}",
                        "audio_ext": "mp3",
                        "page_url": f"https://archive.org/details/{ident}",
                        "youtube_url": f"https://www.youtube.com/results?search_query={quote_plus(str(title) + ' piano')}",
                        "artwork_url": f"https://archive.org/services/img/{ident}",
                        "is_full_track": True,
                    })
    except Exception as e:
        logger.debug(f"Internet Archive piano search lỗi nhẹ: {e}")
    return results


async def search_piano_songs(raw_query: str, limit: int = 6) -> List[Dict[str, Any]]:
    """
    Tìm kiếm các bản nhạc tiếng Piano chuẩn xác cho Nhạc Game & Bài Hát:
    - Ưu tiên số 1: YouTube Full-Length Piano Covers (`_search_youtube_full_piano` — trọn bài 2-6 phút).
    - Nguồn dự phòng song song: Internet Archive Full Piano, Apple Music / iTunes, Deezer.
    - Lọc bỏ các bài không phải tiếng đàn Piano và xếp hạng khớp chính xác tên bài / tên Game lên đầu!
    """
    purge_corrupt_cached_audio()
    piano_query = build_piano_search_query(raw_query)
    timeout = aiohttp.ClientTimeout(total=6.5)
    headers = {"User-Agent": "Mozilla/5.0 NenekaPianoBot/3.0"}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        yt_res, ia_res, itunes_res, deezer_res = await asyncio.gather(
            _search_youtube_full_piano(raw_query, limit=8),
            _search_internet_archive_full_piano(session, raw_query or piano_query, limit=2),
            _search_itunes(session, piano_query, limit=6),
            _search_deezer(session, piano_query, limit=5),
            return_exceptions=True,
        )

    merged: List[Dict[str, Any]] = []
    for batch in (yt_res, ia_res, itunes_res, deezer_res):
        if isinstance(batch, list):
            merged.extend(batch)

    # Chỉ giữ lại các bản thực sự là nhạc tiếng Piano (nếu lọc xong rỗng mới nới lỏng)
    strict_piano = [t for t in merged if _is_genuine_piano_result(t)]
    candidates = strict_piano if strict_piano else merged

    deduped: List[Dict[str, Any]] = []
    seen_keys = set()
    for t in candidates:
        norm_key = (
            re.sub(r"\W+", "", (t.get("title") or "").lower())[:32],
            re.sub(r"\W+", "", (t.get("artist") or "").lower())[:18],
        )
        if norm_key in seen_keys:
            continue
        seen_keys.add(norm_key)
        t["relevance_score"] = _score_piano_relevance(t, raw_query)
        deduped.append(t)

    deduped.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return deduped[: max(1, limit)]


def _download_youtube_to_mp3_sync(watch_url: str, target_mp3_path: str) -> Optional[str]:
    """
    Tải trọn vẹn bản nhạc Piano từ YouTube bằng `yt-dlp` và xuất ra chuẩn `.mp3` 128kbps Stereo
    nhờ binary FFmpeg tích hợp sẵn (`imageio-ffmpeg`) để phát mượt 100% trên mọi thiết bị Discord!
    """
    import yt_dlp

    ffmpeg_exe = resolve_ffmpeg_executable()
    temp_base = target_mp3_path[:-4] if target_mp3_path.lower().endswith(".mp3") else target_mp3_path

    ydl_opts: Dict[str, Any] = {
        "format": "bestaudio[filesize<15M]/bestaudio/best[filesize<16M]",
        "outtmpl": f"{temp_base}_raw.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 12,
    }

    downloaded_raw = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(watch_url, download=True)
            downloaded_raw = ydl.prepare_filename(info)

        if not downloaded_raw or not os.path.exists(downloaded_raw):
            return None

        # Chuyển sang chuẩn .mp3 bằng FFmpeg tích hợp để Discord hiển thị thanh phát nhạc đầy đủ thời lượng!
        if ffmpeg_exe:
            cmd = [
                ffmpeg_exe,
                "-y",
                "-i", downloaded_raw,
                "-vn",
                "-acodec", "libmp3lame",
                "-b:a", "128k",
                "-ar", "44100",
                "-ac", "2",
                target_mp3_path,
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=35, check=False)
            try:
                if os.path.exists(downloaded_raw) and downloaded_raw != target_mp3_path:
                    os.remove(downloaded_raw)
            except OSError:
                pass
            if is_valid_playable_audio_file(target_mp3_path):
                return target_mp3_path

        # Nếu không có FFmpeg nhưng file gốc là .m4a hợp lệ
        if is_valid_playable_audio_file(downloaded_raw):
            return downloaded_raw
    except Exception as e:
        logger.warning(f"yt-dlp tải nhạc Piano lỗi ({watch_url}): {e}")
        if downloaded_raw and os.path.exists(downloaded_raw):
            try:
                os.remove(downloaded_raw)
            except OSError:
                pass
    return None


async def download_piano_track_audio(track: Dict[str, Any]) -> Optional[str]:
    """
    Tải file âm thanh đầy đủ & kiểm định chất lượng thật (>= 40KB, đúng header âm thanh, không bao giờ gửi file lỗi 892 bytes).
    """
    audio_url = track.get("audio_url")
    if not audio_url:
        return None

    digest = hashlib.md5(audio_url.encode("utf-8")).hexdigest()[:12]

    # 1. Nếu là bản Full-Length từ YouTube Piano -> dùng yt-dlp + bundled FFmpeg xuất ra .mp3 trọn bài!
    if "youtube.com/" in audio_url or "youtu.be/" in audio_url or track.get("yt_id"):
        yt_mp3_path = os.path.join(AUDIO_CACHE_DIR, f"yt_piano_{digest}.mp3")
        if is_valid_playable_audio_file(yt_mp3_path):
            return yt_mp3_path
        res_path = await asyncio.to_thread(_download_youtube_to_mp3_sync, audio_url, yt_mp3_path)
        if is_valid_playable_audio_file(res_path):
            track["audio_ext"] = "mp3" if res_path.lower().endswith(".mp3") else "m4a"
            return res_path
        return None

    # 2. Tải HTTP trực tiếp (Internet Archive Full MP3 / iTunes M4A / Deezer) kèm kiểm định chống file 892 bytes!
    ext = track.get("audio_ext") or "mp3"
    file_path = os.path.join(AUDIO_CACHE_DIR, f"piano_track_{digest}.{ext}")

    if is_valid_playable_audio_file(file_path):
        return file_path

    timeout = aiohttp.ClientTimeout(total=15.0)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NenekaPianoBot/3.0"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(audio_url) as resp:
                if resp.status != 200:
                    return None
                ctype = (resp.headers.get("Content-Type") or "").lower()
                # Chặn sớm nếu server trả về trang báo lỗi XML/HTML thay vì audio!
                if any(bad in ctype for bad in ("text/html", "application/xml", "text/xml", "application/json")):
                    logger.warning(f"Bỏ qua link audio hết hạn trả về {ctype}: {audio_url}")
                    return None

                data = await resp.content.read(MAX_AUDIO_DOWNLOAD_BYTES + 1)
                if not data or len(data) < MIN_VALID_AUDIO_BYTES or len(data) > MAX_AUDIO_DOWNLOAD_BYTES:
                    logger.warning(f"Bỏ qua file audio không hợp lệ ({len(data) if data else 0} bytes): {audio_url}")
                    return None

                with open(file_path, "wb") as f:
                    f.write(data)

                # Nếu là file .m4a (ví dụ từ iTunes) và có FFmpeg, chuyển luôn sang .mp3 để phát mượt 100% trên mọi Discord!
                ffmpeg_exe = resolve_ffmpeg_executable()
                if file_path.lower().endswith(".m4a") and ffmpeg_exe:
                    mp3_converted = os.path.join(AUDIO_CACHE_DIR, f"piano_track_{digest}.mp3")
                    await asyncio.to_thread(
                        subprocess.run,
                        [ffmpeg_exe, "-y", "-i", file_path, "-vn", "-acodec", "libmp3lame", "-b:a", "128k", mp3_converted],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=20,
                    )
                    if is_valid_playable_audio_file(mp3_converted):
                        try:
                            os.remove(file_path)
                        except OSError:
                            pass
                        track["audio_ext"] = "mp3"
                        return mp3_converted

                if is_valid_playable_audio_file(file_path):
                    return file_path
                else:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
    except Exception as e:
        logger.warning(f"Không thể tải audio từ '{audio_url}': {e}")

    return None


def format_duration_mmss(seconds: int) -> str:
    if not seconds or seconds <= 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"
