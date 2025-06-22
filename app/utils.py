import google.genai as genai  # ← ここを修正
from google.genai import types
import os, wave, io
import logging
import base64
from google.cloud import bigquery
from datetime import date
from dateutil.relativedelta import relativedelta
import vertexai
from vertexai.generative_models import (
    GenerativeModel,
    Part,
    GenerationConfig,
    ChatSession,
)
from dotenv import load_dotenv
import pandas as pd

# `.env` ファイルを読み込む
load_dotenv("credential/.env")
CREDENTIAL_PATH = "credential/tu-connectedlife-9fb1acc86198.json"

MODEL = "gemini-2.5-flash-preview-04-17"
TEST_TABLE = "tu-connectedlife.fitbit.activity_summary"


class SQL_EXECUTION:
    def __init__(self):
        try:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIAL_PATH
            self.client = bigquery.Client()
        except Exception as e:
            logging.error(f"Error initializing BigQuery client: {e}")
            raise

    def run_query(self, query):
        try:
            query_job = self.client.query(query)
            results = query_job.result()
            return results
        except Exception as e:
            logging.error(f"Error executing query: {e}")
            raise


class Gemini_Execution:
    def __init__(self):
        try:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIAL_PATH
            self.client = bigquery.Client()
        except Exception as e:
            logging.error(f"Error initializing BigQuery client: {e}")
            raise

    def run_prompt(self, prompt):
        # 環境変数を利用する
        PROJECT_ID = os.environ.get("PROJECT_ID")
        LOCATION = os.environ.get("LOCATION")
        vertexai.init(project=PROJECT_ID, location=LOCATION)

        model = GenerativeModel(MODEL)
        chat = model.start_chat()

        response = chat.send_message(prompt)
        return response.text


class Gemini_TTS_Execution:
    def __init__(self):
        try:
            self.client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        except Exception as e:
            logging.error(f"Error initializing BigQuery client: {e}")
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


class GeminiChatExecution:
    """Vertex AI Gemini と対話するシンプルなチャットクラス"""

    # デフォルトモデル（必要に応じて pro / ultra 等へ変更）
    DEFAULT_MODEL = "gemini-2.5-flash-preview-04-17"

    def __init__(
        self,
        project_id: str | None = None,
        location: str | None = None,
        model_name: str | None = None,
        generation_config: GenerationConfig | None = None,
        system_prompt: str | None = None,  # ★ 追加: 初期システムプロンプト
    ):
        """
        Parameters
        ----------
        project_id, location : 環境変数 PROJECT_ID / LOCATION を既定値として利用
        model_name           : 省略時 DEFAULT_MODEL
        generation_config    : 省略時  temperature=0.7, top_p=0.95, max_output_tokens=1024
        system_prompt        : 省略時 なし
        """
        try:
            # ① Vertex AI 初期化 -------------------------------------------------
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIAL_PATH
            self.client = bigquery.Client()
            PROJECT_ID = os.environ.get("PROJECT_ID")
            LOCATION = os.environ.get("LOCATION")
            vertexai.init(project=PROJECT_ID, location=LOCATION)

            # ② GenerationConfig（無指定ならデフォルトを用意） ------------------
            self._generation_config = generation_config or GenerationConfig(
                temperature=0.7, top_p=0.95, max_output_tokens=8092
            )

            self._model_name = model_name or self.DEFAULT_MODEL

            # ③ GenerativeModel インスタンス生成（← config はここに渡す） -------
            self._model: GenerativeModel = GenerativeModel(
                self._model_name,
                generation_config=self._generation_config,
                system_instruction=[system_prompt] if system_prompt else None,
            )

            # ④ チャットセッション開始（ここでは引数なし） ----------------------
            self._chat: ChatSession = self._model.start_chat(response_validation=False)

        except Exception as e:
            logging.error(f"[GeminiChat] init error: {e}")
            raise

    # --------------------------------------------------------------------------
    # system 指示を与える：context 付きでセッションを再生成する方法が確実
    # --------------------------------------------------------------------------
    def set_system_prompt(self, system_text: str) -> None:
        """
        モデルの振る舞いを変えたいときは新しいセッションを作り直す。
        `context` 引数は新しいSDK用。古いSDKではモデル自体にシステム指示を与える。
        """
        # モデルをシステム指示付きで再生成
        self._model = GenerativeModel(
            self._model_name,
            generation_config=self._generation_config,
            system_instruction=[system_text],
        )
        # 新しいモデルからチャットセッションを開始
        self._chat = self._model.start_chat(response_validation=False)

    # --------------------------------------------------------------------------
    # ユーザーメッセージ送信
    # --------------------------------------------------------------------------
    def send_message(
        self,
        user_text: str,
        generation_config: GenerationConfig | None = None,
    ) -> str:
        """
        generation_config をその都度変更したい場合は引数で渡す。
        渡さなければコンストラクタの既定値を使う。
        """
        try:
            response = self._chat.send_message(
                user_text,
                generation_config=generation_config or self._generation_config,
            )
            return response.text.strip()
        except TypeError:
            # 古い SDK では generation_config が未対応→付け直して再送
            response = self._chat.send_message(user_text)
            return response.text.strip()
        except Exception as e:
            logging.error(f"[GeminiChat] send_message error: {e}")
            raise

    # --------------------------------------------------------------------------
    # 履歴取得（デバッグ用）
    # --------------------------------------------------------------------------
    def history(self):
        """チャット履歴を list[dict] で返す"""
        return [
            {"role": m.role, "content": (m.parts[0].text if m.parts else "")}
            for m in self._chat.history
        ]


if __name__ == "__main__":
    # テスト用のクラスインスタンスを作成
    sql_exec = SQL_EXECUTION()
    gemini_exec = Gemini_Execution()
    tts_exec = Gemini_TTS_Execution()
    chat_exec = GeminiChatExecution(
        system_prompt="あなたは親切な日本語の AI アシスタントです。"
    )
    print(chat_exec.send_message("こんにちは！元気ですか？"))
