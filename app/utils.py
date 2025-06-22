import google.genai as genai  # ← ここを修正
from google.genai import types
import os, wave, io
import logging
import base64
from google.cloud import bigquery
from datetime import date
from dateutil.relativedelta import relativedelta
import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
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


if __name__ == "__main__":
    # テスト用のクラスインスタンスを作成
    sql_exec = SQL_EXECUTION()
    gemini_exec = Gemini_Execution()
    tts_exec = Gemini_TTS_Execution()
    text = "こんにちは、元気ですか？"
    audio_data = tts_exec.run_tts(text)
    with open("output.wav", "wb") as f:
        f.write(audio_data)
    print("TTS 音声を output.wav に保存しました。")
