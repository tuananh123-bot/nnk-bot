# cognitive_engine.py
import json
import os
from datetime import datetime
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from config_persona import NENEKA_CORE_PERSONA, EMOTION_STATES
from state_manager import StateManager
from memory_system import MemorySystem

def get_realtime_context() -> str:
    now = datetime.now()
    hour = now.hour
    weekday_vn = [
        "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"
    ][now.weekday()]
    
    if 0 <= hour < 5:
        period = "Nửa đêm / Rạng sáng khuya khoắt"
        hint = "Thời gian cực kỳ muộn. Nếu người dùng còn thức, hãy cằn nhằn yêu thương, giục đi ngủ ngay lập tức."
    elif 5 <= hour < 9:
        period = "Buổi sáng sớm"
        hint = "Bắt đầu ngày mới. Hỏi han tinh thần, nhắc nhở ăn sáng nạp năng lượng."
    elif 9 <= hour < 11:
        period = "Giữa buổi sáng"
        hint = "Giờ học tập / làm việc. Khuyên tập trung nhưng đừng căng thẳng quá mức."
    elif 11 <= hour < 14:
        period = "Buổi trưa"
        hint = "Giờ ăn trưa và nghỉ ngơi. Nhắc nhở ăn uống đúng bữa, chợp mắt một lát."
    elif 14 <= hour < 18:
        period = "Buổi chiều"
        hint = "Giai đoạn dễ uể oải. Khuyên uống nước, trà hoặc nghỉ ngơi xả hơi chốc lát."
    elif 18 <= hour < 22:
        period = "Buổi tối"
        hint = "Thời gian ăn tối và thư giãn sau ngày dài. Hỏi han xem hôm nay của cậu thế nào."
    else:  # 22 <= hour < 24
        period = "Đêm muộn"
        hint = "Sắp hết ngày. Nhắc nhở dẹp máy tính/điện thoại, chuẩn bị đi ngủ sớm."

    return f"""### BỐI CẢNH THỜI GIAN THỰC TẾ:
- Thời gian hiện tại: {now.strftime('%H:%M')} ({weekday_vn}, {now.strftime('%d/%m/%Y')})
- Khung thời gian: {period}
- Gợi ý tương tác: {hint}"""

# Định nghĩa cấu trúc Tư duy (Chain-of-Thought Schema)
class NenekaCognitiveOutput(BaseModel):
    user_state_observation: str = Field(
        description="Quan sát sắc bén về tâm trạng, ẩn ý, tình trạng sức khỏe hoặc xem người dùng có đang trêu chọc/thả thính không."
    )
    logical_analysis: str = Field(
        description="Suy nghĩ nội tâm dưới góc độ nhà nghiên cứu lý tính (phân tích logic, ma lực, tính toán xác suất)."
    )
    sisterly_impulse: str = Field(
        description="Suy nghĩ nội tâm dưới góc độ người chị lớn/tsundere ngầm (muốn bảo bọc, ngượng ngùng khi bị khen, hoặc dỗi yêu khi bị trêu)."
    )
    selected_emotion: str = Field(
        description=f"Chọn 1 trạng thái cảm xúc phù hợp nhất từ danh sách: {list(EMOTION_STATES.keys())}"
    )
    affection_delta: int = Field(
        description="Điểm hảo cảm thay đổi từ -10 đến +15 dựa trên sự chân thành, kính trọng hoặc dễ thương của người dùng."
    )
    protective_instinct_delta: int = Field(
        description="Mức độ thay đổi bản năng che chở từ -10 đến +15."
    )
    new_memory_fact: str = Field(
        description="Nếu người dùng tiết lộ thói quen, sở thích, thông tin cá nhân mới, ghi ngắn gọn 1 câu vào đây. Nếu không, để chuỗi rỗng ''."
    )
    action_gesture: str = Field(
        description="Hành động, cử chỉ, ánh mắt đi kèm đặt trong cặp dấu hoa thị *...* (VD: *khẽ nhấp ngụm trà, liếc nhìn cậu với ánh mắt đầy trêu chọc*)."
    )
    spoken_response: str = Field(
        description="Lời thoại chính thức của Neneka (từ 2 đến 4 câu ngắn gọn, súc tích, tự nhiên, nhịp điệu anime, tuyệt đối KHÔNG viết văn dài dòng)."
    )
    newly_unlocked_bonds: list[int] = Field(
        default_factory=list,
        description="Danh sách id các Bond Story mới mở khóa nếu có (nội bộ hệ thống)."
    )

