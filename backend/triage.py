"""Claude API START triage module for STAT."""

import json
import os

import anthropic

TRIAGE_PROMPT = """你是一位緊急醫療專業人員，負責依照 START 檢傷系統對傷患進行分類。

根據以下口述內容，判讀傷患的檢傷級別，並輸出結構化 JSON。

判讀規則：
- 黑（expectant）：無呼吸（開放呼吸道後仍無）
- 紅（immediate）：呼吸>30次/分、無橈動脈脈搏、無法遵從指令
- 黃（delayed）：傷情嚴重但暫時穩定
- 綠（minor）：可自行走動

特殊情況處理：
- 若口述內容模糊、資訊不足以判斷檢傷級別，將 triage_level 設為 "unknown"
- 若口述內容明顯為非傷患相關的語音（如閒聊、環境噪音轉錄），同樣設為 "unknown"
- 若語音辨識結果為亂碼或無意義文字，設為 "unknown"
- 設為 "unknown" 時，summary 應說明無法判讀的原因，actions 應建議操作者如何補充資訊

口述內容：{transcript}

請以 JSON 格式回覆，包含：
- triage_level: "black" | "red" | "yellow" | "green" | "unknown"
- triage_label: 對應中文名稱（unknown 對應「無法判讀」）
- summary: 傷況摘要（繁體中文，50字內）
- actions: 建議處置步驟（陣列，每項15字內，最多3項）

只回覆 JSON，不要其他文字。"""


def triage(transcript: str) -> dict:
    """Call Claude API to perform START triage on the transcript.

    Args:
        transcript: The transcribed speech text.

    Returns:
        Dict with triage_level, triage_label, summary, actions.

    Raises:
        RuntimeError: If Claude API fails or returns invalid JSON.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": TRIAGE_PROMPT.format(transcript=transcript),
            }
        ],
    )

    raw_text = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        raw_text = "\n".join(lines).strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude 回傳非 JSON 格式: {e}")

    # Validate required fields
    required = ["triage_level", "triage_label", "summary", "actions"]
    for field in required:
        if field not in result:
            raise RuntimeError(f"Claude 回傳缺少欄位: {field}")

    valid_levels = {"black", "red", "yellow", "green", "unknown"}
    if result["triage_level"] not in valid_levels:
        raise RuntimeError(f"無效的 triage_level: {result['triage_level']}")

    return result
