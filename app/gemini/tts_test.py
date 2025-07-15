"""
Gemini 2.5 Flash TTS ─ チャンク内容を列挙して確認するだけのスクリプト
必要ライブラリ:
  google-genai >= 1.21.0
"""

import os, sys
from google import genai
from google.genai import types

# ======================  パス & イベントループ初期化  ======================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)
from app.utils import _get_Gemini_API_key  # ← API キー取得ヘルパ

# ───── Gemini 初期化 ────────────────────────────────
client = genai.Client(api_key=_get_Gemini_API_key())
MODEL, VOICE = "gemini-2.5-flash-preview-tts", "Kore"
cfg = types.GenerateContentConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)
        )
    ),
)


# ───── チャンクを列挙して print ──────────────────────
def list_tts_chunks(prompt: str):
    """
    prompt を TTS でストリーミングし、受信した各チャンクの
    バイト長と先頭 30 バイトだけを print する。
    """
    for i, chunk in enumerate(
        client.models.generate_content_stream(
            model=MODEL,
            contents=prompt,
            config=cfg,
        )
    ):
        # Gemini 側の仕様で空チャンクが来る可能性あり
        if not chunk.candidates:
            print(f"[{i:04d}]  ── <empty / skipped>")
            continue

        data: bytes = chunk.candidates[0].content.parts[0].inline_data.data
        head = data[:30]  # 先頭 30 バイトだけプレビュー
        print(f"[{i:04d}] {len(data):6d} bytes  |  {head!r}")


if __name__ == "__main__":
    sample_text = (
        "こんにちは。こちらは低遅延 TTS の動作確認用のロングテキストです。"
        "Gemini 2.5 Flash ではレスポンスが複数のチャンクに分割されるので、"
        "チャンクサイズや分割タイミングを観察してみましょう。"
        "文章が長くなるほどチャンク数が増えるはずです。"
    )
    list_tts_chunks(sample_text)
