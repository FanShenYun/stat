"""Gemini API START triage module for STAT."""

import json
import os

from google import genai

TRIAGE_PROMPT = """你是一位緊急醫療專業人員，負責依照末社傷情卡 v5.0 格式對傷患進行檢傷分類。

根據以下口述內容，判讀傷患的檢傷級別與相關資訊，並輸出結構化 JSON。

## 檢傷判讀規則（後送順序）
- 紅（緊急 immediate）：呼吸>30次/分、無橈動脈脈搏、無法遵從指令
- 黃（優先 delayed）：傷情嚴重但暫時穩定
- 綠（一般 minor）：可自行走動
- 黑（期待 expectant）：無呼吸（開放呼吸道後仍無）、OHCA

## MARCH 初級評估欄位
從口述中擷取以下資訊（未提及的項目設為 null）：
- M 大出血：止血帶(CAT)使用、填塞、加壓等
- A 呼吸道：鼻咽、口咽、甦醒球、復甦姿勢等
- R 呼吸：呼吸次數、胸封、針刺減壓等
- C 循環：CRT、末梢濕冷、膚色（白/紺/紅）等
- H 低體溫：保暖毯等

## 生命徵象
從口述中擷取（未提及設為 null）：HR 脈搏、BP 血壓、SpO2 血氧、Temp 體溫、意識(AVPU)、GCS(E/V/M)

## 創傷分類代碼
若口述內容符合以下分類，列出對應代碼字母：
A 開放性顱骨骨折 TBI、B 顱底骨折 TBI、C 顏面/呼吸道灼傷、
D 張力性氣胸/氣管受損、E 氣胸/氣血胸、F 開放性氣胸、
G 腹腔內出血、H 大血管損傷/臟器穿刺傷、I 雙側股骨骨折、
J 脫皮性損傷、K 壓砸傷症候群、L 骨盆骨折、M 內臟外露、
N 燒燙傷、O OHCA、P 斷肢

## 創傷/非創傷機轉代碼
1 爆炸、2 槍傷、3 銳物穿刺傷、4 交通意外、5 墜落、6 化生放核毒物中毒、
7 生物襲咬傷、8 氣壓傷應症候群、9 高體溫/熱傷害、10 低體溫/失溫*、
11 溺水*、12 電擊傷*（*需逆向檢傷）
非創傷：疑似食物中毒、吸入性傷害或發紺、疑似心臟原因者、過度換氣

## 特殊情況處理
- 若口述內容模糊、資訊不足以判斷檢傷級別，將 triage_level 設為 "unknown"
- 若口述內容明顯為非傷患相關的語音（如閒聊、環境噪音轉錄），同樣設為 "unknown"
- 若語音辨識結果為亂碼或無意義文字，設為 "unknown"
- 設為 "unknown" 時，summary 應說明無法判讀的原因，actions 應建議操作者如何補充資訊

## 特殊族群標記
若口述中提及：兒童、孕婦、慢性病、高齡、旅行者、外國人，請標記。

口述內容：{transcript}

請以 JSON 格式回覆，包含以下欄位：
- triage_level: "black" | "red" | "yellow" | "green" | "unknown"
- triage_label: 對應中文（緊急/優先/一般/期待/無法判讀）
- summary: 傷況摘要（繁體中文，50字內）
- actions: 建議處置步驟（陣列，每項15字內，最多3項）
- march: 物件，包含以下欄位（未提及設為 null）：
  - m_hemorrhage: 大出血處置描述
  - a_airway: 呼吸道處置描述
  - r_respiration: 呼吸狀況描述
  - c_circulation: 循環狀況描述
  - h_hypothermia: 低體溫處置描述
- vitals: 物件，包含（未提及設為 null）：
  - consciousness: 意識狀態 (A/V/P/U)
  - gcs: GCS 字串如 "E4V5M6"（若有提及）
  - hr: 脈搏
  - bp: 血壓
  - spo2: 血氧
  - temp: 體溫
  - rr: 呼吸次數
- trauma_codes: 創傷分類代碼字母陣列，如 ["E", "L"]（無則空陣列）
- mechanism_codes: 機轉代碼數字陣列，如 [5]（無則空陣列）
- special_population: 特殊族群標記陣列，如 ["兒童"]（無則空陣列）
- mist: MIST 回報摘要物件：
  - m_mechanism: 受傷機轉
  - i_injuries: 已發現傷勢/疾患
  - s_signs: 生命徵象
  - t_treatment: 已做處置

只回覆 JSON，不要其他文字。"""


def triage(transcript: str) -> dict:
    """Call Gemini API to perform START triage on the transcript.

    Args:
        transcript: The transcribed speech text.

    Returns:
        Dict with triage_level, triage_label, summary, actions.

    Raises:
        RuntimeError: If Gemini API fails or returns invalid JSON.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=TRIAGE_PROMPT.format(transcript=transcript),
    )

    raw_text = response.text.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        raw_text = "\n".join(lines).strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini 回傳非 JSON 格式: {e}")

    # Validate required fields
    required = ["triage_level", "triage_label", "summary", "actions",
                "march", "vitals", "mist"]
    for field in required:
        if field not in result:
            raise RuntimeError(f"Gemini 回傳缺少欄位: {field}")

    valid_levels = {"black", "red", "yellow", "green", "unknown"}
    if result["triage_level"] not in valid_levels:
        raise RuntimeError(f"無效的 triage_level: {result['triage_level']}")

    return result
