# -*- coding: utf-8 -*-
"""
CSV（あすけん栄養サマリー）を BigQuery テーブル
tu-connectedlife.fitbit.asuken_summary に
  1) スキーマに沿って整形
  2) 空テーブルを作成（無ければスキップ）
  3) データを INSERT（append）する
まで一括で実行するスクリプト
"""

import os
import sys
from datetime import datetime
import pandas as pd
from google.cloud import bigquery

# --------------------------------------------------
# 自前ユーティリティ
# --------------------------------------------------
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from app.utils import (
    SQL_EXECUTION,
    CREDENTIAL_PATH,
)  # noqa: E402 pylint: disable=wrong-import-position

# --------------------------------------------------
# 定数
# --------------------------------------------------
NUTRITION_TABLE = "tu-connectedlife.fitbit.asuken_summary"
CSV_PATH = "data/あすけんrawデータ 2.csv"

# --------------------------------------------------
# BigQuery スキーマ（13 列）
# --------------------------------------------------
BQ_SCHEMA = [
    bigquery.SchemaField("login_id", "STRING"),
    bigquery.SchemaField("record_date", "DATE"),
    bigquery.SchemaField("meal_type", "STRING"),
    bigquery.SchemaField("manual_input_time", "TIME"),
    bigquery.SchemaField("created_date", "DATE"),
    bigquery.SchemaField("created_time", "TIME"),
    bigquery.SchemaField("energy", "FLOAT"),
    bigquery.SchemaField("water", "FLOAT"),
    bigquery.SchemaField("protein", "FLOAT"),
    bigquery.SchemaField("lipid", "FLOAT"),
    bigquery.SchemaField("carbohydrate", "FLOAT"),
    bigquery.SchemaField("cholesterol", "FLOAT"),
    bigquery.SchemaField("dietary_fiber", "FLOAT"),
]
SCHEMA_COLS = [f.name for f in BQ_SCHEMA]


# --------------------------------------------------
# DataFrame 準備
# --------------------------------------------------
def prepare_dataframe(csv_path: str) -> pd.DataFrame:
    """CSV → DataFrame → スキーマ列抽出＋型整形"""
    df = pd.read_csv(csv_path)

    # 必須列チェック
    missing = [c for c in SCHEMA_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame に存在しない列があります: {missing}")

    df = df[SCHEMA_COLS].copy()

    # 日付・時刻型へ
    df["record_date"] = pd.to_datetime(df["record_date"]).dt.date
    df["created_date"] = pd.to_datetime(df["created_date"]).dt.date

    time_fmt = "%H:%M"
    df["manual_input_time"] = pd.to_datetime(
        df["manual_input_time"], format=time_fmt, errors="coerce"
    ).dt.time
    df["created_time"] = pd.to_datetime(
        df["created_time"], format=time_fmt, errors="coerce"
    ).dt.time

    # 数値は float へ変換
    numeric_cols = [
        "energy",
        "water",
        "protein",
        "lipid",
        "carbohydrate",
        "cholesterol",
        "dietary_fiber",
    ]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")

    return df


# --------------------------------------------------
# BigQuery 操作
# --------------------------------------------------
def ensure_table(
    client: bigquery.Client, table_id: str, schema: list[bigquery.SchemaField]
) -> None:
    """存在しなければテーブルを作成"""
    try:
        client.get_table(table_id)
        print(f"👍  Table exists: {table_id}")
    except Exception:
        table = bigquery.Table(table_id, schema=schema)
        client.create_table(table)
        print(f"✅  Created table: {table_id}")


def insert_dataframe(client: bigquery.Client, table_id: str, df: pd.DataFrame) -> None:
    """DataFrame を BigQuery に INSERT（append）"""
    job_config = bigquery.LoadJobConfig(
        schema=BQ_SCHEMA,
        write_disposition="WRITE_APPEND",  # 追記
    )
    load_job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    load_job.result()  # 完了待ち
    print(f"✅  Inserted {load_job.output_rows} rows into {table_id}")


# --------------------------------------------------
# メイン処理
# --------------------------------------------------
if __name__ == "__main__":
    # 認証
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIAL_PATH
    bq_client = bigquery.Client()

    # DataFrame 作成
    df_bq = prepare_dataframe(CSV_PATH)

    # テーブル作成（存在チェック込み）
    ensure_table(bq_client, NUTRITION_TABLE, BQ_SCHEMA)

    # データ INSERT
    insert_dataframe(bq_client, NUTRITION_TABLE, df_bq)
