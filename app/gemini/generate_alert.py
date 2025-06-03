import os
import sys
from datetime import datetime
import pandas as pd
from tqdm import tqdm
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from app.utils import Gemini_Execution, SQL_EXECUTION
from app.gemini.prompt import (
    MONTHLY_ACTIVE_PROMPT,
    MONTHLY_STEP_PROMPT,
    WEEKLY_ACTIVE_PROMPT,
    WEEKLY_STEP_PROMPT,
    MONTHLY_ACTIVE_INFORMATION,
    MONTHLY_STEP_INFORMATION,
    WEEKLY_ACTIVE_INFORMATION,
    WEEKLY_STEP_INFORMATION,
    WEEKLY_SLEEP_PROMPT,
    WEEKLY_SLEEP_INFORMATION,
    MONTHLY_SLEEP_PROMPT,
    MONTHLY_SLEEP_INFORMATION,
    NUTRION_PROMPT,
    NUTRITION_INFORMATION,
)


def generate_monthly_active_alert(this_month_data, this_month_mean):
    """
    Generate monthly activity alert using Gemini API.
    Args:
        this_month_data (str): Monthly activity data.
    Returns:
        str: Generated alert.
    """
    prompt = MONTHLY_ACTIVE_PROMPT.format(
        this_month_data=this_month_data, this_month_mean=this_month_mean
    )
    prompt += MONTHLY_ACTIVE_INFORMATION
    gemini_execution = Gemini_Execution()
    return gemini_execution.run_prompt(prompt)


def generate_monthly_step_alert(this_month_data, this_month_mean):
    """
    Generate monthly step alert using Gemini API.
    Args:
        this_month_data (str): Monthly step data.
    Returns:
        str: Generated alert.
    """
    prompt = MONTHLY_STEP_PROMPT.format(
        this_month_data=this_month_data, this_month_mean=this_month_mean
    )
    prompt += MONTHLY_STEP_INFORMATION
    gemini_execution = Gemini_Execution()
    return gemini_execution.run_prompt(prompt)


def generate_weekly_active_alert(
    this_week_data, previous_two_week_data, this_week_mean, previous_two_week_mean
):
    """
    Generate weekly activity alert using Gemini API.
    Args:
        this_week_data (str): This week's activity data.
        previous_two_week_data (str): Previous two weeks' activity data.
    Returns:
        str: Generated alert.
    """
    prompt = WEEKLY_ACTIVE_PROMPT.format(
        this_week_data=this_week_data,
        previous_two_week_data=previous_two_week_data,
        this_week_mean=this_week_mean,
        previous_two_week_mean=previous_two_week_mean,
    )
    prompt += WEEKLY_ACTIVE_INFORMATION
    gemini_execution = Gemini_Execution()
    return gemini_execution.run_prompt(prompt)


def generate_weekly_step_alert(
    this_week_data, previous_two_week_data, this_week_mean, previous_two_week_mean
):
    """
    Generate weekly step alert using Gemini API.
    Args:
        this_week_data (str): This week's step data.
        previous_two_week_data (str): Previous two weeks' step data.
    Returns:
        str: Generated alert.
    """
    prompt = WEEKLY_STEP_PROMPT.format(
        this_week_data=this_week_data,
        previous_two_week_data=previous_two_week_data,
        this_week_mean=this_week_mean,
        previous_two_week_mean=previous_two_week_mean,
    )
    prompt += WEEKLY_STEP_INFORMATION
    gemini_execution = Gemini_Execution()
    return gemini_execution.run_prompt(prompt)


def generate_weekly_sleep_alert(this_week_data, this_week_mean):
    """
    Generate weekly sleep alert using Gemini API.
    Args:
        this_week_data (str): This week's sleep data.
    Returns:
        str: Generated alert.
    """
    prompt = WEEKLY_SLEEP_PROMPT.format(
        this_week_data=this_week_data, this_week_mean=this_week_mean
    )
    prompt += WEEKLY_SLEEP_INFORMATION
    gemini_execution = Gemini_Execution()
    return gemini_execution.run_prompt(prompt)


