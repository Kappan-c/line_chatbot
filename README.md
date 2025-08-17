# 🤖 LINE x Gemini AI Bot

基於 Python Flask 的 LINE 聊天機器人，整合 Google Gemini AI，支援文字對話、圖片解析和智慧記憶管理。

## ✨ 主要功能

- 🧠 **Gemini AI 對話**：整合 Google Gemini 模型，提供智慧對話
- 🖼️ **圖片解析**：上傳圖片即可獲得 AI 分析和描述
- 💭 **記憶管理**：自動維護對話歷史，支援 token 預算控制
- 🎯 **系統提示詞**：可自訂 AI 角色和回應風格
- 👥 **多來源支援**：支援個人、群組、聊天室獨立對話記憶
- 🔄 **指令控制**：豐富的指令系統管理機器人行為

## 🚀 快速開始

### 1. 環境設置

```bash
# 建立虛擬環境
python -m venv .venv

# 啟動虛擬環境
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# 安裝依賴
pip install -U pip
pip install -r requirements.txt
```

### 2. 環境變數配置

建立 `.env` 檔案並設定以下變數：

```env
# LINE Bot 設定
LINE_CHANNEL_ACCESS_TOKEN=你的_LINE_Channel_Access_Token
LINE_CHANNEL_SECRET=你的_LINE_Channel_Secret

# Gemini AI 設定
GEMINI_API_KEY=你的_Gemini_API_Key
GEMINI_MODEL=gemini-1.5-flash

# 可選設定
PORT=3000
SYSTEM_PROMPT=你是一個樂於助人的 LINE 助理，回答要簡潔、有禮貌，以繁體中文回覆。
HISTORY_TOKEN_BUDGET=2000
```

### 3. 啟動服務

```bash
python app.py
```

服務將在 http://localhost:3000 啟動

### 4. 設定 Webhook

使用 ngrok 暴露本地服務：

```bash
# 下載並執行 ngrok
./ngrok http 3000

# 將生成的 URL 設定為 LINE Webhook
# 例如：https://abc123.ngrok.io/webhook
```

在 LINE Developers Console 中：
1. 設定 Webhook URL：`https://你的ngrok網址.ngrok.io/webhook`
2. 啟用 Webhook
3. 驗證連接

## 📋 環境變數說明

| 變數名稱 | 必填 | 說明 | 預設值 |
|---------|------|------|--------|
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | LINE Channel Access Token | - |
| `LINE_CHANNEL_SECRET` | ✅ | LINE Channel Secret | - |
| `GEMINI_API_KEY` | ✅ | Google Gemini API Key | - |
| `GEMINI_MODEL` | ❌ | Gemini 模型名稱 | `gemini-1.5-flash` |
| `PORT` | ❌ | Flask 服務埠號 | `3000` |
| `SYSTEM_PROMPT` | ❌ | 預設系統提示詞 | 內建中文助理提示 |
| `HISTORY_TOKEN_BUDGET` | ❌ | 對話歷史 token 預算 | `2000` |

## 🎮 指令系統

### 📝 系統提示詞管理

| 指令 | 功能 | 範例 |
|------|------|------|
| `/setprompt <內容>` | 設定系統提示詞 | `/setprompt 你是一個專業的程式設計師` |
| `/sp <內容>` | 設定系統提示詞（簡寫） | `/sp 你是一個幽默的助理` |
| `!system:<內容>` | 快捷設定提示詞 | `!system:你是一個詩人` |
| `/showprompt` 或 `/sp?` | 顯示目前提示詞 | `/showprompt` |
| `/resetprompt` 或 `/rsp` | 重置為預設提示詞 | `/resetprompt` |

### 🧠 記憶管理

| 指令 | 功能 | 範例 |
|------|------|------|
| `/clear` | 清除對話記憶 | `/clear` |
| `/clearhistory` | 清除對話記憶 | `/clearhistory` |
| `/ch` | 清除對話記憶（簡寫） | `/ch` |

