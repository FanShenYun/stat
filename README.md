# STAT - Speech Triage And Tag

語音檢傷分類與標籤列印系統，用於大量傷病患演練場景。操作人員透過語音描述傷患狀況，系統自動進行 START 檢傷分類判讀，並透過藍牙熱感印表機列印檢傷標籤。

## 功能

- **語音輸入** - 按住錄音鍵口述傷患狀況（支援中文）
- **語音轉文字** - OpenAI Whisper API 即時轉錄
- **AI 檢傷判讀** - Gemini 2.5 Flash 依據 START 檢傷準則自動分類（紅/黃/綠/黑）
- **結構化報告** - 顯示 MARCH 評估、MIST 報告、生命徵象、創傷代碼
- **藍牙列印** - 透過 Web Bluetooth 直連 MXW01 熱感印表機列印標籤
- **案件追蹤** - 自動編號（001, 002, ...）

## 系統架構

```
Android Chrome
  ├── MediaRecorder (WebM/Opus 錄音)
  ├── Web Bluetooth (MXW01 印表機)
  └── fetch API
        │
        ▼
FastAPI Backend (Railway)
  ├── OpenAI Whisper API (STT)
  └── Gemini 2.5 Flash (檢傷判讀)
```

## 環境需求

- Python 3.11+
- Android 裝置 + Chrome 瀏覽器（Web Bluetooth 僅 Android Chrome 支援）
- MXW01 藍牙熱感印表機

## 快速開始

### 1. 取得 API 金鑰

- [OpenAI API Key](https://platform.openai.com/api-keys)（Whisper STT 用）
- [Gemini API Key](https://aistudio.google.com)（檢傷判讀用）

### 2. 設定環境變數

```bash
cp .env.sample .env
```

編輯 `.env`：

```env
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
APP_SECRET_PATH=your_secret_token
```

產生 secret path：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(16))"
```

### 3. 安裝與啟動

```bash
pip install -r backend/requirements.txt
cd backend && uvicorn main:app --reload
```

### 4. 存取

開啟 `http://localhost:8000/s/{APP_SECRET_PATH}/`

> 存取根路徑 `/` 會回傳 404，這是設計行為。

## 部署

專案使用 [Railway](https://railway.app) 部署：

```toml
# railway.toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "cd backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"
```

在 Railway 設定以下環境變數：`OPENAI_API_KEY`、`GEMINI_API_KEY`、`APP_SECRET_PATH`

## 專案結構

```
stat/
├── backend/
│   ├── main.py              # FastAPI 伺服器
│   ├── stt.py               # OpenAI Whisper 語音轉文字
│   ├── triage.py            # Gemini 檢傷判讀邏輯
│   └── requirements.txt
├── frontend/
│   ├── index.html           # 主頁面（錄音/顯示/列印）
│   └── ble-test.html        # BLE 印表機測試頁
├── docs/
│   ├── TODO.md              # 開發進度
│   ├── develop_spec.md      # 開發規格書
│   └── develop_spec_v2.md   # 開發規格書 v2
├── railway.toml             # Railway 部署設定
└── .env.sample              # 環境變數範本
```

## API

### POST `/s/{secret}/transcribe-and-triage`

上傳錄音檔案，回傳檢傷判讀結果。

**Request:** `multipart/form-data`，欄位 `audio`（WebM 格式）

**Response:**

```json
{
  "transcript": "患者無意識，呼吸微弱，大腿開放性骨折",
  "triage_level": "red",
  "triage_label": "立即處置",
  "summary": "大腿開放骨折，呼吸微弱，無意識",
  "actions": ["立即開放呼吸道", "加壓止血", "優先後送"],
  "march": {
    "m_hemorrhage": "大腿開放性骨折，需加壓止血",
    "a_airway": { "status": "open_at_risk", "description": "無意識，有阻塞風險" },
    "r_respiration": "呼吸微弱，需監控",
    "c_circulation": "無橈動脈脈搏，疑似休克",
    "h_hypothermia": null
  },
  "vitals": { "consciousness": "U", "hr": null, "bp": null, "spo2": null },
  "trauma_codes": ["I", "L"],
  "mechanism_codes": [5],
  "special_population": [],
  "mist": { "mechanism": "...", "injuries": "...", "signs": "...", "treatment": "..." },
  "timestamp": "2026-03-28T14:32:00+08:00",
  "case_id": "007"
}
```

`triage_level` 為 `unknown` 時表示資訊不足，前端不會顯示列印按鈕。

## 印表機協議

MXW01 使用私有二進制協議（非 ESC/POS）：

- **Service UUID:** `0xAE30`
- **AE01** - 指令通道（狀態查詢、列印請求）
- **AE02** - 回應通道（狀態回報、列印完成）
- **AE03** - 資料通道（點陣圖像素）
- **圖片格式:** 384px 寬 = 48 bytes/row，LSB-first，1=黑色
- **封包格式:** `[0x22][0x21][CMD][0x00][LEN_LO][LEN_HI][PAYLOAD...][CRC8][0xFF]`

參考：[clementvp/mxw01-thermal-printer](https://github.com/clementvp/mxw01-thermal-printer)

## 限制

- Web Bluetooth 僅支援 Android Chrome（iOS 不支援）
- 案件編號存於記憶體，伺服器重啟後歸零
- 存取控制僅依靠 secret path，無使用者驗證機制
