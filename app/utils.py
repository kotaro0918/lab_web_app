import google.genai as genai  # ← そのまま
from google.genai import types  # ← そのまま
import os, wave, io, json, logging
from tempfile import NamedTemporaryFile  # （未使用になっても import は触らない）
from google.cloud import bigquery
from datetime import date
from dateutil.relativedelta import relativedelta
import streamlit as st
import vertexai
from vertexai.generative_models import (
    GenerativeModel,
    Part,
    GenerationConfig,
    ChatSession,
)
from dotenv import load_dotenv
import pandas as pd


MODEL = "gemini-2.5-flash"
TEST_TABLE = "tu-connectedlife.fitbit.activity_summary"


# ───────────────────────────────────────────────────────────────
#  一時ファイルを使わず、メモリ上だけでサービスアカウントを扱う
# ───────────────────────────────────────────────────────────────
def _to_builtin(o):
    """streamlit.secrets の AttrDict / list をネイティブ型へ再帰変換"""
    if isinstance(o, dict):
        return {k: _to_builtin(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_to_builtin(v) for v in o]
    return o


def _build_credentials():
    """secrets から Credentials オブジェクトを生成（メモリ完結）"""
    from google.oauth2 import service_account  # ← import はローカルで実行

    raw = st.secrets["google_credentials"]  # JSON 文字列 or AttrDict
    info = json.loads(raw) if isinstance(raw, str) else _to_builtin(raw)
    return service_account.Credentials.from_service_account_info(info)


def _get_Gemini_API_key() -> str:
    """Gemini API キーを環境変数 or secrets から取得して返す"""
    # ① 既に環境変数にあるならそれを使う
    if "GOOGLE_API_KEY" in os.environ:
        return os.environ["GOOGLE_API_KEY"]

    # ② secrets.toml に定義されているか確認
    key = st.secrets["GOOGLE_API_KEY"]["key"]
    if not key:
        # 両方になければエラー
        raise ValueError(
            "Gemini の API キーが見つかりません。"
            "環境変数 GOOGLE_API_KEY か secrets['GOOGLE_API_KEY'] に設定してください。"
        )

    # ③ 見つかったキーを環境変数にもセットして返す
    os.environ["GOOGLE_API_KEY"] = key
    return key


CREDS = _build_credentials()
PROJECT_ID = CREDS.project_id
LOCATION = (
    "us-central1"  # os.environ.get("LOCATION", "asia-northeast1")  # .env に合わせて
)


# ───────────────────────────────────────────────────────────────
#  クライアント生成部：Credentials を明示的に渡す
# ───────────────────────────────────────────────────────────────
class SQL_EXECUTION:
    def __init__(self):
        try:
            self.client = bigquery.Client(credentials=CREDS, project=PROJECT_ID)
        except Exception as e:
            logging.error(f"Error initializing BigQuery client: {e}")
            raise

    def run_query(self, query):
        try:
            query_job = self.client.query(query)
            return query_job.result()
        except Exception as e:
            logging.error(f"Error executing query: {e}")
            raise


class Gemini_Execution:
    def __init__(self):
        try:
            self.client = bigquery.Client(credentials=CREDS, project=PROJECT_ID)
        except Exception as e:
            logging.error(f"Error initializing BigQuery client: {e}")
            raise

    def run_prompt(self, prompt):
        vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=CREDS)
        model = GenerativeModel(MODEL)
        chat = model.start_chat()
        return chat.send_message(prompt).text


class Gemini_TTS_Execution:
    def __init__(self):
        try:
            self.client = genai.Client(api_key=_get_Gemini_API_key())
        except Exception as e:
            logging.error(f"Error initializing Gemini client: {e}")
            raise

    def run_tts(self, text: str) -> bytes:
        resp = self.client.models.generate_content(
            model="gemini-2.5-pro-preview-tts",
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Kore"
                        )
                    )
                ),
            ),
        )
        pcm = resp.candidates[0].content.parts[0].inline_data.data
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(24_000)  # 24 kHz
            wf.writeframes(pcm)
        return buf.getvalue()  # WAV ヘッダ + 音声


