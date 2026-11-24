# src/utils/media_extractor.py
"""
Bộ trích xuất đa phương tiện cho Discord Message:
1. Đọc file code / văn bản đính kèm (.py, .js, .ts, .html, .css, .json, .cpp, .java, .sql, .log, ...)
2. Nhận diện ý định đọc/viết code (Coding Intent Detection)
3. Đọc ảnh tĩnh & ảnh động GIF (File .gif, link Tenor, Giphy, Discord CDN, Embeds, Stickers)
4. Chia nhỏ câu trả lời chứa code dài (> 2000 ký tự) mà không làm vỡ khối ```code``` trên Discord
"""

import io
import os
import re
import logging
from typing import List, Dict, Optional, Tuple
import aiohttp

logger = logging.getLogger("Neneka.MediaExtractor")

# Ánh xạ đuôi file sang ngôn ngữ Markdown code fence
CODE_EXTENSION_MAP: Dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".md": "markdown",
    ".txt": "text",
    ".log": "log",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".bat": "bat",
    ".cmd": "bat",
    ".ps1": "powershell",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".lua": "lua",
    ".r": "r",
    ".xml": "xml",
    ".csv": "csv",
    ".vue": "vue",
    ".svelte": "svelte",
    ".dart": "dart",
    ".prisma": "prisma",
    ".graphql": "graphql",
    ".dockerfile": "dockerfile",
}

SPECIAL_CODE_FILENAMES = {
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "procfile": "yaml",
    "requirements.txt": "text",
    "package.json": "json",
    "tsconfig.json": "json",
    ".env.example": "ini",
    ".gitignore": "text",
}

MAX_CODE_FILE_BYTES = 45_000   # ~45KB mỗi file
MAX_CODE_CHARS_IN_PROMPT = 18_000
MAX_CODE_FILES_PER_MESSAGE = 3
MAX_GIF_DOWNLOAD_BYTES = 8 * 1024 * 1024  # 8MB

# Regex nhận diện URL GIF phổ biến trên Discord (Tenor, Giphy, Discord CDN, Imgur)
GIF_URL_REGEX = re.compile(
    r"(https?://(?:[\w\-]+\.)?(?:tenor\.com|giphy\.com|imgur\.com|discordapp\.com|discordapp\.net|gifer\.com)/[^\s<>\"']+)",
    re.IGNORECASE,
)


def get_code_language_for_filename(filename: str, content_type: Optional[str] = None) -> Optional[str]:
    """Xác định xem attachment có phải là file code/text không và trả về tên ngôn ngữ."""
    if not filename:
        return None
    lower_name = filename.lower().strip()
    if lower_name in SPECIAL_CODE_FILENAMES:
        return SPECIAL_CODE_FILENAMES[lower_name]

    _, ext = os.path.splitext(lower_name)
    if ext in CODE_EXTENSION_MAP:
        return CODE_EXTENSION_MAP[ext]

    if content_type:
        ct = content_type.lower().split(";")[0].strip()
        if ct.startswith("text/") or ct in {
            "application/json",
            "application/javascript",
            "application/x-javascript",
            "application/typescript",
            "application/xml",
            "application/x-sh",
            "application/x-python-code",
        }:
            return ext.lstrip(".") or "text"

    return None


def decode_code_bytes(raw: bytes) -> str:
    """Giải mã an toàn nội dung file code từ bytes sang chuỗi."""
    for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


