import os
import threading
from typing import Dict
from collections import deque
from flask import Flask, request, abort
from io import BytesIO
import traceback
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from PIL import Image

load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
PORT = int(os.getenv("PORT", 3000))
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "你是一個樂於助人的 LINE 助理，回答要簡潔、有禮貌，以繁體中文回覆。",
)

# 每個對話來源的歷史 token 上限（可調整）
HISTORY_TOKEN_BUDGET = int(os.getenv("HISTORY_TOKEN_BUDGET", "2000"))

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET or not GEMINI_API_KEY:
    raise RuntimeError(
        "Missing env. Please set LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, GEMINI_API_KEY"
    )

app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 設定 Gemini（新版 SDK：google-genai）
client = genai.Client(api_key=GEMINI_API_KEY)


def _normalize_model_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        return "models/gemini-1.5-flash"
    return cleaned if cleaned.startswith("models/") else f"models/{cleaned}"

MODEL_NAME = _normalize_model_name(GEMINI_MODEL)


# 舊版備援已移除；統一使用新版 google-genai


# 以來源維度保存自訂系統提示詞（user/group/room）
sender_key_to_system_prompt: Dict[str, str] = {}
sender_prompt_lock = threading.Lock()

# 以 sender_key 維護對話歷史
sender_key_to_history: Dict[str, deque[genai_types.Content]] = {}
history_lock = threading.Lock()

def get_history(sender_key: str) -> deque[genai_types.Content]:
    with history_lock:
        return sender_key_to_history.setdefault(sender_key, deque())

def add_turn(sender_key: str, role: str, parts: list[genai_types.Part]) -> None:
    history = get_history(sender_key)
    with history_lock:
        history.append(genai_types.Content(role=role, parts=parts))

def trim_history_to_budget(sender_key: str, system_prompt: str) -> None:
    history = get_history(sender_key)
    while True:
        contents = [genai_types.Part.from_text(system_prompt)] + list(history)
        try:
            ct = client.models.count_tokens(model=MODEL_NAME, contents=contents)
            total = getattr(ct, "total_tokens", None) or getattr(ct, "total_tokens_count", None) or 0
        except Exception:
            total = 0
        if total and total > HISTORY_TOKEN_BUDGET and history:
            with history_lock:
                history.popleft()
        else:
            break

def clear_history_for_sender(sender_key: str) -> None:
    with history_lock:
        sender_key_to_history.pop(sender_key, None)


def build_sender_key(event: MessageEvent) -> str:
    source = event.source
    try:
        source_type = getattr(source, "type", "") or ""
        if source_type == "user" and getattr(source, "user_id", None):
            return f"user:{source.user_id}"
        if source_type == "group" and getattr(source, "group_id", None):
            return f"group:{source.group_id}"
        if source_type == "room" and getattr(source, "room_id", None):
            return f"room:{source.room_id}"
    except Exception:
        # fallback
        pass
    return "global"


def get_system_prompt_for_sender(sender_key: str) -> str:
    with sender_prompt_lock:
        return sender_key_to_system_prompt.get(sender_key, SYSTEM_PROMPT)


def set_system_prompt_for_sender(sender_key: str, new_prompt: str) -> None:
    trimmed_prompt = (new_prompt or "").strip()
    with sender_prompt_lock:
        if trimmed_prompt:
            sender_key_to_system_prompt[sender_key] = trimmed_prompt
        else:
            sender_key_to_system_prompt.pop(sender_key, None)


