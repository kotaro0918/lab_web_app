import streamlit as st
import sys
import os
from datetime import datetime
from pathlib import Path
import pandas as pd
import asyncio
import nest_asyncio
import cProfile  # ★ cProfileモジュールをインポート
import pstats  # ★ pstatsモジュールをインポート (結果整形用)
import io  # ★ pstatsの結果を文字列として扱うためにインポート


# ---------- イベントループ初期化 ----------
def ensure_event_loop():
    """
    ScriptRunner.scriptThread にはデフォルトのイベントループが無いので、
    無ければ生成して set_event_loop した上で nest_asyncio.apply() を呼ぶ。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:  # まだループが無い
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    # nest_asyncio.apply() は ensure_event_loop を呼び出す側、またはmainの最初で行うのが一般的
    # ここではmainの最初で呼び出すことにします。


# ---------- パス設定 ----------
# スクリプトの場所に基づいて適切に設定してください
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# 非同期ヘルパー (async_utils.py が適切な場所にあることを確認してください)
try:
    from async_utils import fetch_all
except ImportError:
    st.error("async_utils.py が見つかりません。パス設定を確認してください。")
    st.stop()  # fetch_allがないと動作しないため停止

# -----------------  フィードバック収集ユーティリティ  -----------------
FEEDBACK_FILE = "feedback.csv"


def save_feedback(user_id: str, message_id: str, rating: int):
    """CSV に追記保存（初回はヘッダ付きで作成）"""
    df = pd.DataFrame(
        [
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "user_id": user_id,
                "message_id": message_id,
                "rating": rating,  # 👍 = 1, 👎 = 0
            }
        ]
    )
    # ファイル存在チェックのPathオブジェクト生成を最適化するなら、
    # アプリ起動時に一度だけ存在確認し、結果をst.session_stateに持つなども考えられる
    feedback_file_path = Path(FEEDBACK_FILE)
    df.to_csv(
        feedback_file_path,
        mode="a",
        header=not feedback_file_path.exists(),
        index=False,
    )


def rated_info(message_id: str, text: str, user_id: str):
    """
    st.info() の横に 👍 / 👎 ボタンを付け、結果を保存
    """
    if "ratings" not in st.session_state:
        st.session_state["ratings"] = {}

    disabled_flag = message_id in st.session_state["ratings"]

    col_msg, col_like, col_dislike = st.columns([8, 1, 1])
    with col_msg:
        st.info(text)

    like_clicked = col_like.button(
        "👍", key=f"like_{message_id}", disabled=disabled_flag, help="参考になった"
    )
    dislike_clicked = col_dislike.button(
        "👎",
        key=f"dislike_{message_id}",
        disabled=disabled_flag,
        help="参考にならなかった",
    )

    if like_clicked or dislike_clicked:
        rating_val = 1 if like_clicked else 0
        st.session_state["ratings"][message_id] = rating_val
        save_feedback(user_id, message_id, rating_val)
        st.toast("フィードバックありがとうございます！", icon="✅")


# -------- ヘルパー関数 --------
def display_activity_data(title, activity_data, key_suffix=""):
    if activity_data and activity_data.get("dates"):
        # DataFrame生成を最適化するなら、元データの日付が既にdatetime型なら変換不要
        df = pd.DataFrame(
            {
                "Date": pd.to_datetime(activity_data["dates"]),
                "Steps": activity_data.get("steps", []),
                "Activity Minutes": activity_data.get("activity_minutes", []),
            }
        ).set_index("Date")
        st.subheader(f"{title} - Steps")
        st.line_chart(df["Steps"])
        st.subheader(f"{title} - Activity Minutes")
        st.line_chart(df["Activity Minutes"])
    else:
        st.write(f"{title}: データがありません。")


def display_sleep_data(title, sleep_data, key_suffix=""):
    if sleep_data and sleep_data.get("dates"):
        df = pd.DataFrame(
            {
                "Date": pd.to_datetime(sleep_data["dates"]),
                "Total Minutes Asleep": sleep_data.get("total_minutes_asleep", []),
            }
        ).set_index("Date")
        st.subheader(f"{title} - Total Minutes Asleep")
        st.line_chart(df["Total Minutes Asleep"])
    else:
        st.write(f"{title}: データがありません。")


def display_nutrition_data(title, nutrition_data, key_suffix=""):
    """栄養データをグラフ表示するヘルパー関数"""
    dates_raw = nutrition_data.get("dates", [])
    if not dates_raw:
        st.write(f"{title}: データがありません。")
        return

    dates = pd.to_datetime(dates_raw)
    df = pd.DataFrame(index=dates)

    field_map = {
        "energy": "energy",
        "carbohydrate": "carbohydrates",
        "protein": "protein",
        "lipid": "lipid",
        "dietary_fiber": "dietary_fiber",
    }

    for field, col_name in field_map.items():
        values = nutrition_data.get(field, [])
        # len(values) が len(dates) と異なる場合の処理も考慮
        if values and len(values) == len(dates):
            df[col_name] = values
        elif values:  # データはあるが長さが異なる場合 (エラーまたは補間処理など検討)
            df[col_name] = pd.Series(
                values,
                index=dates[: len(values)] if len(values) < len(dates) else dates,
            )  # 一例
        else:
            df[col_name] = float("nan")  # または pd.NA

    for col in df.columns:
        if not df[col].isnull().all():  # or df[col].notna().any()
            st.subheader(f"{title} - {col.replace('_', ' ').title()}")
            st.line_chart(df[col].dropna())  # NaNをグラフ描画前に除外


def main():
    """Streamlitアプリケーションのメインロジック"""
    ensure_event_loop()  # イベントループの初期化
    nest_asyncio.apply()  # ループ再入可能化

    # ---------- 画面設定 ----------
    st.set_page_config(layout="wide")
    st.title("ユーザー健康データ分析ダッシュボード 📊")

    # ---------- ユーザー選択 ----------
    user_ids = [
        "ashita14977@gmail.com",
        "ashita02057@gmail.com",
        "ashita15607@gmail.com",
        "ashita03841@gmail.com",
        "ashita02063@gmail.com",
        "ashita02981@gmail.com",
        "ashita15019@gmail.com",
        "ashita03168@gmail.com",
    ]
    user_id_input = st.selectbox(
        "ユーザーIDを選択してください:", user_ids, key="user_id_selector"
    )

    # ---------- 日付設定 ----------
    # この日付はデモ用に固定されています。動的に変更する場合は st.date_input などを検討。
    today = datetime(2024, 4, 7)
    st.sidebar.info(f"基準日: {today.strftime('%Y-%m-%d')}")

    # ================== データ取得ボタン ==================
    if st.button("データを表示", key="show_data_button"):
        if not user_id_input:
            st.error("ユーザーIDを入力してください。")
            st.stop()

        st.session_state["user_id"] = user_id_input

        loop = asyncio.get_event_loop()
        with st.spinner("パイプライン実行中…"):
            try:
                (
                    weekly_activity_result,
                    weekly_sleep_result,
                    weekly_nutrition_result,
                    monthly_activity_result,
                    monthly_sleep_result,
                ) = loop.run_until_complete(fetch_all(user_id_input, today))
            except Exception as e:
                st.error(f"パイプライン実行中にエラーが発生しました: {e}")
                # 詳細なエラー情報をログに出力することも検討
                # import traceback
                # st.error(traceback.format_exc())
                st.stop()

        st.session_state.update(
            {
                "weekly_activity_result": weekly_activity_result,
                "weekly_sleep_result": weekly_sleep_result,
                "weekly_nutrition_result": weekly_nutrition_result,
                "monthly_activity_result": monthly_activity_result,
                "monthly_sleep_result": monthly_sleep_result,
            }
        )
        # セッションステートにデータが入ったことを確認するためにキーをリセットする（再描画を促す場合）
        # st.experimental_rerun() # もし必要なら

    # =====================================================

    # session_state に結果がある場合にのみ UI を描画
    if "weekly_activity_result" in st.session_state:
        uid = st.session_state["user_id"]

        weekly_activity_result = st.session_state["weekly_activity_result"]
        weekly_sleep_result = st.session_state["weekly_sleep_result"]
        weekly_nutrition_result = st.session_state["weekly_nutrition_result"]
        monthly_activity_result = st.session_state["monthly_activity_result"]
        monthly_sleep_result = st.session_state["monthly_sleep_result"]

        st.header(f"ユーザー: {uid} の分析結果")
        tab_titles = ["📅 週次レポート", "🗓️ 月次レポート", "栄養レポート"]
        tab1, tab2, tab3 = st.tabs(tab_titles)

        with tab1:
            st.subheader("活動データ (週次) 🏃‍♀️")
            rated_info(
                "weekly_step_alert",
                f"歩数アラート: {weekly_activity_result.get('weekly_step_alert', 'N/A')}",
                uid,
            )
            rated_info(
                "weekly_active_alert",
                f"活動時間アラート: {weekly_activity_result.get('weekly_active_alert', 'N/A')}",
                uid,
            )
            st.divider()
            current_activity_data = weekly_activity_result.get("current_activity_data")
            previous_activity_data = weekly_activity_result.get(
                "previous_activity_data"
            )
            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    label="今週の平均歩数",
                    value=f"{weekly_activity_result.get('current_steps_mean', 0):.0f} 歩",
                )
                display_activity_data(
                    "今週の活動データ", current_activity_data, "weekly_current_activity"
                )
            with col2:
                st.metric(
                    label="先週の平均歩数",
                    value=f"{weekly_activity_result.get('previous_steps_mean', 0):.0f} 歩",
                )
                display_activity_data(
                    "先週の活動データ",
                    previous_activity_data,
                    "weekly_previous_activity",
                )
            st.divider()
            col1, col2 = st.columns(2)  # レイアウト調整のため再定義
            with col1:
                st.metric(
                    label="今週の平均活動時間",
                    value=f"{weekly_activity_result.get('current_activity_mean', 0):.0f} 分",
                )
            with col2:
                st.metric(
                    label="先週の平均活動時間",
                    value=f"{weekly_activity_result.get('previous_activity_mean', 0):.0f} 分",
                )
            st.divider()
            st.subheader("睡眠データ (週次) 😴")
            rated_info(
                "weekly_sleep_alert",
                f"睡眠時間アラート: {weekly_sleep_result.get('weekly_sleep_alert', 'N/A')}",
                uid,
            )
            st.divider()
            current_sleep_data = weekly_sleep_result.get("current_sleep_data")
            col1, _ = st.columns(2)  # レイアウト調整のため再定義
            with col1:
                st.metric(
                    label="今週の平均睡眠時間",
                    value=f"{weekly_sleep_result.get('current_sleep_mean', 0):.0f} 分",
                )
                display_sleep_data(
                    "今週の睡眠データ", current_sleep_data, "weekly_current_sleep"
                )

        with tab2:
            st.subheader("活動データ (月次) 🏃‍♂️")
            rated_info(
                "monthly_step_alert",
                f"月次 歩数アラート: {monthly_activity_result.get('monthly_step_alert', 'N/A')}",
                uid,
            )
            rated_info(
                "monthly_active_alert",
                f"月次 活動時間アラート: {monthly_activity_result.get('monthly_active_alert', 'N/A')}",
                uid,
            )
            st.divider()
            current_monthly_activity_data = monthly_activity_result.get(
                "current_activity_data"
            )
            st.metric(
                label="今月の平均歩数",
                value=f"{monthly_activity_result.get('current_steps_mean', 0):.0f} 歩",
            )
            st.metric(
                label="今月の平均活動時間",
                value=f"{monthly_activity_result.get('current_activity_mean', 0):.0f} 分",
            )
            display_activity_data(
                "今月の活動データ",
                current_monthly_activity_data,
                "monthly_current_activity",
            )
            st.divider()
            st.subheader("睡眠データ (月次) 🛌")
            rated_info(
                "monthly_sleep_alert",
                f"月次 睡眠時間アラート: {monthly_sleep_result.get('monthly_sleep_alert', 'N/A')}",
                uid,
            )
            st.divider()
            current_monthly_sleep_data = monthly_sleep_result.get("current_sleep_data")
            st.metric(
                label="今月の平均睡眠時間",
                value=f"{monthly_sleep_result.get('current_sleep_mean', 0):.0f} 分",
            )
            display_sleep_data(
                "今月の睡眠データ", current_monthly_sleep_data, "monthly_current_sleep"
            )

        with tab3:
            st.subheader("栄養データ (週次) 🍽️")
            rated_info(
                "weekly_nutrition_alert",
                f"栄養アラート: {weekly_nutrition_result.get('weekly_nutrition_alert', 'N/A')}",
                uid,
            )
            st.divider()
            current_nutrition_data = weekly_nutrition_result.get(
                "current_nutrition_data", {}
            )
            energy_values = current_nutrition_data.get("energy", [])
            average_energy = (
                sum(energy_values) / len(energy_values) if energy_values else 0
            )
            protein_ratio = weekly_nutrition_result.get(
                "protein_ratio", 0
            )  # このキーが結果に含まれているか確認

            col1, _ = st.columns(2)  # レイアウト調整
            with col1:
                st.metric(label="今週のカロリー", value=f"{average_energy:.0f} kcal")
                st.metric(
                    label="今週のタンパク質比率",
                    value=f"{protein_ratio:.2%}",
                    help="タンパク質のカロリー比率",
                )
                st.write(
                    "※ タンパク質のカロリー比率は、タンパク質のカロリーを総カロリーで割った値です。"
                )
                display_nutrition_data(
                    "今週の栄養データ",
                    current_nutrition_data,
                    "weekly_current_nutrition",
                )
    else:
        st.info('左上の"データを表示"ボタンを押して、分析を開始してください。')


if __name__ == "__main__":
    profiler = cProfile.Profile()
    profiler.enable()

    main()  # Streamlitアプリケーションのメイン関数を実行

    profiler.disable()

    # プロファイル結果をコンソールに出力
    s = io.StringIO()
    # 'cumulative' (累積時間順)、'tottime' (正味時間順)、'ncalls' (呼び出し回数順) などでソート可能
    sortby = "cumulative"
    ps = pstats.Stats(profiler, stream=s).sort_stats(sortby)
    ps.print_stats(50)  # 上位50件を表示（件数は適宜調整）

    print("\n--- cProfile Stats (コンソールに出力) ---")
    print(s.getvalue())
    print("------------------------------------------\n")

    # プロファイル結果をファイルに保存 (snakevizなどで可視化する場合)
    # profiler_output_file = "profile_output.prof"
    # profiler.dump_stats(profiler_output_file)
    # print(f"プロファイル結果を {profiler_output_file} に保存しました。")
    # print(f"snakeviz {profiler_output_file} で可視化できます。")

    # 注意: StreamlitのUI上に直接プロファイル結果を表示する場合、
    # main()関数が完了した後にしか表示されません。
    # デバッグ目的であれば、上記コンソール出力やファイル保存がより確実です。
    # if st.sidebar.checkbox("Show Profiler Stats", key="show_profiler_checkbox"):
    # st.sidebar.text_area("Profiler Stats", s.getvalue(), height=600)
