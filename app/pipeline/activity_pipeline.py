import pandas as pd
import numpy as np
import os
import sys
from tqdm import tqdm
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from app.jobs.activity import get_activity_by_user, get_random_activity_users
from app.gemini.generate_alert import (
    generate_monthly_active_alert,
    generate_monthly_step_alert,
    generate_weekly_active_alert,
    generate_weekly_step_alert,
)


def weekly_activity_pipeline(user_id, today):
    """
    ユーザーの活動データを処理し、アラートを生成するパイプライン関数
    Args:
        user_id (str): ユーザーID
        today (datetime): 処理日
    Returns:
        None
    """
    # 1週間前の日付を計算
    two_week_ago = today - pd.DateOffset(weeks=2)
    one_week_ago = today - pd.DateOffset(weeks=1)
    end_date = today - pd.DateOffset(days=1)

    # 1週間の活動データを取得
    previous_activity_data = get_activity_by_user(user_id, two_week_ago, one_week_ago)
    current_activity_data = get_activity_by_user(user_id, one_week_ago, end_date)

    # 平均値の計算
    current_steps_mean = (
        np.mean(current_activity_data["steps"]) if current_activity_data["steps"] else 0
    )
    previous_steps_mean = (
        np.mean(previous_activity_data["steps"])
        if previous_activity_data["steps"]
        else 0
    )
    current_activity_mean = (
        np.mean(current_activity_data["activity_minutes"])
        if current_activity_data["activity_minutes"]
        else 0
    )
    previous_activity_mean = (
        np.mean(previous_activity_data["activity_minutes"])
        if previous_activity_data["activity_minutes"]
        else 0
    )

    # アラートの生成
    weekly_step_alert = generate_weekly_step_alert(
        current_activity_data["steps"],
        previous_activity_data["steps"],
        current_steps_mean,
        previous_steps_mean,
    )
    weekly_active_alert = generate_weekly_active_alert(
        current_activity_data["activity_minutes"],
        previous_activity_data["activity_minutes"],
        current_activity_mean,
        previous_activity_mean,
    )
    return {
        "user_id": user_id,
        "date": today,
        "weekly_step_alert": weekly_step_alert,
        "weekly_active_alert": weekly_active_alert,
        "current_activity_data": current_activity_data,
        "previous_activity_data": previous_activity_data,
        "current_steps_mean": current_steps_mean,
        "previous_steps_mean": previous_steps_mean,
        "current_activity_mean": current_activity_mean,
        "previous_activity_mean": previous_activity_mean,
    }


def monthly_activity_pipeline(user_id, today):
    """
    ユーザーの活動データを処理し、アラートを生成するパイプライン関数
    Args:
        user_id (str): ユーザーID
        today (datetime): 処理日
    Returns:
        None
    """
    # 1ヶ月前の日付を計算
    one_month_ago = today - pd.DateOffset(months=1)
    end_date = today - pd.DateOffset(days=1)

    # 1ヶ月の活動データを取得
    current_activity_data = get_activity_by_user(user_id, one_month_ago, end_date)

    # 平均値の計算
    current_steps_mean = (
        np.mean(current_activity_data["steps"]) if current_activity_data["steps"] else 0
    )
    current_activity_mean = (
        np.mean(current_activity_data["activity_minutes"])
        if current_activity_data["activity_minutes"]
        else 0
    )

    # アラートの生成
    monthly_step_alert = generate_monthly_step_alert(
        current_activity_data["steps"],
        current_steps_mean,
    )
    monthly_active_alert = generate_monthly_active_alert(
        current_activity_data["activity_minutes"],
        current_activity_mean,
    )

    return {
        "user_id": user_id,
        "date": today,
        "monthly_step_alert": monthly_step_alert,
        "monthly_active_alert": monthly_active_alert,
        "current_activity_data": current_activity_data,
        "current_steps_mean": current_steps_mean,
        "current_activity_mean": current_activity_mean,
    }


if __name__ == "__main__":
    # テスト用のユーザーIDと日付を指定
    today = datetime(2024, 5, 1)
    user_id = get_random_activity_users(
        limit=1,
        min_records=20,
        start_date=today - pd.DateOffset(month=1),
        end_date=today,
    )[0]
    # 1週間の活動データを処理
    weekly_result = weekly_activity_pipeline(user_id, today)
    print("Weekly Result:", weekly_result)

    # 1ヶ月の活動データを処理
    monthly_result = monthly_activity_pipeline(user_id, today)
    print("Monthly Result:", monthly_result)
