import os
import logging
from google.cloud import bigquery
from datetime import date
from dateutil.relativedelta import relativedelta
import vertexai
from vertexai.generative_models import GenerativeModel, Part
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


if __name__ == "__main__":

    sql_execution = SQL_EXECUTION()
    test_query = f"""
    SELECT * FROM `{TEST_TABLE}`
    LIMIT 10
    """
    results = sql_execution.run_query(test_query)
    for row in results:
        print(row)
    gemini_execution = Gemini_Execution()
    test_prompt = "What is the capital of France?"
    response = gemini_execution.run_prompt(test_prompt)
    if response:
        print(response)
    else:
        print("No response generated.")