async def extract_code_attachments(message) -> List[Dict[str, str]]:
    """
    Trích xuất các tệp code/văn bản từ tin nhắn hiện tại (và tin nhắn được reply nếu có).
    Trả về list các dict: {"filename": str, "language": str, "content": str, "truncated": bool}
    """
    candidates = []
    if getattr(message, "attachments", None):
        candidates.extend(message.attachments)

    # Nếu người dùng reply vào một tin nhắn chứa file code
    ref = getattr(message, "reference", None)
    resolved = getattr(ref, "resolved", None) if ref else None
    if resolved and getattr(resolved, "attachments", None):
        for att in resolved.attachments:
            if att not in candidates:
                candidates.append(att)

    extracted: List[Dict[str, str]] = []
    for att in candidates:
        if len(extracted) >= MAX_CODE_FILES_PER_MESSAGE:
            break
        filename = getattr(att, "filename", "") or ""
        ctype = getattr(att, "content_type", None)
        # Bỏ qua ảnh/âm thanh/video
        if ctype and any(ctype.lower().startswith(p) for p in ("image/", "audio/", "video/")):
            continue

        lang = get_code_language_for_filename(filename, ctype)
        if not lang:
            continue

        try:
            size = getattr(att, "size", 0) or 0
            raw = await att.read()
            truncated = False
            if len(raw) > MAX_CODE_FILE_BYTES or size > MAX_CODE_FILE_BYTES:
                raw = raw[:MAX_CODE_FILE_BYTES]
                truncated = True

            # Tránh đọc nhầm file nhị phân (có nhiều null byte)
            if b"\x00" in raw[:512]:
                continue

            text = decode_code_bytes(raw)
            if len(text) > MAX_CODE_CHARS_IN_PROMPT:
                text = text[:MAX_CODE_CHARS_IN_PROMPT]
                truncated = True

            extracted.append({
                "filename": filename,
                "language": lang,
                "content": text.strip(),
                "truncated": "true" if truncated else "",
            })
        except Exception as e:
            logger.warning(f"Không thể đọc file code đính kèm '{filename}': {e}")

    return extracted


def format_code_files_for_prompt(code_files: List[Dict[str, str]]) -> str:
    """Định dạng nội dung các file code đính kèm để đưa vào prompt cho LLM."""
    if not code_files:
        return ""
    blocks = []
    for item in code_files:
        trunc_note = " *(đã cắt bớt phần cuối do file lớn)*" if item.get("truncated") else ""
        line_count = item["content"].count("\n") + 1
        blocks.append(
            f"### 📄 TỆP MÃ NGUỒN ĐÍNH KÈM: `{item['filename']}` ({line_count} dòng){trunc_note}\n"
            f"```{item['language']}\n{item['content']}\n```"
        )
    return "\n\n".join(blocks)


def detect_coding_intent(text: str, has_code_files: bool = False) -> bool:
    """
    Nhận diện tin nhắn đang yêu cầu đọc code, viết code, sửa bug hoặc giải thích thuật toán.
    """
    if has_code_files:
        return True
    if not text:
        return False

    # Có code block ```...```
    if "```" in text:
        return True

    lower = text.lower()

    # Các mẫu cú pháp code trực tiếp dán vào khung chat
    code_syntax_patterns = [
        r"\bdef\s+[a-zA-Z_]\w*\s*\(",
        r"\basync\s+def\s+[a-zA-Z_]\w*\s*\(",
        r"\bfunction\s+[a-zA-Z_]\w*\s*\(",
        r"\bconst\s+[a-zA-Z_]\w*\s*=",
        r"\bimport\s+[a-zA-Z_][\w.]*",
        r"\bfrom\s+[a-zA-Z_][\w.]*\s+import\b",
        r"#include\s*<[\w.]+>",
        r"\bpublic\s+static\s+void\s+main\b",
        r"\btraceback\s*\(most recent call last\)",
        r"\b(?:syntaxerror|typeerror|valueerror|attributeerror|keyerror|indexerror|nameerror|referenceerror):",
    ]
    for pat in code_syntax_patterns:
        if re.search(pat, lower):
            return True

    # Các cụm từ yêu cầu viết / đọc / sửa code bằng tiếng Việt & tiếng Anh
    coding_phrases = [
        "viết code", "viet code", "đọc code", "doc code", "sửa code", "sua code",
        "fix code", "fix bug", "fix lỗi", "sửa lỗi code", "review code", "check code",
        "tối ưu code", "giải thích code", "viết hàm", "viet ham", "viết script",
        "viết chương trình", "viết thuật toán", "code giúp", "code hộ", "code bài",
        "lập trình", "write code", "write a function", "write a script", "debug this",
        "refactor", "pull request", "source code", "mã nguồn",
    ]
    if any(p in lower for p in coding_phrases):
        return True

    # Nhắc đến ngôn ngữ lập trình đi kèm động từ kỹ thuật
    langs = ["python", "javascript", "typescript", "nodejs", "reactjs", "html", "css", "c++", "csharp", "c#", "golang", "rust", "java", "sql", "fastapi", "flask", "django", "discord.py", "pytorch"]
    tech_verbs = ["viết", "code", "lỗi", "bug", "hàm", "api", "script", "class", "chạy", "tạo", "build", "fix", "error", "how to"]
    if any(l in lower for l in langs) and any(v in lower for v in tech_verbs):
        return True

    return False


