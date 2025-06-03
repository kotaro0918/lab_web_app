import pandas as pd
import numpy as np
import os
import sys
from tqdm import tqdm
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from app.jobs.nutrition import get_nutrition_by_user
from app.gemini.generate_alert import generate_weekly_nutrition_alert


def weekly_nutrition_pipeline(user_id, today):
    """
    ユーザーの栄養データを処理し、アラートを生成するパイプライン関数
    Args:
        user_id (str): ユーザーID
        today (datetime): 処理日
    Returns:
        dict: 処理結果を含む辞書
    """
    # 1週間前の日付を計算
    one_week_ago = today - pd.DateOffset(weeks=1)
    end_date = today - pd.DateOffset(days=1)

    current_nutrition_data = get_nutrition_by_user(user_id, one_week_ago, end_date)
    # 平均値の計算
    sum_energy = (
        sum(current_nutrition_data["energy"])
        if current_nutrition_data.get(
            "energy"
        )  # .get() を使ってキーが存在しない場合にも対応
        else 0
    )
    sum_protein = (
        sum(current_nutrition_data["protein"])  # np.sum から sum に変更 (どちらでも可)
        if current_nutrition_data.get(
            "protein"
        )  # .get() を使ってキーが存在しない場合にも対応
        else 0
    )
    protein_ratio = sum_protein * 4 / sum_energy if sum_energy > 0 else 0
    # アラートの生成
    weekly_nutrition_alert = generate_weekly_nutrition_alert(
        current_nutrition_data, protein_ratio
    )

    return {
        "user_id": user_id,
        "date": today,
        "weekly_nutrition_alert": weekly_nutrition_alert,
        "current_nutrition_data": current_nutrition_data,
        "protein_ratio": protein_ratio,
    }


if __name__ == "__main__":
    start_date = datetime(2024, 6, 1)
    end_date = datetime(2024, 6, 7)
    user_id = "ashita14977"  # 適切なユーザーIDを指定してください
    # パイプラインを実行
    result = weekly_nutrition_pipeline(user_id, end_date)
    print(result)
