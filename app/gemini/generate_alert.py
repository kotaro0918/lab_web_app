import os
import sys
from datetime import datetime
import pandas as pd
from tqdm import tqdm
import asyncio

# ルートパスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# アプリ依存モジュール
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


# --------------------------------------------------------------------------- #
# Gemini 呼び出しをスレッド化して await 可能にするユーティリティ
# --------------------------------------------------------------------------- #
async def _run_in_thread(prompt: str) -> str:
    """
    同期版 gemini_execution.run_prompt をスレッドで実行し、
    非同期タスクとして await できるようにする共通ヘルパー。
    """
    gemini_execution = Gemini_Execution()
    return await asyncio.to_thread(gemini_execution.run_prompt, prompt)


# --------------------------------------------------------------------------- #
# 各種アラート生成 ─ すべて await _run_in_thread(prompt)
# --------------------------------------------------------------------------- #
async def generate_monthly_active_alert(
    this_month_data, this_month_mean, user_profile=None
):
    prompt = (
        MONTHLY_ACTIVE_PROMPT.format(
            this_month_data=this_month_data, this_month_mean=this_month_mean
        )
        + MONTHLY_ACTIVE_INFORMATION
        + user_profile
    )
    return await _run_in_thread(prompt)


async def generate_monthly_step_alert(
    this_month_data, this_month_mean, user_profile=None
):
    prompt = (
        MONTHLY_STEP_PROMPT.format(
            this_month_data=this_month_data, this_month_mean=this_month_mean
        )
        + MONTHLY_STEP_INFORMATION
        + user_profile
    )
    return await _run_in_thread(prompt)


async def generate_weekly_active_alert(
    this_week_data,
    previous_two_week_data,
    this_week_mean,
    previous_two_week_mean,
    user_profile=None,
):
    prompt = (
        WEEKLY_ACTIVE_PROMPT.format(
            this_week_data=this_week_data,
            previous_two_week_data=previous_two_week_data,
            this_week_mean=this_week_mean,
            previous_two_week_mean=previous_two_week_mean,
        )
        + WEEKLY_ACTIVE_INFORMATION
        + user_profile
    )
    return await _run_in_thread(prompt)


async def generate_weekly_step_alert(
    this_week_data,
    previous_two_week_data,
    this_week_mean,
    previous_two_week_mean,
    user_profile=None,
):
    prompt = (
        WEEKLY_STEP_PROMPT.format(
            this_week_data=this_week_data,
            previous_two_week_data=previous_two_week_data,
            this_week_mean=this_week_mean,
            previous_two_week_mean=previous_two_week_mean,
        )
        + WEEKLY_STEP_INFORMATION
        + user_profile
    )
    return await _run_in_thread(prompt)


async def generate_weekly_sleep_alert(
    this_week_data, this_week_mean, user_profile=None
):
    prompt = (
        WEEKLY_SLEEP_PROMPT.format(
            this_week_data=this_week_data, this_week_mean=this_week_mean
        )
        + WEEKLY_SLEEP_INFORMATION
        + user_profile
    )
    return await _run_in_thread(prompt)


async def generate_monthly_sleep_alert(
    this_month_data, this_month_mean, user_profile=None
):
    prompt = (
        MONTHLY_SLEEP_PROMPT.format(
            this_month_data=this_month_data, this_month_mean=this_month_mean
        )
        + MONTHLY_SLEEP_INFORMATION
        + user_profile
    )
    return await _run_in_thread(prompt)


async def generate_weekly_nutrition_alert(
    this_week_data, this_week_protein_ratio, user_profile=None
):
    prompt = (
        NUTRION_PROMPT.format(
            this_week_data=this_week_data,
            this_week_protein_ratio=this_week_protein_ratio,
        )
        + NUTRITION_INFORMATION
        + user_profile
    )
    return await _run_in_thread(prompt)
