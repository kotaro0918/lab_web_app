import pandas as pd
import numpy as np
import os
import sys
from tqdm import tqdm
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from app.jobs.sleep import get_sleep_by_user, get_random_sleep_users
from app.gemini.generate_alert import (
    generate_monthly_sleep_alert,
    generate_weekly_sleep_alert,
)


def weekly_sleep_pipeline(user_id, today):
    """
    ユーザーの睡眠データを処理し、アラートを生成するパイプライン関数
    Args:
        user_id (str): ユーザーID
        today (datetime): 処理日
    Returns:
        dict: 処理結果を含む辞書
    """
    # 1週間前の日付を計算
    one_week_ago = today - pd.DateOffset(weeks=1)
    end_date = today - pd.DateOffset(days=1)

    current_sleep_data = get_sleep_by_user(user_id, one_week_ago, end_date)
    # 平均値の計算
    current_sleep_mean = (
        np.mean(current_sleep_data["total_minutes_asleep"])
        if current_sleep_data["total_minutes_asleep"]
        else 0
    )
    # アラートの生成
    weekly_sleep_alert = generate_weekly_sleep_alert(
        current_sleep_data["total_minutes_asleep"],
        current_sleep_mean,
    )

    return {
        "user_id": user_id,
        "date": today,
        "weekly_sleep_alert": weekly_sleep_alert,
        "current_sleep_mean": current_sleep_mean,
        "current_sleep_data": current_sleep_data,
    }


def monthly_sleep_pipeline(user_id, today):
    """
    ユーザーの睡眠データを処理し、アラートを生成するパイプライン関数
    Args:
        user_id (str): ユーザーID
        today (datetime): 処理日
    Returns:
        dict: 処理結果を含む辞書
    """
    # 1ヶ月前の日付を計算
    one_month_ago = today - pd.DateOffset(months=1)
    end_date = today - pd.DateOffset(days=1)

    current_sleep_data = get_sleep_by_user(user_id, one_month_ago, end_date)
    # 平均値の計算
    current_sleep_mean = (
        np.mean(current_sleep_data["total_minutes_asleep"])
        if current_sleep_data["total_minutes_asleep"]
        else 0
    )
    # アラートの生成
    monthly_sleep_alert = generate_monthly_sleep_alert(
        current_sleep_data["total_minutes_asleep"],
        current_sleep_mean,
    )

    return {
        "user_id": user_id,
        "date": today,
        "monthly_sleep_alert": monthly_sleep_alert,
        "current_sleep_mean": current_sleep_mean,
        "current_sleep_data": current_sleep_data,
    }


if __name__ == "__main__":
    # 例として、2024年4月1日を処理日とする
    today = datetime(2024, 6, 1)
    # ランダムなユーザーIDを取得
    user_id = get_random_sleep_users(
        limit=1,
        min_records=20,
        start_date=today - pd.DateOffset(month=1),
        end_date=today,
    )[0]
    # 週間睡眠パイプラインを実行
    weekly_sleep_result = weekly_sleep_pipeline(user_id, today)
    print(weekly_sleep_result)
    # 月間睡眠パイプラインを実行
    monthly_sleep_result = monthly_sleep_pipeline(user_id, today)
    print(monthly_sleep_result)
