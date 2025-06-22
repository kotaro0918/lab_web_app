import os
import sys
from datetime import datetime
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from app.utils import SQL_EXECUTION

ACTIVITY_TABLE = "tu-connectedlife.fitbit.activity_summary"


def get_activity_by_user(user_id, start_date, end_date):
    sql_execution = SQL_EXECUTION()

    query = f"""
    SELECT 
        date,
        steps,
        sedentary_minutes,
        calories_out,
        (fairly_active_minutes + very_active_minutes * 2) as activity_time
    FROM `{ACTIVITY_TABLE}`
    WHERE id = '{user_id}' AND date BETWEEN '{start_date.date()}' AND '{end_date.date()}'
    ORDER BY date DESC
    """

    results = sql_execution.run_query(query)
    # 結果をリストに変換
    dates = []
    steps = []
    activity_minutes = []
    sedentary_minutes = []
    calorys_out = []
    for row in results:
        dates.append(row.date)
        steps.append(row.steps)
        activity_minutes.append(row.activity_time)
        sedentary_minutes.append(row.sedentary_minutes)
        calorys_out.append(row.calories_out)
    return {
        "dates": dates,
        "steps": steps,
        "activity_minutes": activity_minutes,
        "sedentary_minutes": sedentary_minutes,
        "calories_out": calorys_out,
    }


def get_random_activity_users(limit=7, min_records=7, start_date=None, end_date=None):
    sql_execution = SQL_EXECUTION()

    date_filter = ""
    if start_date and end_date:
        date_filter = f"AND date BETWEEN '{start_date.date()}' AND '{end_date.date()}'"

    query = f"""
    SELECT id
    FROM `{ACTIVITY_TABLE}`
    WHERE steps > 0 AND (fairly_active_minutes + very_active_minutes * 2) > 0
    {date_filter}
    GROUP BY id
    HAVING COUNT(*) >= {min_records}
    ORDER BY RAND()
    LIMIT {limit}
    """

    results = sql_execution.run_query(query)
    return [row.id for row in results]


if __name__ == "__main__":
    start_date = datetime(2024, 6, 1)
    end_date = datetime(2024, 6, 7)
    user_id = get_random_activity_users(7, 4, start_date, end_date)
    print(user_id)
    # activity_data = get_activity_by_user(user_id[0], start_date, end_date)
