# src/utils/response_guard.py
"""
Bộ Khiên Kiểm Soát Chất Lượng Phản Hồi LLM (Response Quality & Anti-Loop Guard):
1. Bóc tách và loại bỏ hoàn toàn khối suy nghĩ nội tâm rò rỉ (`<think>...</think>`, `<reasoning>...</reasoning>`).
2. Phát hiện hiện tượng "tẩu hỏa nhập ma" (Degenerative Repetition Loop & Self-Contradiction Spiral) —
   ví dụ model tự đoán mò, tự bác bỏ liên tiếp ("không, sai rồi... không, ta đang đùa... ta đang tự mâu thuẫn... hãy để ta làm lại...").
3. Khử trùng lặp dòng và cắt bỏ phần đuôi lặp/mâu thuẫn để cứu câu trả lời sạch sẽ, đồng thời chặn lưu rác vào Short-Term Memory.
"""

import re
from typing import List

# Regex xóa khối suy nghĩ nội tâm của các dòng model Qwen3 / DeepSeek / R1
THINK_BLOCK_RE = re.compile(r"<(?:think|thinking|reasoning|thought)>[\s\S]*?</(?:think|thinking|reasoning|thought)>", re.IGNORECASE)
UNCLOSED_THINK_RE = re.compile(r"<(?:think|thinking|reasoning|thought)>[\s\S]*$", re.IGNORECASE)

# Các cụm từ báo hiệu model đang bị kẹt vòng lặp tự mâu thuẫn / tự sửa lưng ngay trong câu trả lời
HARD_CONTRADICTION_PHRASES = (
    "ta đang tự mâu thuẫn",
    "tôi đang tự mâu thuẫn",
    "mình đang tự mâu thuẫn",
    "hãy để ta làm lại",
    "để ta làm lại từ đầu",
    "khoan, ta làm lại",
    "i am contradicting myself",
    "i'm contradicting myself",
    "let me start over",
    "wait, let me redo",
)

FLIP_FLOP_PATTERNS = (
    r"không,\s*sai\s*rồi",
    r"không,\s*đó\s*chỉ\s*có",
    r"không,\s*đó\s*là",
    r"không,\s*ta\s*đang\s*đùa",
    r"không,\s*ta\s*không",
    r"à\s*không,\s*thực\s*ra",
    r"khoan\s*đã,\s*sai",
    r"wait,\s*no[,.]",
    r"no,\s*that's\s*wrong",
    r"actually,\s*no[,.]",
)


def strip_thinking_blocks(text: str) -> str:
    """Xóa sạch mọi thẻ <think>...</think> (kể cả thẻ mở chưa kịp đóng do chạm max_tokens)."""
    if not text:
        return ""
    cleaned = THINK_BLOCK_RE.sub("", text)
    cleaned = UNCLOSED_THINK_RE.sub("", cleaned)
    return cleaned.strip()