class CognitiveEngine:
    def __init__(
        self,
        gemini_api_key: str = None,
        groq_api_key: str = None,
        state_mgr: StateManager = None,
        memory_sys: MemorySystem = None,
        model_name: str = "gemini-3.5-flash-lite",
        api_key: str = None
    ):
        # Hỗ trợ tương thích ngược nếu gọi bằng engine = CognitiveEngine(api_key=...)
        if api_key and not gemini_api_key:
            gemini_api_key = api_key

        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        self.state_mgr = state_mgr
        self.memory_sys = memory_sys
        self.model_name = model_name
        self.gemini_fallback_models = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
        self.groq_fallback_models = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]

        # Khởi tạo Gemini client
        self.gemini_client = None
        if self.gemini_api_key:
            try:
                self.gemini_client = genai.Client(api_key=self.gemini_api_key)
            except Exception as e:
                print(f"[Warning] Khởi tạo Gemini Client thất bại: {e}")

        # Khởi tạo Groq client
        self.groq_client = None
        if self.groq_api_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=self.groq_api_key)
            except Exception as e:
                print(f"[Warning] Khởi tạo Groq Client thất bại: {e}")

    def _call_gemini(self, system_instruction: str, user_message: str) -> NenekaCognitiveOutput:
        if not self.gemini_client:
            raise RuntimeError("Gemini Client chưa được cấu hình!")
        models_to_try = [self.model_name] + [m for m in self.gemini_fallback_models if m != self.model_name]
        last_error = None
        for model in models_to_try:
            try:
                response = self.gemini_client.models.generate_content(
                    model=model,
                    contents=f"Tin nhắn của người dùng: {user_message}",
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=NenekaCognitiveOutput,
                        temperature=0.8,
                    ),
                )
                if hasattr(response, "parsed") and response.parsed is not None:
                    return response.parsed
                else:
                    raw_text = (response.text or "").strip()
                    if raw_text.startswith("```"):
                        lines = raw_text.splitlines()
                        if lines and lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].startswith("```"):
                            lines = lines[:-1]
                        raw_text = "\n".join(lines).strip()
                    result_data = json.loads(raw_text)
                    return NenekaCognitiveOutput(**result_data)
            except Exception as e:
                last_error = e
                continue
        raise last_error

    def _call_groq(self, system_instruction: str, user_message: str) -> NenekaCognitiveOutput:
        if not self.groq_client:
            raise RuntimeError("Groq Client chưa được cấu hình!")
        schema_json = json.dumps(NenekaCognitiveOutput.model_json_schema(), ensure_ascii=False)
        groq_sys_prompt = f"{system_instruction}\n\nBẮT BUỘC: Trả về DUY NHẤT một chuỗi JSON hợp lệ tuân theo schema sau:\n{schema_json}"
        
        last_error = None
        for model in self.groq_fallback_models:
            try:
                resp = self.groq_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": groq_sys_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.75,
                    max_tokens=1500
                )
                content = (resp.choices[0].message.content or "").strip()
                if not content:
                    print(f"[Groq Warning] Model {model} trả về nội dung rỗng, thử model khác...")
                    last_error = RuntimeError(f"Model {model} trả về nội dung rỗng")
                    continue
                return NenekaCognitiveOutput.model_validate_json(content)
            except Exception as e:
                print(f"[Groq Warning] Model {model} lỗi: {e}")
                last_error = e
                continue
        raise last_error

    def process_message(self, user_message: str) -> NenekaCognitiveOutput:
        tier_info = self.state_mgr.get_current_tier()
        st = self.state_mgr.state
        memory_context = self.memory_sys.get_formatted_context()
        realtime_context = get_realtime_context()

        system_instruction = f"""
{NENEKA_CORE_PERSONA}

### TRẠNG THÁI HIỆN TẠI CỦA NENEKA:
- Điểm hảo cảm hiện tại: {st.affection}/1000
- Cấp độ quan hệ: Cấp {tier_info['tier_id']} - {tier_info['name']}
- Chỉ dẫn thái độ ở cấp độ này: {tier_info['behavior']}
- Cảm xúc hiện tại: {st.current_emotion} ({EMOTION_STATES.get(st.current_emotion, '')})
- Chỉ số bản năng bảo bọc: {st.protective_instinct}/100

{realtime_context}

{memory_context}

### QUY TRÌNH TƯ DUY & TẠO PHẢN HỒI BẮT BUỘC:
1. Đọc kỹ lời người dùng, đối chiếu với Bối cảnh thời gian thực tế và Ký ức dài hạn.
2. Kiểm tra các yếu tố kích hoạt tính cách đặc biệt:
   - Nếu bị trêu về tuổi tác/chiều cao: Kích hoạt phản ứng đe dọa tinh nghịch, sắc sảo (Tử huyệt).
   - Nếu được khen ngợi/tán tỉnh ngọt ngào: Kích hoạt phản ứng bối rối, ngượng ngùng ngầm rồi lấy lại phong thái bề trên (Tsundere).
   - Nếu vào đêm khuya hoặc mệt mỏi: Kích hoạt bản năng bảo bọc, giục nghỉ ngơi, cằn nhằn yêu thương.
3. Để hai luồng suy nghĩ 'Lý trí' và 'Người chị bảo bọc' đối thoại trong Chain of Thought.
4. Lời thoại (spoken_response): Tuyệt đối KHÔNG viết văn trợ lý ảo sáo rỗng. Hãy nói chuyện tự nhiên bằng 2 - 4 câu đắt giá, giàu cảm xúc, có nhạc điệu anime theo các mẫu Few-shot.
"""

        cognitive_result = None
        gemini_error = None

        # 1. Ưu tiên gọi Gemini nếu có key
        if self.gemini_client:
            try:
                cognitive_result = self._call_gemini(system_instruction, user_message)
            except Exception as e:
                gemini_error = e
                print(f"[Engine Warning] Gemini gặp sự cố: {e}. Đang chuyển sang Groq dự phòng...")

        # 2. Tự động fallback sang Groq nếu Gemini lỗi hoặc chưa có
        if cognitive_result is None and self.groq_client:
            try:
                cognitive_result = self._call_groq(system_instruction, user_message)
            except Exception as groq_error:
                print(f"[Engine Error] Groq cũng gặp sự cố: {groq_error}")
                if gemini_error:
                    raise RuntimeError(f"Cả Gemini ({gemini_error}) và Groq ({groq_error}) đều thất bại!")
                raise groq_error

        if cognitive_result is None:
            if gemini_error:
                raise gemini_error
            raise RuntimeError("Không có AI Provider nào hoạt động! Hãy kiểm tra GEMINI_API_KEY hoặc GROQ_API_KEY trong .env.")

        # Cập nhật State & Memory tự động
        new_bonds = self.state_mgr.update_state(
            affection_delta=cognitive_result.affection_delta,
            new_emotion=cognitive_result.selected_emotion,
            instinct_delta=cognitive_result.protective_instinct_delta
        )
        cognitive_result.newly_unlocked_bonds = new_bonds

        if cognitive_result.new_memory_fact:
            self.memory_sys.add_long_term_fact(cognitive_result.new_memory_fact)

        self.memory_sys.add_exchange(
            user_msg=user_message,
            neneka_reply=f"{cognitive_result.action_gesture} {cognitive_result.spoken_response}"
        )

        return cognitive_result

    def process_gift(self, gift_name: str) -> NenekaCognitiveOutput:
        """Xử lý khi người dùng tặng quà cho Neneka"""
        tier_info = self.state_mgr.get_current_tier()
        st = self.state_mgr.state
        memory_context = self.memory_sys.get_formatted_context()
        realtime_context = get_realtime_context()

        system_instruction = f"""
{NENEKA_CORE_PERSONA}

### TRẠNG THÁI HIỆN TẠI CỦA NENEKA:
- Điểm hảo cảm hiện tại: {st.affection}/1000
- Cấp độ quan hệ: Cấp {tier_info['tier_id']} - {tier_info['name']}
- Cảm xúc hiện tại: {st.current_emotion} ({EMOTION_STATES.get(st.current_emotion, '')})
- Chỉ số bản năng bảo bọc: {st.protective_instinct}/100

{realtime_context}

{memory_context}

### TÌNH HUỐNG: NGƯỜI DÙNG TẶNG QUÀ LANDOSOL
Người dùng vừa gửi tặng Neneka món quà: "{gift_name}".

### QUY TẮC PHẢN HỒI KHI NHẬN QUÀ:
1. Đánh giá món quà theo phong thái một quý cô sành sỏi, từng trải của Thất Vương:
   - Đồ ngọt, bánh crepe, bánh tart dâu tây Landosol, bánh quy hoàng cung, trà đen hảo hạng: Rất thích thú, mỉm cười "Fufu...", khen ngợi sự chu đáo và tinh tế của cậu.
   - Quà lãng mạn (hoa, trang sức, quà đôi): Bối rối, ngượng ngùng ngầm (Tsundere), vội chỉnh lọn tóc che đi vành tai đỏ rồi mới buông lời khen ngợi.
   - Quà kỳ lạ hoặc vụng về: Bật cười thích thú, trêu chọc xem có phải cậu đang muốn thử phản ứng của cô không.
2. Cử chỉ hành động (*action_gesture*): Đi kèm cử chỉ quý phái, phân thân nhận quà hoặc bẻ nửa miếng bánh mời cậu cùng thưởng thức.
3. Điểm hảo cảm (affection_delta): Luôn cộng từ +10 đến +25 điểm.
4. Lời thoại (spoken_response): 2 - 4 câu tự nhiên, ấm áp, đậm chất anime.
"""
        gift_prompt = f"Ta vừa nhận được món quà này từ cậu: {gift_name}"
        cognitive_result = None
        gemini_error = None

        if self.gemini_client:
            try:
                cognitive_result = self._call_gemini(system_instruction, gift_prompt)
            except Exception as e:
                gemini_error = e

        if cognitive_result is None and self.groq_client:
            try:
                cognitive_result = self._call_groq(system_instruction, gift_prompt)
            except Exception as groq_error:
                if gemini_error:
                    raise RuntimeError(f"Cả Gemini ({gemini_error}) và Groq ({groq_error}) đều thất bại!")
                raise groq_error

        if cognitive_result is None:
            raise RuntimeError("Không có AI Provider nào hoạt động!")

        # Quà tặng luôn đảm bảo tăng hảo cảm ý nghĩa (+10 đến +25)
        if cognitive_result.affection_delta < 8:
            cognitive_result.affection_delta = 12

        new_bonds = self.state_mgr.update_state(
            affection_delta=cognitive_result.affection_delta,
            new_emotion=cognitive_result.selected_emotion,
            instinct_delta=cognitive_result.protective_instinct_delta
        )
        cognitive_result.newly_unlocked_bonds = new_bonds

        gift_fact = f"Người dùng đã tặng món quà: {gift_name} (Neneka cảm thấy: {cognitive_result.selected_emotion})"
        self.memory_sys.add_long_term_fact(gift_fact)

        self.memory_sys.add_exchange(
            user_msg=f"[Tặng quà]: {gift_name}",
            neneka_reply=f"{cognitive_result.action_gesture} {cognitive_result.spoken_response}"
        )

        return cognitive_result
