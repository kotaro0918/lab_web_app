import os
import sys
from datetime import datetime
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from app.utils import SQL_EXECUTION

SLEEP_TABLE = "tu-connectedlife.fitbit.sleep_summary"


def get_sleep_by_user(user_id, start_date, end_date):
    sql_execution = SQL_EXECUTION()

    query = f"""
    SELECT 
        date,
        total_minutes_asleep,
    FROM `{SLEEP_TABLE}`
    WHERE id = '{user_id}' AND date BETWEEN '{start_date.date()}' AND '{end_date.date()}'
    ORDER BY date DESC
    """

    results = sql_execution.run_query(query)
    # 結果をリストに変換
    dates = []
    total_minutes_asleep = []
    sleep_quality = []
    for row in results:
        dates.append(row.date)
        total_minutes_asleep.append(row.total_minutes_asleep)
    return {
        "dates": dates,
        "total_minutes_asleep": total_minutes_asleep,
    }


def get_random_sleep_users(limit=7, min_records=7, start_date=None, end_date=None):
    sql_execution = SQL_EXECUTION()

    date_filter = ""
    if start_date and end_date:
        date_filter = f"AND date BETWEEN '{start_date.date()}' AND '{end_date.date()}'"

    query = f"""
    SELECT id
    FROM `{SLEEP_TABLE}`
    WHERE total_minutes_asleep > 0
    {date_filter}
    GROUP BY id
    HAVING COUNT(*) >= {min_records}
    ORDER BY RAND()
    LIMIT {limit}
    """

    results = sql_execution.run_query(query)
    return [row.id for row in results]


if __name__ == "__main__":
    start_date = datetime(2024, 2, 1)
    end_date = datetime(2024, 6, 1)
    user_id = get_random_sleep_users(
        limit=200, min_records=100, start_date=start_date, end_date=end_date
    )
    print(len(user_id))
    print(user_id)

    df = pd.DataFrame(user_id)
    df.to_csv("data/user_id.csv", index=False)
