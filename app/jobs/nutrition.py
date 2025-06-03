import os
import sys
from datetime import datetime
import pandas as pd
from google.cloud import bigquery

# --------------------------------------------------
# 自前ユーティリティ
# --------------------------------------------------
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from app.utils import SQL_EXECUTION

NUTRITION_TABLE = "tu-connectedlife.fitbit.asuken_summary"


def get_nutrition_by_user(user_id, start_date, end_date):
    sql_execution = SQL_EXECUTION()

    query = f"""
    SELECT 
        record_date,
        meal_type,
        manual_input_time,
        created_date,
        created_time,
        energy,
        water,
        protein,
        lipid,
        carbohydrate,
        cholesterol,
        dietary_fiber
    FROM `{NUTRITION_TABLE}`
    WHERE login_id = '{user_id}' AND record_date BETWEEN '{start_date.date()}' AND '{end_date.date()}'
    ORDER BY record_date DESC, created_time DESC -- 日付内でcreated_timeも考慮して順序を安定させる
    """

    results = sql_execution.run_query(query)

    daily_nutrition_summary = {}

    for row in results:
        date_key = row.record_date
        if date_key not in daily_nutrition_summary:
            daily_nutrition_summary[date_key] = {
                "meal_type": row.meal_type,
                "manual_input_time": row.manual_input_time,
                "created_date": row.created_date,
                "created_time": row.created_time,
                "energy": 0,
                "water": 0,
                "protein": 0,
                "lipid": 0,
                "carbohydrate": 0,
                "cholesterol": 0,
                "dietary_fiber": 0,
            }

        # 栄養素の値を加算 (Noneの場合は0として扱う)
        daily_nutrition_summary[date_key]["energy"] += (
            row.energy if row.energy is not None else 0
        )
        daily_nutrition_summary[date_key]["water"] += (
            row.water if row.water is not None else 0
        )
        daily_nutrition_summary[date_key]["protein"] += (
            row.protein if row.protein is not None else 0
        )
        daily_nutrition_summary[date_key]["lipid"] += (
            row.lipid if row.lipid is not None else 0
        )
        daily_nutrition_summary[date_key]["carbohydrate"] += (
            row.carbohydrate if row.carbohydrate is not None else 0
        )
        daily_nutrition_summary[date_key]["cholesterol"] += (
            row.cholesterol if row.cholesterol is not None else 0
        )
        daily_nutrition_summary[date_key]["dietary_fiber"] += (
            row.dietary_fiber if row.dietary_fiber is not None else 0
        )

    # 結果をリスト形式に変換 (日付の降順を維持)
    sorted_dates_keys = sorted(daily_nutrition_summary.keys(), reverse=True)

    dates = []
    meal_types = []
    manual_input_times = []
    created_dates = []
    created_times = []
    energy = []
    water = []
    protein = []
    lipid = []
    carbohydrate = []
    cholesterol = []
    dietary_fiber = []

    for date_key in sorted_dates_keys:
        summary = daily_nutrition_summary[date_key]
        dates.append(date_key)  # record_date
        meal_types.append(summary["meal_type"])
        manual_input_times.append(summary["manual_input_time"])
        created_dates.append(summary["created_date"])
        created_times.append(summary["created_time"])
        energy.append(summary["energy"])
        water.append(summary["water"])
        protein.append(summary["protein"])
        lipid.append(summary["lipid"])
        carbohydrate.append(summary["carbohydrate"])
        cholesterol.append(summary["cholesterol"])
        dietary_fiber.append(summary["dietary_fiber"])

    return {
        "dates": dates,
        "meal_types": meal_types,
        "manual_input_times": manual_input_times,
        "created_dates": created_dates,
        "created_times": created_times,
        "energy": energy,
        "water": water,
        "protein": protein,
        "lipid": lipid,
        "carbohydrate": carbohydrate,
        "cholesterol": cholesterol,
        "dietary_fiber": dietary_fiber,
    }


if __name__ == "__main__":
    start_date = datetime(2024, 6, 1)
    end_date = datetime(2024, 6, 7)
    user_id = "ashita14977"  # 適切なユーザーIDを指定してください
    nutrition_data = get_nutrition_by_user(user_id, start_date, end_date)
    print(nutrition_data)
