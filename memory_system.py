# memory_system.py
import json
import os
from typing import List, Dict

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neneka_memories.json")

class MemorySystem:
    def __init__(self, filepath: str = MEMORY_FILE, max_short_term: int = 12):
        self.filepath = filepath
        self.max_short_term = max_short_term
        self.short_term_history: List[Dict[str, str]] = []
        self.long_term_facts: List[str] = self._load_memories()

    def _load_memories(self) -> List[str]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_memories(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.long_term_facts, f, ensure_ascii=False, indent=4)

    def add_exchange(self, user_msg: str, neneka_reply: str):
        self.short_term_history.append({"role": "user", "content": user_msg})
        self.short_term_history.append({"role": "assistant", "content": neneka_reply})
        if len(self.short_term_history) > self.max_short_term * 2:
            self.short_term_history = self.short_term_history[-(self.max_short_term * 2):]

    def add_long_term_fact(self, fact: str):
        fact = fact.strip()
        if fact and fact not in self.long_term_facts:
            self.long_term_facts.append(fact)
            # Giữ tối đa 50 ghi chú quan trọng nhất
            if len(self.long_term_facts) > 50:
                self.long_term_facts.pop(0)
            self.save_memories()

    def get_formatted_context(self) -> str:
        facts_str = "\n".join([f"- {fact}" for fact in self.long_term_facts]) if self.long_term_facts else "Chưa có dữ liệu đặc biệt."
        history_str = "\n".join([
            f"{'Người dùng' if m['role'] == 'user' else 'Neneka'}: {m['content']}"
            for m in self.short_term_history[-8:]
        ])
        return f"### GHI CHÚ DÀI HẠN VỀ NGƯỜI DÙNG:\n{facts_str}\n\n### LỊCH SỬ HỘI THOẠI GẦN ĐÂY:\n{history_str}"