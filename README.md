# STAT - Speech Triage And Tag

語音檢傷分類與標籤列印系統，用於大量傷病患演練場景。操作人員透過語音描述傷患狀況，系統自動進行 START 檢傷分類判讀，並透過藍牙熱感印表機列印檢傷標籤。

## 功能

- **語音輸入** - 按錄音鍵口述傷患狀況（支援中文，最長 2 分鐘）
- **語音轉文字** - OpenAI Whisper API 即時轉錄
- **AI 檢傷判讀** - Gemini 2.5 Flash 依據 START 檢傷準則自動分類（紅/黃/綠/黑）
- **結構化報告** - 顯示 MARCH 評估、MIST 報告、生命徵象、創傷代碼
- **MIST QR Code** - 察看結果 modal 與列印標籤皆含 QR，掃描可直接取得 MIST 四欄純文字匯入 HIS/EMR
- **藍牙列印** - 透過 Web Bluetooth 直連 MXW01 熱感印表機列印標籤
- **佇列式多傷患處理** - 錄音結束後可立刻錄下一位，AI 處理與列印在背景進行
- **傷患列表** - 首頁集中顯示所有傷患的處理狀態，可逐筆察看、列印、刪除、重試
- **列印佇列** - 藍牙印表機 mutex，多筆依序列印不衝突

## 操作流程

```
[錄音] → [錄音結束]
              │
              ├─ 返回首頁  ──▶ 首頁列表（可看到該筆處理中）
              └─ 錄下一位 ──▶ 立刻開始下一筆錄音
                                    │
                         AI 背景處理完成後 ──▶ 狀態自動更新為「待列印」
                                                      │
                                              [按列印] → 進列印佇列
                                                      │
                                              列印成功 → 狀態「已列印」+ Google Sheet 記錄
```

### 傷患狀態機

```
processing ──▶ done ──┬──▶ printing ──▶ printed
     │                │                    │
     └──▶ error ◀─────┘       (可重複列印) ◀┘
           │
           └──▶ 重試（回到 processing）
```

## 系統架構

```
Android Chrome
  ├── MediaRecorder (WebM/Opus 錄音)
  ├── Web Bluetooth (MXW01 印表機)
  ├── sessionStorage (傷患列表、狀態、音訊暫存)
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
GOOGLE_SHEET_WEBHOOK_URL=https://...  # 選填，Google Apps Script webhook
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
│   ├── index.html           # 主頁面（錄音/列表/列印）
│   ├── qrcode.min.js        # qrcode-generator v1.4.4（MIST QR 用，vendored）
│   └── ble-test.html        # BLE 印表機測試頁
├── docs/
│   ├── develop_spec.md      # 開發規格書 v1
│   ├── develop_spec_v2.md   # 開發規格書 v2
│   ├── develop_spec_v3_queue.md  # 開發規格書 v3（佇列式流程）
│   └── v3_test_guide.md     # v3 測試指南
├── railway.toml             # Railway 部署設定
└── .env.sample              # 環境變數範本
```

## API

### POST `/s/{secret}/transcribe-and-triage`

上傳錄音檔案，回傳檢傷判讀結果。Case ID 由**前端**根據錄音順序分配，後端不再產生編號。

**Request:** `multipart/form-data`，欄位 `audio_file`（WebM 格式）

**Response:**

```json
{
  "casualties": [
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
      "mist": {
        "m_mechanism": "...", "i_injuries": "...", "s_signs": "...", "t_treatment": "..."
      },
      "timestamp": "2026-03-28T14:32:00+08:00"
    }
  ]
}
```

- `casualties` 陣列長度通常為 1，單次口述描述多位傷患時可能回傳多筆
- `triage_level` 為 `unknown` 時表示資訊不足
- 前端收到後依錄音順序分配 case_id：單筆為 `"007"`，多筆為 `"008a"`、`"008b"`

### POST `/s/{secret}/log-casualties`

列印成功後送出傷患紀錄至 Google Sheet。**僅在第一次列印成功後呼叫**，重複列印不重送。

**Request:** `application/json`

```json
{
  "casualties": [
    { "case_id": "007", "triage_level": "red", "summary": "...", ... }
  ]
}
```

## 前端資料儲存

傷患資料以 `sessionStorage` 儲存（關閉分頁自動清除）：

| Key | 說明 |
|---|---|
| `stat.casualties` | 所有傷患的 JSON 陣列（含狀態、AI 結果、音訊 base64） |
| `stat.batchSeq` | 最後分配的錄音序號（單調遞增，用於排序與 case_id 生成） |

重整分頁後，原本 `processing` 狀態的項目會自動轉為 `error`（可用原始音訊重試）。

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
- 傷患資料存於 sessionStorage，關閉分頁後清除（單場演練設計）
- 存取控制僅依靠 secret path，無使用者驗證機制
- sessionStorage 上限約 5MB；WebM/Opus 錄音 base64 後約 40-70KB/筆，可容納約 80 筆