def parse_gif_slug_hint(url: str) -> Optional[str]:
    """
    Trích xuất mô tả ngữ nghĩa từ đường dẫn Tenor / Giphy
    Ví dụ: https://tenor.com/view/anime-hug-sweet-pat-gif-25123456 -> 'anime hug sweet pat'
    """
    if not url:
        return None
    m_tenor = re.search(r"tenor\.com/(?:[\w\-]{2,5}/)?view/([a-zA-Z0-9\-]+)", url, re.IGNORECASE)
    if m_tenor:
        slug = m_tenor.group(1)
        # Bỏ hậu tố -gif-<số>
        slug = re.sub(r"-gif-\d+$", "", slug, flags=re.IGNORECASE)
        slug = re.sub(r"-\d+$", "", slug)
        words = [w for w in slug.split("-") if w and not w.isdigit()]
        if words:
            return " ".join(words)

    m_giphy = re.search(r"giphy\.com/gifs/([a-zA-Z0-9\-]+)", url, re.IGNORECASE)
    if m_giphy:
        slug = m_giphy.group(1)
        parts = slug.split("-")
        if len(parts) > 1:
            words = parts[:-1]  # Bỏ ID hash cuối của Giphy
            if words:
                return " ".join(words)
    return None


async def _download_media_bytes(url: str, timeout_sec: float = 5.0) -> Optional[Tuple[bytes, str]]:
    """Tải dữ liệu ảnh/GIF từ URL (hoặc trích xuất og:image nếu là trang Tenor/Giphy)."""
    if not url or not url.startswith(("http://", "https://")):
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DiscordBot-Neneka/2.0",
        "Accept": "image/gif,image/webp,image/png,image/jpeg,text/html,*/*;q=0.8",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                ctype = (resp.headers.get("Content-Type") or "").lower().split(";")[0].strip()

                # Nếu URL trả về trực tiếp ảnh hoặc GIF
                if ctype.startswith("image/"):
                    data = await resp.content.read(MAX_GIF_DOWNLOAD_BYTES + 1)
                    if len(data) > MAX_GIF_DOWNLOAD_BYTES or not data:
                        return None
                    return data, ctype

                # Nếu là trang HTML của Tenor / Giphy -> tìm thẻ meta og:image (.gif / .png)
                if "text/html" in ctype:
                    html_chunk = (await resp.content.read(65_536)).decode("utf-8", errors="ignore")
                    og_match = re.search(
                        r'<meta\s+(?:property|name)=["\']og:image["\']\s+content=["\'](https?://[^"\']+)["\']',
                        html_chunk,
                        re.IGNORECASE,
                    )
                    if not og_match:
                        og_match = re.search(
                            r'content=["\'](https?://media[^"\']+\.(?:gif|png|webp|jpg))["\']',
                            html_chunk,
                            re.IGNORECASE,
                        )
                    if og_match:
                        media_url = og_match.group(1)
                        async with session.get(media_url) as media_resp:
                            if media_resp.status == 200:
                                m_type = (media_resp.headers.get("Content-Type") or "image/gif").lower().split(";")[0].strip()
                                if m_type.startswith("image/"):
                                    m_data = await media_resp.content.read(MAX_GIF_DOWNLOAD_BYTES + 1)
                                    if 0 < len(m_data) <= MAX_GIF_DOWNLOAD_BYTES:
                                        return m_data, m_type
    except Exception as e:
        logger.debug(f"Không tải được media từ URL '{url}': {e}")

    return None


