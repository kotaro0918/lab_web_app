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
from app.jobs.sleep import get_sleep_by_user, get_random_sleep_users
from app.gemini.generate_alert import (
    generate_monthly_sleep_alert,
    generate_weekly_sleep_alert,
)


# --------------------------------------------------------------------------- #
#                             非同期パイプライン
# --------------------------------------------------------------------------- #
async def weekly_sleep_pipeline(
    user_id: str, today: datetime, user_profile: str = ""
) -> dict:
    """
    1 週間分の睡眠データを取得し、週次アラートを生成する。
    """
    one_week_ago = today - pd.DateOffset(weeks=1)
    end_date = today - pd.DateOffset(days=1)

    # 同期関数をスレッドへ
    current_sleep_data = await asyncio.to_thread(
        get_sleep_by_user, user_id, one_week_ago, end_date
    )

    current_sleep_values = [
        x for x in current_sleep_data["total_minutes_asleep"] if x > 0
    ]
    current_sleep_mean = np.mean(current_sleep_values) if current_sleep_values else 0
    weekly_sleep_alert = await generate_weekly_sleep_alert(
        current_sleep_data["total_minutes_asleep"], current_sleep_mean, user_profile
    )

    return {
        "user_id": user_id,
        "date": today,
        "weekly_sleep_alert": weekly_sleep_alert,
        "current_sleep_mean": current_sleep_mean,
        "current_sleep_data": current_sleep_data,
    }


async def monthly_sleep_pipeline(
    user_id: str, today: datetime, user_profile: str = ""
) -> dict:
    """
    1 か月分の睡眠データを取得し、月次アラートを生成する。
    """
    one_month_ago = today - pd.DateOffset(months=1)
    end_date = today - pd.DateOffset(days=1)

    current_sleep_data = await asyncio.to_thread(
        get_sleep_by_user, user_id, one_month_ago, end_date
    )

    current_sleep_values = [
        x for x in current_sleep_data["total_minutes_asleep"] if x > 0
    ]
    current_sleep_mean = np.mean(current_sleep_values) if current_sleep_values else 0

    monthly_sleep_alert = await generate_monthly_sleep_alert(
        current_sleep_data["total_minutes_asleep"], current_sleep_mean, user_profile
    )

    return {
        "user_id": user_id,
        "date": today,
        "monthly_sleep_alert": monthly_sleep_alert,
        "current_sleep_mean": current_sleep_mean,
        "current_sleep_data": current_sleep_data,
    }


# --------------------------------------------------------------------------- #
#                               テスト実行ブロック
# --------------------------------------------------------------------------- #
async def _test():
    """
    ランダムユーザー 1 名で週次・月次パイプラインを並列実行して結果を表示。
    """
    today = datetime(2024, 6, 1)

    user_id = (
        await asyncio.to_thread(
            get_random_sleep_users,
            limit=1,
            min_records=20,
            start_date=today - pd.DateOffset(months=1),
            end_date=today,
        )
    )[0]

    weekly_result, monthly_result = await asyncio.gather(
        weekly_sleep_pipeline(user_id, today),
        monthly_sleep_pipeline(user_id, today),
    )

    print("=== Weekly Sleep Pipeline Result ===")
    print(weekly_result)
    print("\n=== Monthly Sleep Pipeline Result ===")
    print(monthly_result)


if __name__ == "__main__":
    asyncio.run(_test())
