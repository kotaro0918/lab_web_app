import os
import sys
from datetime import datetime
import asyncio
import pandas as pd
import numpy as np
from tqdm import tqdm

# ルートパスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# アプリ依存モジュール
from app.jobs.nutrition import get_nutrition_by_user
from app.gemini.generate_alert import generate_weekly_nutrition_alert


# --------------------------------------------------------------------------- #
#                        非同期版 weekly_nutrition_pipeline
# --------------------------------------------------------------------------- #
async def weekly_nutrition_pipeline(
    user_id: str, today: datetime, user_profile: str = ""
) -> dict:
    """
    指定ユーザーの 1 週間分の栄養データを取得し、Gemini でアラートを生成する。

    Returns
    -------
    dict
        - weekly_nutrition_alert : str
        - current_nutrition_data : dict
        - protein_ratio          : float
        - user_id, date          : 入力値をそのまま保持
    """
    # ── 期間計算 ───────────────────────────────────────────────
    one_week_ago = today - pd.DateOffset(weeks=1)
    two_week_ago = today - pd.DateOffset(weeks=2)
    end_date = today - pd.DateOffset(days=1)

    # ── データ取得（同期関数をスレッドへ）────────────────────
    current_nutrition_data = await asyncio.to_thread(
        get_nutrition_by_user, user_id, one_week_ago, end_date
    )
    previous_nutrition_data = await asyncio.to_thread(
        get_nutrition_by_user, user_id, two_week_ago, one_week_ago
    )
    # ── 集計 ───────────────────────────────────────────────
    current_sum_energy = sum(current_nutrition_data.get("energy", []))
    current_sum_protein = sum(current_nutrition_data.get("protein", []))
    current_protein_ratio = (
        (current_sum_protein * 4 / current_sum_energy) if current_sum_energy > 0 else 0
    )

    previous_sum_energy = sum(previous_nutrition_data.get("energy", []))
    previous_sum_protein = sum(previous_nutrition_data.get("protein", []))
    previous_protein_ratio = (
        (previous_sum_protein * 4 / previous_sum_energy)
        if previous_sum_energy > 0
        else 0
    )
    # ── アラート生成（Gemini 呼び出しを await）────────────────
    weekly_nutrition_alert = await generate_weekly_nutrition_alert(
        current_nutrition_data, current_protein_ratio, user_profile
    )
    # 0を除外したタンパク質の平均値を計算
    current_protein_values = [
        x for x in current_nutrition_data.get("protein", []) if x > 0
    ]
    current_protein_mean = (
        np.mean(current_protein_values) if current_protein_values else 0
    )

    previous_protein_values = [
        x for x in previous_nutrition_data.get("protein", []) if x > 0
    ]
    previous_protein_mean = (
        np.mean(previous_protein_values) if previous_protein_values else 0
    )

    return {
        "user_id": user_id,
        "date": today,
        "weekly_nutrition_alert": weekly_nutrition_alert,
        "current_nutrition_data": current_nutrition_data,
        "current_protein_ratio": current_protein_ratio,
        "current_protein_mean": current_protein_mean,
        "previous_protein_mean": previous_protein_mean,
        "previous_nutrition_data": previous_nutrition_data,
        "previous_protein_ratio": previous_protein_ratio,
    }


# --------------------------------------------------------------------------- #
#                               テスト実行ブロック
# --------------------------------------------------------------------------- #
async def _test():
    """
    - 固定ユーザー & 日付でパイプラインを実行
    - 結果を表示
    """
    user_id = "ashita14977"  # 適切なユーザー ID に置き換えてください
    today = datetime(2024, 6, 7)  # today を「週終わりの日付」として想定

    result = await weekly_nutrition_pipeline(user_id, today)
    print("=== Weekly Nutrition Pipeline Result ===")
    print(result)


if __name__ == "__main__":
    asyncio.run(_test())