async def extract_image_or_gif_from_message(message) -> Tuple[Optional[Tuple[bytes, str]], Optional[str]]:
    """
    Tìm và đọc hình ảnh hoặc ảnh động GIF từ:
    1. Attachment trực tiếp (PNG, JPG, WEBP, GIF)
    2. Discord Sticker (PNG / GIF / APNG, kèm tên cảm xúc sticker)
    3. Link GIF Tenor / Giphy / Discord CDN & Embeds (gifv / image / thumbnail)
    4. Tin nhắn được reply (nếu tin nhắn hiện tại không đính kèm ảnh/GIF nhưng đang reply vào ảnh/GIF)

    Trả về: (image_data=(bytes, mime_type) hoặc None, media_context_hint hoặc None)
    """
    async def _extract_single(msg) -> Tuple[Optional[Tuple[bytes, str]], Optional[str]]:
        if not msg:
            return None, None

        # 1. File đính kèm trực tiếp (bao gồm .gif)
        if getattr(msg, "attachments", None):
            for att in msg.attachments:
                ctype = (getattr(att, "content_type", "") or "").lower()
                fname = (getattr(att, "filename", "") or "").lower()
                is_gif_ext = fname.endswith(".gif")
                is_img_ext = fname.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
                if ctype.startswith("image/") or is_img_ext:
                    try:
                        raw = await att.read()
                        mime = "image/gif" if (is_gif_ext or "gif" in ctype) else (ctype or "image/png")
                        hint = f"Người dùng gửi một {'ảnh động GIF' if 'gif' in mime else 'bức ảnh'} đính kèm (`{att.filename}`)."
                        return (raw, mime), hint
                    except Exception as e:
                        logger.warning(f"Lỗi đọc attachment ảnh/GIF: {e}")

        # 2. Discord Stickers
        if getattr(msg, "stickers", None):
            for st in msg.stickers:
                st_name = getattr(st, "name", "sticker")
                st_url = str(getattr(st, "url", "") or "")
                fmt = str(getattr(st, "format", "")).lower()
                hint = f"Người dùng gửi nhãn dán (Sticker) biểu cảm tên là: '{st_name}'."
                if st_url and "lottie" not in fmt:
                    downloaded = await _download_media_bytes(st_url, timeout_sec=4.0)
                    if downloaded:
                        return downloaded, hint
                return None, hint

        # 3. Embeds (Tenor / Giphy gifv hoặc ảnh nhúng trên Discord) & URL GIF trong nội dung
        content_str = getattr(msg, "content", "") or ""
        url_match = GIF_URL_REGEX.search(content_str)
        matched_url = url_match.group(1) if url_match else ""
        slug_hint = parse_gif_slug_hint(matched_url) if matched_url else None

        if getattr(msg, "embeds", None):
            for emb in msg.embeds:
                emb_type = getattr(emb, "type", "") or ""
                emb_title = getattr(emb, "title", "") or ""
                emb_url = getattr(emb, "url", "") or ""
                if not slug_hint and emb_url:
                    slug_hint = parse_gif_slug_hint(emb_url)

                # Tìm URL ảnh tĩnh hoặc GIF preview từ embed (ưu tiên image -> thumbnail)
                candidate_urls = []
                emb_img = getattr(emb, "image", None)
                if emb_img:
                    if getattr(emb_img, "proxy_url", None):
                        candidate_urls.append(str(emb_img.proxy_url))
                    if getattr(emb_img, "url", None):
                        candidate_urls.append(str(emb_img.url))

                emb_thumb = getattr(emb, "thumbnail", None)
                if emb_thumb:
                    if getattr(emb_thumb, "proxy_url", None):
                        candidate_urls.append(str(emb_thumb.proxy_url))
                    if getattr(emb_thumb, "url", None):
                        candidate_urls.append(str(emb_thumb.url))

                if emb_type in ("gifv", "image") or slug_hint or matched_url.lower().endswith(".gif"):
                    for cu in candidate_urls:
                        downloaded = await _download_media_bytes(cu, timeout_sec=4.5)
                        if downloaded:
                            desc_parts = ["Người dùng gửi một ảnh động GIF trên Discord."]
                            if slug_hint:
                                desc_parts.append(f"Chủ đề/Từ khóa của GIF: '{slug_hint}'.")
                            elif emb_title:
                                desc_parts.append(f"Tiêu đề GIF: '{emb_title}'.")
                            return downloaded, " ".join(desc_parts)

        # 4. Nếu nội dung có link GIF (Tenor/Giphy/CDN .gif) nhưng Discord chưa kịp tạo embed
        if matched_url:
            is_likely_gif = (
                "tenor.com" in matched_url.lower()
                or "giphy.com" in matched_url.lower()
                or ".gif" in matched_url.lower()
                or "gifer.com" in matched_url.lower()
            )
            if is_likely_gif:
                downloaded = await _download_media_bytes(matched_url, timeout_sec=4.5)
                desc = "Người dùng gửi một ảnh động GIF."
                if slug_hint:
                    desc += f" Nội dung/Chủ đề từ link GIF: '{slug_hint}'."
                if downloaded:
                    return downloaded, desc
                elif slug_hint:
                    # Ngay cả khi mạng chặn tải ảnh, vẫn hiểu được nội dung GIF nhờ slug!
                    return None, desc

        return None, None

    # Kiểm tra tin nhắn hiện tại trước
    img_data, hint = await _extract_single(message)
    if img_data or hint:
        return img_data, hint

    # Nếu không có, kiểm tra tin nhắn được reply (ví dụ user reply vào 1 cái GIF và hỏi "gif gì đây")
    ref = getattr(message, "reference", None)
    resolved = getattr(ref, "resolved", None) if ref else None
    if resolved:
        r_img, r_hint = await _extract_single(resolved)
        if r_img or r_hint:
            return r_img, (f"[Từ tin nhắn được trả lời] {r_hint}" if r_hint else None)

    return None, None