def generate_monthly_sleep_alert(this_month_data, this_month_mean):
    """
    Generate monthly sleep alert using Gemini API.
    Args:
        this_month_data (str): Monthly sleep data.
    Returns:
        str: Generated alert.
    """
    prompt = MONTHLY_SLEEP_PROMPT.format(
        this_month_data=this_month_data, this_month_mean=this_month_mean
    )
    prompt += MONTHLY_SLEEP_INFORMATION
    gemini_execution = Gemini_Execution()
    return gemini_execution.run_prompt(prompt)


if __name__ == "__main__":
    tqdm.pandas()
    monthly_active_data = "results/processed/monthly_summary_with_category.csv"
    weekly_active_data_path = "results/processed/weekly_comparison_with_category.csv"
    monthly_prompt = """以下のデータは高齢者一人のの1ヶ月の運動時間のデータを表したものです。

    今月のデータ: {this_month_data}
    健康状態を改善するためにアドバイスを出力してください。

    字数は100字以内にして要約してください。"""
    weekly_prompt = """以下のデータは高齢者一人のの1週間の運動時間のデータを表したものです。

    2週間前のデータ: {previous_two_week_data}
    今週のデータ: {this_week_data}
    健康状態を改善するためにアドバイスを出力してください。

    字数は100字以内にして要約してください。"""
    monthly_insert_information = """
    以下の方針に沿って、アドバイスを行なってください
    系列	条件	内容
    1	daily active minutes<45	運動時間上昇を促す
    2	45 ≤daily active minute<90	運動時間上昇を促す
    3	90 ≤daily active minute<150	運動時間上昇を促す
    4	150 ≤daily active minute	達成のお祝いと維持を促す
    """
    weekly_insert_information = """
    以下の方針に沿って、アドバイスを行なってください
    系列	条件	内容
    5	daily active minute <150 and count increased by <10% compared to prior week	運動時間上昇を促す
    6	daily active minute<150,step count increased by ≥10% compared to prior week	達成のお祝いと維持を促す
    7	150≤daily steps	達成のお祝いと維持を促す
    """
    month_df = pd.read_csv(monthly_active_data)
    month_df = month_df[
        [
            "id",
            "activity_minutes_list",
            "active_month_category",
            "daily_activity_minutes",
        ]
    ]
    week_df = pd.read_csv(weekly_active_data_path)
    week_df = week_df[
        [
            "id",
            "activity_minutes_list_x",
            "activity_minutes_list_y",
            "previous_daily_activity_minutes",
            "daily_activity_minutes",
            "active_week_category",
        ]
    ]
    week_df = week_df[
        week_df["activity_minutes_list_x"].notna()
        & week_df["activity_minutes_list_y"].notna()
    ]

    # データの確認
    print(f"\n有効なデータ数: {len(week_df)}")
    print("\n最初の行のデータ:")
    print(week_df.head(1))
    gemini_execution = Gemini_Execution()
    # 月間データの処理
    week_df["activity_alert"] = week_df.progress_apply(
        lambda row: gemini_execution.run_prompt(
            weekly_prompt.format(
                this_week_data=row["activity_minutes_list_x"],
                previous_two_week_data=row["activity_minutes_list_y"],
            )
        ),
        axis=1,
    )
    week_df["activity_alert_v2"] = week_df.progress_apply(
        lambda row: gemini_execution.run_prompt(
            weekly_prompt.format(
                this_week_data=row["activity_minutes_list_x"],
                previous_two_week_data=row["activity_minutes_list_y"],
            )
            + weekly_insert_information
        ),
        axis=1,
    )

    week_df.to_csv("results/generated/week_alert.csv", index=False)


def generate_weekly_nutrition_alert(this_week_data, this_week_protein_ratio):
    """
    Generate weekly nutrition alert using Gemini API.
    Args:
        this_week_data (str): This week's nutrition data.
    Returns:
        str: Generated alert.
    """
    prompt = NUTRION_PROMPT.format(
        this_week_data=this_week_data, this_week_protein_ratio=this_week_protein_ratio
    )
    prompt += NUTRITION_INFORMATION
    gemini_execution = Gemini_Execution()
    return gemini_execution.run_prompt(prompt)