def generate_reply_text(user_text: str, sender_key: str) -> str:
    system_prompt = get_system_prompt_for_sender(sender_key)

    # 將本輪使用者訊息加入歷史
    add_turn(sender_key, role="user", parts=[genai_types.Part.from_text(user_text)])

    # 修剪歷史到 token 預算
    trim_history_to_budget(sender_key, system_prompt)

    # 準備內容（系統提示 + 歷史）
    contents = [genai_types.Part.from_text(system_prompt)] + list(get_history(sender_key))

    # 呼叫模型
    text = ""
    try:
        result = client.models.generate_content(model=MODEL_NAME, contents=contents)
        text = getattr(result, "output_text", None) or getattr(result, "text", None) or ""
        if not text:
            try:
                for cand in getattr(result, "candidates", []) or []:
                    for part in getattr(getattr(cand, "content", None), "parts", None) or []:
                        t = getattr(part, "text", None) or (isinstance(part, dict) and part.get("text"))
                        if isinstance(t, str) and t:
                            text = t
                            break
                    if text:
                        break
            except Exception:
                pass
    except Exception:
        print("[genai] call failed\n" + traceback.format_exc())

    # 把模型回覆加入歷史
    add_turn(sender_key, role="model", parts=[genai_types.Part.from_text(text or "（無內容）")])
    # 再修剪一次
    trim_history_to_budget(sender_key, system_prompt)

    return (text[:1900] + "…") if len(text) > 1900 else text


def generate_reply_for_image(
    image_bytes: bytes,
    mime_type: str,
    sender_key: str,
    user_text: str | None = None,
) -> str:
    """使用 Gemini 解析圖片，搭配（可選）使用者文字。"""
    system_prompt = get_system_prompt_for_sender(sender_key)
    guide = system_prompt
    if user_text and user_text.strip():
        guide = f"{guide}\n\n使用者補充：{user_text.strip()}"
    else:
        guide = f"{guide}\n\n請根據圖片內容給出有幫助且精簡的描述。"

    # 嘗試壓縮/縮放大圖片，避免超出上傳限制
    def _maybe_downscale(img_bytes: bytes, mt: str) -> tuple[bytes, str]:
        try:
            if len(img_bytes) <= 4 * 1024 * 1024 and mt in {"image/jpeg", "image/png"}:
                return img_bytes, mt
            image = Image.open(BytesIO(img_bytes))
            # 轉為 RGB 以便輸出 JPEG
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            max_side = 1600
            w, h = image.size
            scale = min(1.0, max_side / float(max(w, h)))
            if scale < 1.0:
                image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            # 以 JPEG 優化輸出
            for quality in (85, 80, 75, 70, 65):
                buf = BytesIO()
                image.save(buf, format="JPEG", quality=quality, optimize=True)
                data = buf.getvalue()
                if len(data) <= 4 * 1024 * 1024:
                    return data, "image/jpeg"
            # 若仍過大，返回最後一次嘗試
            return data, "image/jpeg"
        except Exception:
            return img_bytes, mt or "image/jpeg"

    image_bytes, mime_type = _maybe_downscale(image_bytes, mime_type or "image/jpeg")

    # 使用新版 SDK 推薦的 from_text / from_bytes 建構 Part
    contents: list[genai_types.Part | str] = [
        genai_types.Part.from_text(guide),
        genai_types.Part.from_bytes(image_bytes, mime_type=mime_type or "image/jpeg"),
    ]

    result = client.models.generate_content(model=MODEL_NAME, contents=contents)

    text = getattr(result, "output_text", None) or getattr(result, "text", None) or ""
    if not text:
        try:
            candidates = getattr(result, "candidates", None) or []
            for cand in candidates:
                content = getattr(cand, "content", None)
                parts = getattr(content, "parts", None)
                if parts:
                    for part in parts:
                        part_text = getattr(part, "text", None) or (isinstance(part, dict) and part.get("text"))
                        if isinstance(part_text, str) and part_text:
                            text = part_text
                            break
                if text:
                    break
        except Exception:
            pass

    return (text[:1900] + "…") if len(text) > 1900 else text


