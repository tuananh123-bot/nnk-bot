# state_manager.py
import json
import os
from dataclasses import dataclass, asdict
from config_persona import AFFECTION_TIERS, EMOTION_STATES

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neneka_state.json")

@dataclass
class CharacterState:
    affection: int = 150                  # Mặc định bắt đầu ở mức 150/1000
    current_emotion: str = "calm_analytical"
    trust_level: int = 30                 # 0 - 100
    protective_instinct: int = 40        # Mức độ muốn che chở hiện tại (0 - 100)
    interaction_count: int = 0

class StateManager:
    def __init__(self, filepath: str = STATE_FILE):
        self.filepath = filepath
        self.state = self._load_state()

    def _load_state(self) -> CharacterState:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return CharacterState(**data)
            except Exception:
                pass
        return CharacterState()

    def save_state(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(self.state), f, ensure_ascii=False, indent=4)

    def get_current_tier(self) -> dict:
        pts = self.state.affection
        for tier_id, info in AFFECTION_TIERS.items():
            low, high = info["range"]
            if low <= pts <= high:
                return {"tier_id": tier_id, **info}
        return {"tier_id": 5, **AFFECTION_TIERS[5]}

    def update_state(self, affection_delta: int, new_emotion: str, instinct_delta: int = 0):
        # Giới hạn biên độ thay đổi mỗi lượt để tăng tính chân thực (-15 đến +20)
        clamped_delta = max(-15, min(20, affection_delta))
        self.state.affection = max(0, min(1000, self.state.affection + clamped_delta))
        
        if new_emotion in EMOTION_STATES:
            self.state.current_emotion = new_emotion
            
        self.state.protective_instinct = max(0, min(100, self.state.protective_instinct + instinct_delta))
        self.state.interaction_count += 1
        self.save_state()

    def render_affection_bar(self, width: int = 20) -> str:
        pts = self.state.affection
        tier = self.get_current_tier()
        filled = int((pts / 1000) * width)
        bar = "█" * filled + "░" * (width - filled)
        emotion_desc = EMOTION_STATES.get(self.state.current_emotion, "")
        return (
            f"💜 Hảo cảm: [{bar}] {pts}/1000 | Cấp {tier['tier_id']}: {tier['name']}\n"
            f"🎭 Cảm xúc: {self.state.current_emotion} ({emotion_desc})\n"
            f"🛡️ Bản năng bảo bọc: {self.state.protective_instinct}%"
        )