## 🔧 技術架構

### 📁 專案結構

```
linebot/
├── app.py              # 主程式
├── requirements.txt    # Python 依賴
├── ngrok.exe          # ngrok 執行檔
├── .env               # 環境變數（需自建）
└── README.md          # 專案說明
```

### 🛠️ 核心技術

- **Web 框架**：Flask 3.0.3
- **LINE SDK**：line-bot-sdk 3.13.0  
- **AI 模型**：Google Gemini (google-genai 0.3.0)
- **環境管理**：python-dotenv 1.0.1
- **圖片處理**：Pillow (內建)

### 🧠 記憶機制

機器人為每個對話來源（個人/群組/聊天室）維護獨立的：

1. **對話歷史**：儲存在記憶體中，重啟後清除
2. **系統提示詞**：可自訂 AI 角色，重啟後清除  
3. **Token 預算控制**：自動修剪過長的對話歷史

### 🖼️ 圖片處理

- 自動壓縮大圖片（4MB 限制）
- 支援 JPEG、PNG 格式
- 智慧縮放和品質優化
- 與 Gemini Vision 整合分析

## 💡 使用範例

### 基本對話

```
用戶：你好！
機器人：您好！我是您的 LINE 助理，有什麼可以幫助您的嗎？

用戶：幫我解釋量子物理
機器人：量子物理是研究微觀粒子行為的科學分支...
```

### 自訂角色

```
用戶：/sp 你是一個專業的日文老師
機器人：已更新本對話的系統提示詞為：你是一個專業的日文老師

用戶：教我日文的問候語
機器人：こんにちは！作為您的日文老師，我來教您常用的問候語...
```

### 圖片分析

```
用戶：[上傳一張食物照片]
機器人：這看起來是一道美味的義大利麵！我可以看到...
```

## 🔒 安全注意事項

- ✅ LINE Webhook 簽章驗證
- ✅ 環境變數保護敏感資訊
- ✅ 錯誤處理和異常捕獲
- ✅ 圖片大小和格式限制
- ✅ Token 預算控制防止濫用

## 🛠️ 故障排除

### ❗ 常見問題

| 問題 | 可能原因 | 解決方案 |
|------|----------|----------|
| 🔌 **Webhook 驗證失敗** | 簽章錯誤 | 檢查 `LINE_CHANNEL_SECRET` 設定 |
| 🤖 **AI 無回應** | API Key 錯誤 | 檢查 `GEMINI_API_KEY` 有效性 |
| 🖼️ **圖片解析失敗** | 圖片過大或格式不支援 | 檢查圖片大小和格式 |
| 💭 **記憶異常** | Token 超出預算 | 調整 `HISTORY_TOKEN_BUDGET` |

### 📊 除錯資訊

```bash
# 查看詳細錯誤日誌
python app.py

# 檢查服務狀態
curl http://localhost:3000/

# 測試 Webhook
curl -X POST http://localhost:3000/webhook
```

## 📚 參考資料

- 📖 [LINE Messaging API 文檔](https://developers.line.biz/en/docs/messaging-api/)
- 🤖 [Google Gemini API 文檔](https://ai.google.dev/docs)
- 🐍 [Flask 官方文檔](https://flask.palletsprojects.com/)
- 🔗 [ngrok 使用指南](https://ngrok.com/docs)

## 🔄 進階功能

### 持久化儲存

如需跨重啟保持記憶，可修改程式碼使用：

- **Redis**：快速記憶體資料庫
- **SQLite**：輕量級關聯式資料庫  
- **檔案儲存**：JSON 或 pickle 格式

### 擴展功能

- 🎵 **語音處理**：整合語音轉文字
- 📊 **數據分析**：對話統計和分析
- 🔔 **推播訊息**：主動訊息推送
- 🌐 **多語言支援**：國際化介面

---

<div align="center">

**🎉 歡迎貢獻和反饋！**

如有問題請提交 Issue 或改進建議

</div>