@app.route("/webhook", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")

    # 注意：LINE 簽章驗證需要 raw body
    body = request.get_data(as_text=True)

    # 接收後交由 LINE SDK 檢驗簽章並處理事件

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception:
        # 其他未預期錯誤
        print("[webhook] unexpected error\n" + traceback.format_exc(), flush=True)
        abort(500)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: MessageEvent):
    try:
        original_text = (event.message.text or "").strip()
        sender_key = build_sender_key(event)

        # 系統 prompt 管理指令
        lower_text = original_text.lower()

        # /setprompt 或 /sp 指令
        if lower_text.startswith("/setprompt ") or lower_text.startswith("/sp "):
            parts = original_text.split(" ", 1)
            new_prompt = parts[1] if len(parts) > 1 else ""
            set_system_prompt_for_sender(sender_key, new_prompt)
            current = get_system_prompt_for_sender(sender_key)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"已更新本對話的系統提示詞為：\n{current[:900]}"
                ),
            )
            return

        # !system: 前綴（快捷設定）
        if lower_text.startswith("!system:"):
            new_prompt = original_text[len("!system:") :].strip()
            set_system_prompt_for_sender(sender_key, new_prompt)
            current = get_system_prompt_for_sender(sender_key)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"已更新本對話的系統提示詞為：\n{current[:900]}"
                ),
            )
            return

        # 顯示/重置
        if lower_text in {"/showprompt", "/sp?"}:
            current = get_system_prompt_for_sender(sender_key)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"目前系統提示詞：\n{current[:900]}"),
            )
            return

        if lower_text in {"/resetprompt", "/rsp"}:
            set_system_prompt_for_sender(sender_key, "")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="已重置本對話的系統提示詞，改用預設設定。"),
            )
            return

        # 清除記憶
        if lower_text in {"/clear", "/clearhistory", "/ch"}:
            clear_history_for_sender(sender_key)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="已清除本對話的記憶（歷史）。"),
            )
            return

        # 移除測試用 ping 指令

        # 一般對話
        reply_text = generate_reply_text(original_text, sender_key)
        if not reply_text:
            reply_text = "（無內容）"
        try:
            line_bot_api.reply_message(
                event.reply_token, TextSendMessage(text=reply_text)
            )
        except LineBotApiError as e:
            print(f"[line] reply error status={getattr(e, 'status_code', None)} message={getattr(e, 'message', None)} details={getattr(e, 'error', None)}")
            raise
    except Exception:
        # 印出詳細錯誤以利除錯
        print("[handle_message] error:\n" + traceback.format_exc())
        # 嘗試回覆道歉訊息，但避免再次拋出例外
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="抱歉，系統暫時發生錯誤，請稍後再試 🙏"),
            )
        except Exception:
            print("[handle_message] failed to send error reply:\n" + traceback.format_exc())


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event: MessageEvent):
    try:
        # 下載 LINE 端圖片內容
        msg_id = getattr(event.message, "id", None)
        if not msg_id:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="抱歉，沒有取得圖片內容。"),
            )
            return

        resp = line_bot_api.get_message_content(msg_id)
        # 優先用 iter_content，其次用 content（不同 requests 版本行為略有差異）
        image_bytes = b""
        try:
            chunks = [chunk for chunk in resp.iter_content(chunk_size=8192) if chunk]
            image_bytes = b"".join(chunks)
        except Exception:
            pass
        if not image_bytes:
            try:
                image_bytes = getattr(resp, "content", b"") or b""
            except Exception:
                image_bytes = b""
        mime_type = getattr(resp, "headers", {}).get("Content-Type", "image/jpeg")

        sender_key = build_sender_key(event)
        # 將影像輪次納入歷史（可選，先加入一段提示與圖片）
        add_turn(
            sender_key,
            role="user",
            parts=[
                genai_types.Part.from_text("(使用者傳送了一張圖片)"),
                genai_types.Part.from_bytes(image_bytes, mime_type=mime_type),
            ],
        )
        trim_history_to_budget(sender_key, get_system_prompt_for_sender(sender_key))

        reply_text = generate_reply_for_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            sender_key=sender_key,
            user_text=None,
        )
        # 將模型回覆也加入歷史
        add_turn(sender_key, role="model", parts=[genai_types.Part.from_text(reply_text or "（無內容）")])
        trim_history_to_budget(sender_key, get_system_prompt_for_sender(sender_key))
        if not reply_text:
            reply_text = "（無內容）"
        line_bot_api.reply_message(
            event.reply_token, TextSendMessage(text=reply_text)
        )
    except Exception:
        print("[handle_image] error:\n" + traceback.format_exc())
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="抱歉，圖片解析時發生錯誤，請稍後再試 🙏"),
            )
        except Exception:
            print("[handle_image] failed to send error reply:\n" + traceback.format_exc())


@app.get("/")
def index():
    return "LINE x Gemini (Python) bot is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