def message_has_media_or_code(message) -> bool:
    """Kiểm tra nhanh (đồng bộ) xem tin nhắn có ảnh, GIF link, sticker hoặc file code đính kèm không."""
    if getattr(message, "stickers", None):
        return True
    if getattr(message, "attachments", None):
        for att in message.attachments:
            ctype = (getattr(att, "content_type", "") or "").lower()
            fname = getattr(att, "filename", "") or ""
            if ctype.startswith("image/") or fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                return True
            if get_code_language_for_filename(fname, ctype):
                return True
    content = getattr(message, "content", "") or ""
    if GIF_URL_REGEX.search(content):
        return True
    return False


def strip_gif_urls_from_text(text: str) -> str:
    """Xóa link Tenor/Giphy trần khỏi câu hỏi nếu người dùng chỉ gửi mỗi link GIF."""
    if not text:
        return ""
    cleaned = GIF_URL_REGEX.sub("", text).strip()
    return cleaned


def split_discord_message_preserving_code(text: str, limit: int = 1950) -> List[str]:
    """
    Chia tin nhắn dài (> 2000 ký tự của Discord) thành các phần hợp lệ:
    - Không bao giờ cắt ngang dòng nếu có thể.
    - Nếu cắt trúng bên trong khối ```lang ... ```, tự động đóng ``` ở cuối phần trước
      và mở lại ```lang ở đầu phần tiếp theo để code luôn hiển thị đẹp!
    """
    if not text:
        return [""]
    if len(text) <= 2000:
        return [text]

    chunks: List[str] = []
    lines = text.split("\n")
    current_lines: List[str] = []
    current_len = 0
    in_code_block = False
    code_fence_header = "```"

    for line in lines:
        # Nếu 1 dòng đơn lẻ quá dài (> limit - 20), cắt nhỏ dòng đó
        while len(line) > limit - 20:
            part = line[: limit - 20]
            line = line[limit - 20 :]
            if current_len + len(part) + 1 > limit and current_lines:
                chunk_str = "\n".join(current_lines)
                if in_code_block:
                    chunk_str += "\n```"
                chunks.append(chunk_str)
                current_lines = [code_fence_header] if in_code_block else []
                current_len = len(code_fence_header) + 1 if in_code_block else 0
            current_lines.append(part)
            current_len += len(part) + 1

        add_len = len(line) + (1 if current_lines else 0)
        # Dự phòng 8 ký tự để đóng ``` nếu đang trong code block
        reserve = 8 if in_code_block else 0
        if current_len + add_len + reserve > limit and current_lines:
            chunk_str = "\n".join(current_lines)
            if in_code_block:
                chunk_str += "\n```"
            chunks.append(chunk_str)
            current_lines = [code_fence_header] if in_code_block else []
            current_len = (len(code_fence_header) + 1) if in_code_block else 0

        current_lines.append(line)
        current_len += len(line) + 1

        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_fence_header = stripped  # Giữ nguyên ```python, ```js, ...
            else:
                in_code_block = False
                code_fence_header = "```"

    if current_lines:
        chunk_str = "\n".join(current_lines)
        if in_code_block:
            chunk_str += "\n```"
        chunks.append(chunk_str)

    return chunks