def _normalize_line_for_dedup(line: str) -> str:
    """Chuẩn hóa câu để phát hiện câu lặp hoặc lặp đáp án đổi đầu câu."""
    s = line.lower().strip()
    # Bỏ nhiều lớp tiền tố dẫn chuyện lặp đi lặp lại trước mệnh đề chính
    prefix_re = re.compile(
        r"^(?:hãy\s+để\s+ta\s+(?:tiết\s+lộ|giải\s+thích[^:]*|nói[^:]*)\s*:\s*|đáp\s+án\s+(?:đúng|chính)\s+là\s+|thực\s+ra,?\s*từ\s+mà\s+ta\s+đang\s+nghĩ\s+đến\s+là\s+|từ\s+ấy\s+là\s+)"
    )
    changed = True
    while changed:
        new_s = prefix_re.sub("", s).strip()
        if new_s != s:
            s = new_s
        else:
            changed = False
    s = re.sub(r"[*_`~\"'.,!?…:;()\[\]\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def has_degenerative_loop_or_contradiction(text: str) -> bool:
    """
    Kiểm tra xem câu trả lời của LLM có rơi vào vòng lặp lặp câu hoặc tự mâu thuẫn liên hoàn không.
    (Bỏ qua nội dung bên trong khối ```code``` để không ảnh hưởng tính năng đọc/viết code).
    """
    if not text:
        return False

    # Tách bỏ khối code ```...``` trước khi kiểm tra văn bản hội thoại
    non_code = re.sub(r"```[\s\S]*?```", "", text).strip()
    if not non_code:
        return False

    lower = non_code.lower()

    # 1. Dính cụm từ tự thú nhận mâu thuẫn / đòi làm lại
    if any(p in lower for p in HARD_CONTRADICTION_PHRASES):
        return True

    # 2. Đếm số lần tự lật kèo / tự phủ định liên tiếp trong cùng 1 tin nhắn
    flip_count = 0
    for pat in FLIP_FLOP_PATTERNS:
        flip_count += len(re.findall(pat, lower))
    if flip_count >= 2:
        return True

    # 3. Kiểm tra lặp dòng / lặp mệnh đề giữa các đoạn văn
    paragraphs = [p.strip() for p in non_code.split("\n") if p.strip()]
    if len(paragraphs) >= 4:
        norm_counts = {}
        exact_counts = {}
        for p in paragraphs:
            exact_key = re.sub(r"\s+", " ", p.lower())
            exact_counts[exact_key] = exact_counts.get(exact_key, 0) + 1
            if exact_counts[exact_key] >= 2 and len(exact_key) >= 8:
                return True

            norm_key = _normalize_line_for_dedup(p)
            if len(norm_key) >= 8:
                norm_counts[norm_key] = norm_counts.get(norm_key, 0) + 1
                if norm_counts[norm_key] >= 3:
                    return True

    # 4. Quá nhiều đoạn văn ngắn rời rạc (>= 10 dòng xuống hàng liên tục không phải danh sách bullet hay thơ)
    if len(paragraphs) >= 10:
        short_paras = sum(1 for p in paragraphs if len(p) < 85 and not p.startswith(("-", "•", "*", "1.", "2.", "3.")))
        if short_paras >= 8:
            return True

    return False


def salvage_non_looping_text(text: str) -> str:
    """
    Làm sạch thẻ <think>, cắt bỏ các đoạn tự mâu thuẫn / lặp lại nếu model dự phòng vẫn còn vương lỗi nhẹ.
    Bảo toàn nguyên vẹn các khối ```code```.
    """
    cleaned = strip_thinking_blocks(text)
    if not cleaned:
        return ""

    # Nếu có code block hợp lệ và không bị tự mâu thuẫn thì giữ nguyên
    if "```" in cleaned and not has_degenerative_loop_or_contradiction(cleaned):
        return cleaned

    lines = cleaned.split("\n")
    kept_lines: List[str] = []
    seen_norm = set()
    in_code = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            kept_lines.append(line)
            continue

        if in_code:
            kept_lines.append(line)
            continue

        if not stripped:
            if kept_lines and kept_lines[-1] != "":
                kept_lines.append("")
            continue

        low = stripped.lower()
        # Khi đã có nội dung mở đầu hợp lệ mà gặp câu tự thú nhận mâu thuẫn ("Không, ta đang tự mâu thuẫn") -> cắt đứt phần đuôi rối loạn!
        if any(p in low for p in HARD_CONTRADICTION_PHRASES):
            if kept_lines:
                break
            continue
        if any(re.search(pat, low) for pat in FLIP_FLOP_PATTERNS):
            continue

        norm = _normalize_line_for_dedup(stripped)
        if len(norm) >= 3 and norm in seen_norm:
            continue
        if len(norm) >= 3:
            seen_norm.add(norm)

        kept_lines.append(line)

    result = "\n".join(kept_lines).strip()
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result
