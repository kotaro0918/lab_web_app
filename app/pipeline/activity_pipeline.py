import asyncio
import time
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

# tqdm は進捗バーを追加したいときに活用してください
from tqdm import tqdm

# ---- パス設定 ---------------------------------------------------------------
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# ---- アプリケーション依存モジュール ----------------------------------------
from app.jobs.activity import get_activity_by_user, get_random_activity_users
from app.gemini.generate_alert import (
    generate_monthly_active_alert,
    generate_monthly_step_alert,
    generate_weekly_active_alert,
    generate_weekly_step_alert,
)

# ============================================================================ #
#                              非同期パイプライン
# ============================================================================ #


async def weekly_activity_pipeline(
    user_id: str, today: datetime, user_profile: str = ""
):
    """
    指定ユーザーの 1 週間分の活動データを取得して
    週次アラートを非同期生成するパイプライン
    """
    _t0 = time.perf_counter()  # ---- 計測開始 ----

    # 期間計算
    two_weeks_ago = today - pd.DateOffset(weeks=2)
    one_week_ago = today - pd.DateOffset(weeks=1)
    end_date = today - pd.DateOffset(days=1)

    # 活動データ取得
    previous_activity_data = get_activity_by_user(user_id, two_weeks_ago, one_week_ago)
    current_activity_data = get_activity_by_user(user_id, one_week_ago, end_date)

    # 平均値計算
    current_steps_values = [x for x in current_activity_data["steps"] if x > 0]
    current_steps_mean = np.mean(current_steps_values) if current_steps_values else 0
    previous_steps_mean = (
        np.mean(previous_activity_data["steps"])
        if previous_activity_data["steps"]
        else 0
    )
    current_activity_values = [
        x for x in current_activity_data["activity_minutes"] if x > 0
    ]
    current_activity_mean = (
        np.mean(current_activity_values) if current_activity_values else 0
    )
    previous_activity_mean = (
        np.mean(previous_activity_data["activity_minutes"])
        if previous_activity_data["activity_minutes"]
        else 0
    )
    current_sedentary_values = [
        x for x in current_activity_data["sedentary_minutes"] if x > 0
    ]
    current_sedentary_mean = (
        np.mean(current_sedentary_values) if current_sedentary_values else 0
    )
    previous_sedentary_values = [
        x for x in previous_activity_data["sedentary_minutes"] if x > 0
    ]
    previous_sedentary_mean = (
        np.mean(previous_sedentary_values) if previous_sedentary_values else 0
    )
    current_calories_out_values = [
        x for x in current_activity_data["calories_out"] if x > 0
    ]
    current_calories_out_mean = (
        np.mean(current_calories_out_values) if current_calories_out_values else 0
    )

    previous_calories_out_values = [
        x for x in previous_activity_data["calories_out"] if x > 0
    ]
    previous_calories_out_mean = (
        np.mean(previous_calories_out_values) if previous_calories_out_values else 0
    )
    # 非同期アラート生成
    weekly_step_alert, weekly_active_alert = await asyncio.gather(
        generate_weekly_step_alert(
            current_activity_data["steps"],
            previous_activity_data["steps"],
            current_steps_mean,
            previous_steps_mean,
            user_profile,
        ),
        generate_weekly_active_alert(
            current_activity_data["activity_minutes"],
            previous_activity_data["activity_minutes"],
            current_activity_mean,
            previous_activity_mean,
            user_profile,
        ),
    )

    elapsed = time.perf_counter() - _t0  # ---- 計測終了 ----

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
        "current_sedentary_mean": current_sedentary_mean,
        "previous_sedentary_mean": previous_sedentary_mean,
        "current_calories_out_mean": current_calories_out_mean,
        "previous_calories_out_mean": previous_calories_out_mean,
        "elapsed_seconds": elapsed,  # ★ 追加 ★
    }


async def monthly_activity_pipeline(
    user_id: str, today: datetime, user_profile: str = ""
):
    """
    指定ユーザーの 1 か月分の活動データを取得して
    月次アラートを非同期生成するパイプライン
    """
    _t0 = time.perf_counter()  # ---- 計測開始 ----

    one_month_ago = today - pd.DateOffset(months=1)
    end_date = today - pd.DateOffset(days=1)

    current_activity_data = get_activity_by_user(user_id, one_month_ago, end_date)

    current_steps_values = [x for x in current_activity_data["steps"] if x > 0]
    current_steps_mean = np.mean(current_steps_values) if current_steps_values else 0

    current_activity_values = [
        x for x in current_activity_data["activity_minutes"] if x > 0
    ]
    current_activity_mean = (
        np.mean(current_activity_values) if current_activity_values else 0
    )

    monthly_step_alert, monthly_active_alert = await asyncio.gather(
        generate_monthly_step_alert(
            current_activity_data["steps"], current_steps_mean, user_profile
        ),
        generate_monthly_active_alert(
            current_activity_data["activity_minutes"],
            current_activity_mean,
            user_profile,
        ),
    )

    elapsed = time.perf_counter() - _t0  # ---- 計測終了 ----

    return {
        "user_id": user_id,
        "date": today,
        "monthly_step_alert": monthly_step_alert,
        "monthly_active_alert": monthly_active_alert,
        "current_activity_data": current_activity_data,
        "current_steps_mean": current_steps_mean,
        "current_activity_mean": current_activity_mean,
        "elapsed_seconds": elapsed,  # ★ 追加 ★
    }


# ============================================================================ #
#                              テスト実行ブロック
# ============================================================================ #


async def main():
    """
    テスト用エントリポイント:
    - ランダムユーザーを 1 名取得
    - 週次 & 月次パイプラインを並列実行
    """
    today = datetime(2024, 5, 1)

    # get_random_activity_users() は同期関数想定
    user_id = get_random_activity_users(
        limit=1,
        min_records=20,
        start_date=today - pd.DateOffset(months=1),
        end_date=today,
    )[0]

    # パイプラインを並列実行
    weekly_result, monthly_result = await asyncio.gather(
        weekly_activity_pipeline(user_id, today),
        monthly_activity_pipeline(user_id, today),
    )

    # 結果表示
    print(f"Weekly Result  (elapsed {weekly_result['elapsed_seconds']:.3f}s):")
    print(weekly_result)
    print()
    print(f"Monthly Result (elapsed {monthly_result['elapsed_seconds']:.3f}s):")
    print(monthly_result)


if __name__ == "__main__":
    asyncio.run(main())
