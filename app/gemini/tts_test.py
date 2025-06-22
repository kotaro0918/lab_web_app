from google import genai
from google.genai import types
import os, wave
from dotenv import load_dotenv

load_dotenv("credential/.env")
client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])


def save_wav(path: str, pcm: bytes, sr=24_000, ch=1, width=2):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(ch)
        wf.setsampwidth(width)  # 16-bit (=2bytes)
        wf.setframerate(sr)
        wf.writeframes(pcm)  # そのまま書く !!


resp = client.models.generate_content(
    model="gemini-2.5-pro-preview-tts",
    contents="楽しく「素敵な一日をお過ごしください！」と言ってください。",
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
            )
        ),
    ),
)

pcm_bytes = resp.candidates[0].content.parts[0].inline_data.data
print("PCM size:", len(pcm_bytes))  # 2〜3 KB 程度あれば OK
save_wav("japanese_tts.wav", pcm_bytes)
print("✅ 完了 – japanese_tts.wav")
