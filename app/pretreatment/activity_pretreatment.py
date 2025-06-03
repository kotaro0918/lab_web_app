import pandas as pd
import os
def create_user_summary(csv_path):
    """
    ユーザーごとの活動サマリーを作成する
    
    Args:
        csv_path (str): 入力CSVファイルのパス
    
    Returns:
        pd.DataFrame: ユーザーごとの集計データ
    """
    # CSVファイルを読み込む
    df = pd.read_csv(csv_path)
    
    # ユーザーごとにstepsとactivity_timeの集計を作成
    summary_df = df.groupby('id').agg({
        'steps': [('steps_list', lambda x: list(x)),
                 ('daily_steps', 'mean')],
        'activity_time': [('activity_minutes_list', lambda x: list(x)),
                         ('daily_activity_minutes', 'mean')]
    }).round(2)
    
    # カラムの階層をフラット化し、カラム名を設定
    summary_df.columns = ['steps_list', 'daily_steps', 'activity_minutes_list', 'daily_activity_minutes']
    
    # インデックスをリセットしてidをカラムにする
    summary_df = summary_df.reset_index()
    
    return summary_df

def merge_weekly_summaries(current_week, previous_week):
    """
    現在週と前週のサマリーをマージする
    
    Args:
        current_week (pd.DataFrame): 現在週のサマリー
        previous_week (pd.DataFrame): 前週のサマリー
    
    Returns:
        pd.DataFrame: マージされたデータフレーム
    """
    # カラム名を変更して区別をつける
    previous_week = previous_week.rename(columns={
        'steps': 'previous_steps',
        'activity_minutes': 'previous_activity_minutes',
        'daily_steps': 'previous_daily_steps',
        'daily_activity_minutes': 'previous_daily_activity_minutes'
    })
    
    # left joinを実行
    merged_df = current_week.merge(
        previous_week,
        on='id',
        how='left'
    )
    
    return merged_df
def step_month_category(daily_steps):
    """
    月間の歩数をカテゴリに分ける
    
    Args:
        df (pd.DataFrame): 入力データフレーム
    
    Returns:
        pd.DataFrame: カテゴリを追加したデータフレーム
    """
    if daily_steps <3000:
        return "1"
    elif daily_steps < 5000:
        return "2"
    elif daily_steps < 8000:
        return "3"
    else:
        return "4"
def step_week_category(daily_steps,previous_daily_steps):
    """
    週間の歩数をカテゴリに分ける
    
    Args:
        df (pd.DataFrame): 入力データフレーム
    
    Returns:
        pd.DataFrame: カテゴリを追加したデータフレーム
    """
    if daily_steps < 8000 and daily_steps< previous_daily_steps*1.1:
        return "5"
    elif daily_steps < 8000 and daily_steps>= previous_daily_steps*1.1:
        return "6"
    elif daily_steps >= 8000:
        return "7"
def active_month_category(daily_active_minutes):
    """
    月間の歩数をカテゴリに分ける
    
    Args:
        df (pd.DataFrame): 入力データフレーム
    
    Returns:
        pd.DataFrame: カテゴリを追加したデータフレーム
    """
    if daily_active_minutes <45:
        return "1"
    elif daily_active_minutes < 90:
        return "2"
    elif daily_active_minutes < 150:
        return "3"
    else:
        return "4"
def active_week_category(daily_active_minutes,previous_daily_active_minutes):
    """
    週間の歩数をカテゴリに分ける
    
    Args:
        df (pd.DataFrame): 入力データフレーム
    
    Returns:
        pd.DataFrame: カテゴリを追加したデータフレーム
    """
    if daily_active_minutes < 150 and daily_active_minutes< previous_daily_active_minutes*1.1:
        return "5"
    elif daily_active_minutes < 150 and daily_active_minutes>= previous_daily_active_minutes*1.1:
        return "6"
    elif daily_active_minutes >= 150:
        return "7"
def apply_categories(monthly_df, merged_weekly_df):
    """
    月間・週間のカテゴリを適用する
    
    Args:
        monthly_df (pd.DataFrame): 月間サマリー
        merged_weekly_df (pd.DataFrame): マージ済みの週間サマリー
    
    Returns:
        tuple: (月間カテゴリ付きDF, 週間カテゴリ付きDF)
    """
    # 月間カテゴリの適用
    monthly_df['step_month_category'] = monthly_df['daily_steps'].apply(step_month_category)
    monthly_df['active_month_category'] = monthly_df['daily_activity_minutes'].apply(active_month_category)
    # 週間カテゴリの適用
    merged_weekly_df['step_week_category'] = merged_weekly_df.apply(
        lambda row: step_week_category(row['daily_steps'], row['previous_daily_steps']), 
        axis=1
    )
    merged_weekly_df['active_week_category'] = merged_weekly_df.apply(
        lambda row: active_week_category(row['daily_activity_minutes'], row['previous_daily_activity_minutes']), 
        axis=1
    )
    
    return monthly_df, merged_weekly_df
def calculate_missing_days(datas, number_of_days = 7):
    """
    データフレームの欠損日数を計算する
    
    Args:
        df (pd.DataFrame): 入力データフレーム
        start_date (str): 開始日
        end_date (str): 終了日
    
    Returns:
        int: 欠損日数
    """
    missing_days = number_of_days -len(datas)
    return missing_days
if __name__ == "__main__":
    # データパスの設定
    monthly_data_path = "results/raw/monthly_activity_summary_filtered_2024-04-01_2024-04-30.csv"
    weekly_data_path = "results/raw/weekly_activity_summary_filtered_2024-04-08_2024-04-15.csv"
    previous_weekly_data_path = "results/raw/weekly_activity_summary_filtered_2024-04-01_2024-04-08.csv"
    
    # サマリーの作成
    monthly_summary = create_user_summary(monthly_data_path)
    weekly_summary = create_user_summary(weekly_data_path)
    previous_weekly_summary = create_user_summary(previous_weekly_data_path)
    
    # 週間データのマージ
    merged_weekly = merge_weekly_summaries(weekly_summary, previous_weekly_summary)
    
    # カテゴリの適用
    monthly_with_category, weekly_with_category = apply_categories(monthly_summary, merged_weekly)
    
    # 結果を保存するディレクトリの作成
    os.makedirs("results/processed", exist_ok=True)
    
    # 結果の保存
    monthly_with_category.to_csv("results/processed/monthly_summary_with_category.csv", index=False)
    weekly_with_category.to_csv("results/processed/weekly_comparison_with_category.csv", index=False)
    
    # 結果の確認
    print("\n月間サマリー（カテゴリ付き）の例:")
    print(monthly_with_category[['id', 'daily_steps', 'step_month_category']].head())
    
    print("\n週間比較サマリー（カテゴリ付き）の例:")
    print(weekly_with_category[['id', 'daily_steps', 'previous_daily_steps', 'step_week_category']].head())
    
    # カテゴリごとのユーザー数を表示
    print("\n月間カテゴリの分布:")
    print(monthly_with_category['step_month_category'].value_counts().sort_index())
    print("\n月間アクティブカテゴリの分布:")
    print(monthly_with_category['active_month_category'].value_counts().sort_index())
    
    print("\n週間カテゴリの分布:")
    print(weekly_with_category['step_week_category'].value_counts().sort_index())
    print("\n週間アクティブカテゴリの分布:")
    print(weekly_with_category['active_week_category'].value_counts().sort_index())