VOICE_NAME = "Kore"
MODEL_NAME = "gemini-2.5-flash-preview-tts"
RATE_HZ = 24_000
WIDTH = 2  # 16-bit PCM
CHANNELS = 1


class GeminiTTSStream:
    """Gemini TTS を低遅延ストリームで再生・取得するユーティリティ"""

    def __init__(self, voice_name: str = VOICE_NAME, model: str = MODEL_NAME):
        try:
            self._client = genai.Client(api_key=_get_Gemini_API_key())
        except Exception as e:
            logging.error(f"[GeminiTTSStream] init error: {e}")
            raise
        self._model = model
        self._config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            ),
        )

    # —────────────────────────────────────────────────────
    # 同期ストリーム版: for chunk in stream_tts("text")
    # —────────────────────────────────────────────────────
    def stream_tts(self, text: str):
        resp = self._client.models.generate_content(
            model=self._model,
            contents=text,
            config=self._config,
            stream=True,  # ★ ここがポイント
        )
        for chunk in resp:
            if not chunk.candidates:
                continue
            yield chunk.candidates[0].content.parts[0].inline_data.data

    # —────────────────────────────────────────────────────
    # WAV エンコードしたバイト列を返したい場合（後段で st.audio 用）
    # —────────────────────────────────────────────────────
    def to_wav(self, pcm_iterable) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(WIDTH)
            wf.setframerate(RATE_HZ)
            for pcm in pcm_iterable:
                wf.writeframes(pcm)
        return buf.getvalue()


class GeminiChatExecution:
    """Vertex AI Gemini と対話するシンプルなチャットクラス"""

    DEFAULT_MODEL = "gemini-2.5-flash-preview-04-17"

    def __init__(
        self,
        model_name: str | None = None,
        generation_config: GenerationConfig | None = None,
        system_prompt: str | None = None,
    ):
        try:
            self.client = bigquery.Client(credentials=CREDS, project=PROJECT_ID)
            vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=CREDS)

            self._generation_config = generation_config or GenerationConfig(
                temperature=0.7, top_p=0.95, max_output_tokens=8092
            )
            self._model_name = model_name or self.DEFAULT_MODEL

            self._model: GenerativeModel = GenerativeModel(
                self._model_name,
                generation_config=self._generation_config,
                system_instruction=[system_prompt] if system_prompt else None,
            )
            self._chat: ChatSession = self._model.start_chat(response_validation=False)

        except Exception as e:
            logging.error(f"[GeminiChat] init error: {e}")
            raise

    def set_system_prompt(self, system_text: str) -> None:
        self._model = GenerativeModel(
            self._model_name,
            generation_config=self._generation_config,
            system_instruction=[system_text],
        )
        self._chat = self._model.start_chat(response_validation=False)

    def send_message(
        self,
        user_text: str,
        generation_config: GenerationConfig | None = None,
    ) -> str:
        try:
            resp = self._chat.send_message(
                user_text,
                generation_config=generation_config or self._generation_config,
            )
            return resp.text.strip()
        except TypeError:
            return self._chat.send_message(user_text).text.strip()
        except Exception as e:
            logging.error(f"[GeminiChat] send_message error: {e}")
            raise

    def send_audio(self, wav_bytes: bytes) -> str:
        try:
            audio_part = Part.from_data(mime_type="audio/wav", data=wav_bytes)
            prompt_parts = ["この音声を日本語で文字に起こしてください。", audio_part]
            return self._model.generate_content(prompt_parts).text
        except Exception as e:
            logging.error(f"[GeminiChat] send_audio error: {e}")
            return f"音声認識エラー: {e}"

    def history(self):
        return [
            {"role": m.role, "content": (m.parts[0].text if m.parts else "")}
            for m in self._chat.history
        ]


if __name__ == "__main__":
    sql_exec = SQL_EXECUTION()
    gem_exec = Gemini_Execution()
    tts_exec = Gemini_TTS_Execution()
    chat_exec = GeminiChatExecution(
        system_prompt="あなたは親切な日本語の AI アシスタントです。"
    )
    print(chat_exec.send_message("こんにちは！元気ですか？"))
