# main.py の最上部などに一度だけ入れる
import sys, google, pprint

print("Python →", sys.executable)  # ← venv/python になっているか
print("google.__path__ →", list(google.__path__))  # site-packages だけなら OK
try:
    import google.genai as genai

    print("google-genai", genai.__version__)
except ImportError as e:
    print("ImportError:", e)


# main.py  ────────────────────────────────────────────────────────────────
import streamlit as st
import os
from datetime import datetime
from pathlib import Path
import pandas as pd
import asyncio
import nest_asyncio
import cProfile
import pstats
import io
import plotly.graph_objects as go
import json

# webrtc_audio_player.py
import queue, threading, av, numpy as np
from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase

# ======================  パス & イベントループ初期化  ======================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)
from utils import Gemini_TTS_Execution, GeminiChatExecution
from utils import GeminiTTSStream

tts_executor = Gemini_TTS_Execution()


def ensure_event_loop():
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)


# =========  パイプライン（すべて async 版） & async ヘルパー  ==============
from pipeline.activity_pipeline import (
    weekly_activity_pipeline,
    monthly_activity_pipeline,
)
from pipeline.sleep_pipeline import weekly_sleep_pipeline, monthly_sleep_pipeline
from pipeline.nutrition_pipeline import weekly_nutrition_pipeline
from app.jobs.sleep import get_random_sleep_users  # UI で未使用だが保持

import time
import inspect

try:
    with open("data/user_profile.json", "r", encoding="utf-8") as fp:
        user_records = json.load(fp)
except FileNotFoundError:
    user_records = []


def build_alert_context(
    weekly_act: dict,
    monthly_act: dict,
    weekly_slp: dict,
    monthly_slp: dict,
    weekly_nut: dict,
    monthly_nut: dict | None = None,  # 栄養は月次が無いケースも想定
) -> str:
    """
    週次 / 月次 のアラートをまとめて 1 行文字列にするユーティリティ
    """
    parts: list[str] = []

    # ── 週次 ─────────────────────────────
    if weekly_act:
        if weekly_act.get("weekly_step_alert"):
            parts.append(f"週次 歩数アラート: {weekly_act['weekly_step_alert']}")
        if weekly_act.get("weekly_active_alert"):
            parts.append(f"週次 活動時間アラート: {weekly_act['weekly_active_alert']}")

    if weekly_slp and weekly_slp.get("weekly_sleep_alert"):
        parts.append(f"週次 睡眠時間アラート: {weekly_slp['weekly_sleep_alert']}")

    if weekly_nut and weekly_nut.get("weekly_nutrition_alert"):
        parts.append(f"週次 栄養アラート: {weekly_nut['weekly_nutrition_alert']}")

    # ── 月次 ─────────────────────────────
    if monthly_act:
        if monthly_act.get("monthly_step_alert"):
            parts.append(f"月次 歩数アラート: {monthly_act['monthly_step_alert']}")
        if monthly_act.get("monthly_active_alert"):
            parts.append(
                f"月次 活動時間アラート: {monthly_act['monthly_active_alert']}"
            )

    if monthly_slp and monthly_slp.get("monthly_sleep_alert"):
        parts.append(f"月次 睡眠時間アラート: {monthly_slp['monthly_sleep_alert']}")

    if monthly_nut and monthly_nut.get("monthly_nutrition_alert"):
        parts.append(f"月次 栄養アラート: {monthly_nut['monthly_nutrition_alert']}")

    return " / ".join(parts) if parts else ""


def get_user_profile(user_records, user_id: str):
    match = next(  # │
        (rec for rec in user_records if rec["id"] == user_id),
        None,  # ← target_id → user_id
    )

    if match is None:
        print("ユーザーが見つかりません")
        return None

    profile = {k: match[k] for k in ("age", "gender", "bmi")}  # dict で返す例
    return profile  # 呼び出し元で使うなら返しておく


async def _run_pipeline_with_timing(pipeline_name, pipeline_func, *args):
    """
    非同期パイプラインを計測しつつ実行。
    同期関数が渡された場合は to_thread でオフロード。
    """
    start = time.perf_counter()
    print(f"[計測] {pipeline_name} 開始")

    try:
        if inspect.iscoroutinefunction(pipeline_func):
            result = await pipeline_func(*args)
        else:  # 念のため同期関数も扱える汎用化
            result = await asyncio.to_thread(pipeline_func, *args)
        print(f"[計測] {pipeline_name} 完了 ({time.perf_counter() - start:.3f}s)")
        return result
    except Exception as e:
        print(
            f"[計測] {pipeline_name} 例外 ({time.perf_counter() - start:.3f}s): {e!r}"
        )
        raise


async def fetch_all(user_id: str, today: datetime, user_profile: str = ""):
    overall_start = time.perf_counter()
    print(f"[fetch_all] パイプライン開始 for {user_id}")

    # 各パイプラインの同時実行
    tasks = [
        _run_pipeline_with_timing(
            "weekly_activity", weekly_activity_pipeline, user_id, today, user_profile
        ),
        _run_pipeline_with_timing(
            "weekly_sleep", weekly_sleep_pipeline, user_id, today, user_profile
        ),
        _run_pipeline_with_timing(
            "weekly_nutrition",
            weekly_nutrition_pipeline,
            user_id.replace("@gmail.com", ""),  # nutrition だけ ID 仕様が異なる想定
            today,
            user_profile,
        ),
        _run_pipeline_with_timing(
            "monthly_activity", monthly_activity_pipeline, user_id, today, user_profile
        ),
        _run_pipeline_with_timing(
            "monthly_sleep", monthly_sleep_pipeline, user_id, today, user_profile
        ),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=False)
    print(
        f"[fetch_all] 全パイプライン完了 ({time.perf_counter() - overall_start:.3f}s)"
    )
    return tuple(results)


# ===================  フィードバック & グラフ描画ユーティリティ  =============
FEEDBACK_FILE = "feedback.csv"


def save_feedback(user_id, message_id, rating):
    df = pd.DataFrame(
        [
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "user_id": user_id,
                "message_id": message_id,
                "rating": rating,
            }
        ]
    )
    path = Path(FEEDBACK_FILE)
    df.to_csv(path, mode="a", header=not path.exists(), index=False)


def rated_info(message_id, text, user_id):
    if "ratings" not in st.session_state:
        st.session_state["ratings"] = {}

    # 8:1:1:1 → 本文 / 再生 / 👍 / 👎
    col_msg, col_play, col_like, col_dislike = st.columns([8, 0.5, 0.5, 0.5])

    with col_msg:
        st.markdown(
            f"""
            <div style="padding:1em;background-color:#e1f5fe;border-left:4px solid #29b6f6;border-radius:4px;">
                <span style="font-size:25px;">{text}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ▶ ボタン
    if col_play.button("▶️", key=f"play_{message_id}"):
        with st.spinner("音声を生成中…"):
            wav = tts_executor.run_tts(text)
        st.session_state[f"audio_{message_id}"] = wav  # キャッシュ

    # 再生プレーヤー（自動再生 ON）
    if f"audio_{message_id}" in st.session_state:
        col_play.audio(
            st.session_state[f"audio_{message_id}"],
            format="audio/wav",
            autoplay=True,  # ★ これだけ
        )

    # 👍 / 👎 は既存処理
    disabled = message_id in st.session_state["ratings"]
    if col_like.button("👍", key=f"like_{message_id}", disabled=disabled):
        st.session_state["ratings"][message_id] = 1
        save_feedback(user_id, message_id, 1)
        st.toast("フィードバックありがとうございます！", icon="✅")
    if col_dislike.button("👎", key=f"dislike_{message_id}", disabled=disabled):
        st.session_state["ratings"][message_id] = 0
        save_feedback(user_id, message_id, 0)
        st.toast("フィードバックありがとうございます！", icon="✅")


# ---- 活動量データ表示 ---------------------------------------------------
def display_activity_data(title, activity_data, key_suffix=""):
    if activity_data and activity_data.get("dates"):
        df = pd.DataFrame(
            {
                "Date": pd.to_datetime(activity_data["dates"]),
                "Steps": activity_data.get("steps", []),
                "座位時間": activity_data.get("sedentary_minutes", []),
            }
        )

        for col in ["Steps", "座位時間"]:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(x=df["Date"], y=df[col], mode="lines+markers", name=col)
            )
            fig.update_layout(
                title=f"{title} - {col}",
                title_font_size=24,
                font=dict(size=22),
                xaxis=dict(
                    title="Date", title_font=dict(size=22), tickfont=dict(size=18)
                ),
                yaxis=dict(title=col, title_font=dict(size=22), tickfont=dict(size=18)),
                height=450,
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.write(f"{title}: データがありません。")


# ---- 睡眠データ表示 -----------------------------------------------------
def display_sleep_data(title, sleep_data, key_suffix=""):
    if sleep_data and sleep_data.get("dates"):
        df = pd.DataFrame(
            {
                "Date": pd.to_datetime(sleep_data["dates"]),
                "Total Minutes Asleep": sleep_data.get("total_minutes_asleep", []),
            }
        )

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(x=df["Date"], y=df["Total Minutes Asleep"], mode="lines+markers")
        )
        fig.update_layout(
            title=f"{title} - Total Minutes Asleep",
            title_font_size=24,
            font=dict(size=22),
            xaxis=dict(title="Date", title_font=dict(size=22), tickfont=dict(size=18)),
            yaxis=dict(
                title="Minutes", title_font=dict(size=22), tickfont=dict(size=18)
            ),
            height=450,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write(f"{title}: データがありません。")


# ---- 栄養データ表示 -----------------------------------------------------
def display_nutrition_data(title, nutrition_data, key_suffix=""):
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
        "protein_ratio": "protein_ratio",
    }

    for field, col in field_map.items():
        vals = nutrition_data.get(field, [])
        df[col] = pd.Series(vals, index=dates[: len(vals)])

    for col in df.columns:
        if df[col].notna().any():
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(x=df.index, y=df[col], mode="lines+markers", name=col)
            )
            fig.update_layout(
                title=f"{title} - {col}",
                title_font_size=24,
                font=dict(size=22),
                xaxis=dict(
                    title="Date", title_font=dict(size=22), tickfont=dict(size=18)
                ),
                yaxis=dict(title=col, title_font=dict(size=22), tickfont=dict(size=18)),
                height=450,
            )
            st.plotly_chart(fig, use_container_width=True)


# ============================  Streamlit  ===================================
def main():
    ensure_event_loop()
    nest_asyncio.apply()  # Streamlit 再入ループ許可

    st.set_page_config(layout="wide")
    # 👉 追加：チャット用の状態
    if "show_chat" not in st.session_state:
        st.session_state.show_chat = False  # チャットウィンドウの開閉
    if "messages" not in st.session_state:
        st.session_state.messages = []  # [{"role":"user/assistant","content":...}, ...]
        # 👉 Gemini インスタンスを 1 回だけ生成
    if "chat_exec" not in st.session_state:
        st.session_state.chat_exec = GeminiChatExecution(
            system_prompt="あなたは親切な健康アドバイザーです。"
        )
    if "mic_mode" not in st.session_state:  # ★★★ この行を追加 ★★★
        st.session_state.mic_mode = False  # ★★★ この行を追加 ★★★
    st.title("ユーザー健康データ分析ダッシュボード 📊")
    # 👉 追加：チャット切り替えボタン
    if st.button("💬 チャット", key="toggle_chat"):
        st.session_state.show_chat = not st.session_state.show_chat
    st.write("ボタンを押すと音声チャット画面へ遷移します。")

    if st.button("🗣️ 音声チャットを開く", type="primary"):
        # 相対パスまたはページ名で指定
        st.switch_page("pages/audio_stream.py")
    # ページ名だけで動く場合もあります（表示名が一意なら）:
    user_ids = [
        "ashita03626@gmail.com",  # 栄養不足,運動不足　男性　太り気味
        "ashita14866@gmail.com",  # 栄養不足,運動不足　男性
        "ashita01062@gmail.com",  # 運動不足 女性
    ]
    uid = st.selectbox("ユーザーIDを選択してください:", user_ids)
    today = datetime(2024, 2, 19)
    st.sidebar.info(f"基準日: {today:%Y-%m-%d}")

    if st.button("データを表示"):
        if not uid:
            st.error("ユーザーIDを入力してください。")
            st.stop()

        st.session_state["user_id"] = uid
        loop = asyncio.get_event_loop()

        with st.spinner("パイプライン実行中…"):
            user_profile = get_user_profile(user_records, uid)
            if user_profile is not None:
                user_info = f"""
                以下のユーザープロファイルを考慮して、最適化された健康アドバイスを生成してください。
                ユーザープロファイル:
                ---------------
                (年齢: {user_profile.get('age', '不明')}, 性別: {user_profile.get('gender', '不明')}, BMI: {user_profile.get('bmi', '不明')})"""
                st.session_state["user_info"] = user_info
            else:
                user_info = ""
            try:
                (weekly_act, weekly_slp, weekly_nut, monthly_act, monthly_slp) = (
                    loop.run_until_complete(fetch_all(uid, today, user_info))
                )
            except Exception as e:
                st.error(f"パイプライン実行中にエラーが発生しました: {e}")
                st.stop()

        st.session_state.update(
            {
                "weekly_activity_result": weekly_act,
                "weekly_sleep_result": weekly_slp,
                "weekly_nutrition_result": weekly_nut,
                "monthly_activity_result": monthly_act,
                "monthly_sleep_result": monthly_slp,
            }
        )

    # -----------  結果表示（元 UI そのまま） -------------------------------
    if "weekly_activity_result" in st.session_state:
        uid = st.session_state["user_id"]
        weekly_activity_result = st.session_state["weekly_activity_result"]
        weekly_sleep_result = st.session_state["weekly_sleep_result"]
        weekly_nutrition_result = st.session_state["weekly_nutrition_result"]
        monthly_activity_result = st.session_state["monthly_activity_result"]
        monthly_sleep_result = st.session_state["monthly_sleep_result"]

        st.header(f"ユーザー: {uid} の分析結果")
        tab1, tab2, tab3 = st.tabs(
            ["📅 週次レポート", "🗓️ 月次レポート", "栄養レポート"]
        )

        with tab1:
            st.subheader("活動データ (週次) 🏃‍♀️")
            rated_info(
                "weekly_step_alert",
                f"歩数アラート: {weekly_activity_result.get('weekly_step_alert','N/A')}",
                uid,
            )
            rated_info(
                "weekly_active_alert",
                f"活動時間アラート: {weekly_activity_result.get('weekly_active_alert','N/A')}",
                uid,
            )
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    "今週の平均歩数",
                    f"{weekly_activity_result.get('current_steps_mean',0):.0f} 歩",
                )
                st.metric(
                    "今週の平均座位時間",
                    f"{weekly_activity_result.get('current_sedentary_mean',0):.0f} 分",
                )
                display_activity_data(
                    "今週の活動データ",
                    weekly_activity_result.get("current_activity_data"),
                )
            with col2:
                st.metric(
                    "先週の平均歩数",
                    f"{weekly_activity_result.get('previous_steps_mean',0):.0f} 歩",
                )
                st.metric(
                    "先週の平均座位時間",
                    f"{weekly_activity_result.get('previous_sedentary_mean',0):.0f} 分",
                )
                display_activity_data(
                    "先週の活動データ",
                    weekly_activity_result.get("previous_activity_data"),
                )
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    "今週の平均活動時間",
                    f"{weekly_activity_result.get('current_activity_mean',0):.0f} 分",
                )
            with col2:
                st.metric(
                    "先週の平均活動時間",
                    f"{weekly_activity_result.get('previous_activity_mean',0):.0f} 分",
                )
            st.divider()
            st.subheader("睡眠データ (週次) 😴")
            rated_info(
                "weekly_sleep_alert",
                f"睡眠時間アラート: {weekly_sleep_result.get('weekly_sleep_alert','N/A')}",
                uid,
            )
            st.divider()
            st.metric(
                "今週の平均睡眠時間",
                f"{weekly_sleep_result.get('current_sleep_mean',0):.0f} 分",
            )
            display_sleep_data(
                "今週の睡眠データ", weekly_sleep_result.get("current_sleep_data")
            )

        with tab2:
            st.subheader("活動データ (月次) 🏃‍♂️")
            rated_info(
                "monthly_step_alert",
                f"月次 歩数アラート: {monthly_activity_result.get('monthly_step_alert','N/A')}",
                uid,
            )
            rated_info(
                "monthly_active_alert",
                f"月次 活動時間アラート: {monthly_activity_result.get('monthly_active_alert','N/A')}",
                uid,
            )
            st.divider()
            st.metric(
                "今月の平均歩数",
                f"{monthly_activity_result.get('current_steps_mean',0):.0f} 歩",
            )
            st.metric(
                "今月の平均Sedentary Minutes",
                f"{monthly_activity_result.get('current_activity_mean',0):.0f} 分",
            )
            display_activity_data(
                "今月の活動データ", monthly_activity_result.get("current_activity_data")
            )
            st.divider()
            st.subheader("睡眠データ (月次) 🛌")
            rated_info(
                "monthly_sleep_alert",
                f"月次 睡眠時間アラート: {monthly_sleep_result.get('monthly_sleep_alert','N/A')}",
                uid,
            )
            st.divider()
            st.metric(
                "今月の平均睡眠時間",
                f"{monthly_sleep_result.get('current_sleep_mean',0):.0f} 分",
            )
            display_sleep_data(
                "今月の睡眠データ", monthly_sleep_result.get("current_sleep_data")
            )

        with tab3:
            st.subheader("栄養データ (週次) 🍽️")
            rated_info(
                "weekly_nutrition_alert",
                f"栄養アラート: {weekly_nutrition_result.get('weekly_nutrition_alert','N/A')}",
                uid,
            )
            st.divider()
            current_nutrition_data = weekly_nutrition_result.get(
                "current_nutrition_data", {}
            )

            previous_nutrition_data = weekly_nutrition_result.get(
                "previous_nutrition_data", {}
            )
            current_energy_vals = current_nutrition_data.get("energy", [])
            current_avg_energy = (
                sum(current_energy_vals) / len(current_energy_vals)
                if current_energy_vals
                else 0
            )
            current_protein_ratio = weekly_nutrition_result.get(
                "current_protein_ratio", 0
            )
            current_calories_out = weekly_activity_result.get(
                "current_calories_out_mean", []
            )
            current_protein_mean = weekly_nutrition_result.get(
                "current_protein_mean", 0
            )
            current_protein_ratio_by_activity = (
                current_protein_mean * 4 / current_calories_out
                if current_avg_energy > 0
                else 0
            )

            previous_energy_vals = previous_nutrition_data.get("energy", [])
            previous_avg_energy = (
                sum(previous_energy_vals) / len(previous_energy_vals)
                if previous_energy_vals
                else 0
            )
            previous_protein_ratio = weekly_nutrition_result.get(
                "previous_protein_ratio", 0
            )
            previous_calories_out = weekly_activity_result.get(
                "previous_calories_out_mean", []
            )
            previous_protein_mean = weekly_nutrition_result.get(
                "previous_protein_mean", 0
            )
            previous_protein_ratio_by_activity = (
                previous_protein_mean * 4 / previous_calories_out
                if previous_avg_energy > 0
                else 0
            )
            col1, col2 = st.columns(2)
            with col1:
                st.metric("今週のカロリー", f"{current_avg_energy:.0f} kcal")
                st.metric(
                    "今週のタンパク質比率",
                    f"{current_protein_ratio:.2%}",
                    help="タンパク質カロリー / 総摂取カロリー",
                )
                st.metric(
                    "今週のタンパク質比率（活動ベース）",
                    f"{current_protein_ratio_by_activity:.2%}",
                    help="タンパク質カロリー / 総消費カロリー",
                )
                display_nutrition_data("今週の栄養データ", current_nutrition_data)
            with col2:
                st.metric("今週のカロリー", f"{previous_avg_energy:.0f} kcal")
                st.metric(
                    "先週のタンパク質比率",
                    f"{previous_protein_ratio:.2%}",
                    help="タンパク質カロリー / 総カロリー",
                )
                st.metric(
                    "先週のタンパク質比率（活動ベース）",
                    f"{previous_protein_ratio_by_activity:.2%}",
                    help="タンパク質カロリー / 総消費カロリー",
                )
                display_nutrition_data("先週の栄養データ", previous_nutrition_data)
    else:
        st.info('左上の"データを表示"ボタンを押して、分析を開始してください。')

    # ---------- 1) session_state から安全に取得 ------------------
    weekly_act = st.session_state.get("weekly_activity_result")
    weekly_slp = st.session_state.get("weekly_sleep_result")
    weekly_nut = st.session_state.get("weekly_nutrition_result")
    monthly_act = st.session_state.get("monthly_activity_result")
    monthly_slp = st.session_state.get("monthly_sleep_result")
    monthly_nut = st.session_state.get("monthly_nutrition_result", {})  # 無ければ {}
    user_info = st.session_state.get("user_info", "")

    # ---------- 2) まだデータが無い場合は build&set をスキップ -----
    if weekly_act and monthly_act:  # 他も None でないか確認
        alert_ctx = build_alert_context(
            weekly_act, monthly_act, weekly_slp, monthly_slp, weekly_nut, monthly_nut
        )

        sys_ctx = "\n".join(s for s in [user_info, alert_ctx] if s)
        st.session_state.chat_exec.set_system_prompt(
            "以下の情報をもとに、100文字程度で答えてください" + sys_ctx
        )

    # ==========================  サイドバー：チャット ======================
    if st.session_state.show_chat:
        with st.sidebar:
            st.header("🗣️ AI チャット")

            # 🔊 読み上げトグル
            tts_on = st.toggle("🔊 音声読み上げ", key="tts_on")

            # 🎤 マイク入力トグル
            if st.button("🎤", key="toggle_mic", help="音声入力"):
                st.session_state.mic_mode = not st.session_state.mic_mode

            # ------------------- メッセージ表示 ----------------------------
            chat_area = st.container()
            with chat_area:
                for m in st.session_state.messages:
                    with st.chat_message(m["role"]):
                        st.markdown(m["content"])

            # ------------------ 音声ウィジェット ---------------------------
            audio_file = None
            if st.session_state.mic_mode:
                audio_file = st.audio_input("録音して送信", key="mic_rec")

            # ------------------ 入力欄／送信処理 ---------------------------
            prompt = st.chat_input("メッセージを入力…")
            if prompt or audio_file is not None:
                # ① ユーザ発話テキスト
                if audio_file is not None:
                    wav_bytes = audio_file.read()
                    prompt_text = st.session_state.chat_exec.send_audio(wav_bytes)
                else:
                    prompt_text = prompt

                st.session_state.messages.append(
                    {"role": "user", "content": prompt_text}
                )
                with chat_area.chat_message("user"):
                    st.markdown(prompt_text)

                # ② Gemini 応答
                try:
                    response = st.session_state.chat_exec.send_message(prompt_text)
                except Exception as e:
                    response = f"モデル呼び出しエラー: {e}"

                st.session_state.messages.append(
                    {"role": "assistant", "content": response}
                )
                with chat_area.chat_message("assistant"):
                    st.markdown(response)

                # ③ 読み上げ
                if st.session_state.tts_on:
                    wav = tts_executor.run_tts(response)
                    st.audio(wav, format="audio/wav", autoplay=True)


# ============================  プロファイラ  ===============================
if __name__ == "__main__":
    profiler = cProfile.Profile()
    profiler.enable()
    main()
    profiler.disable()

    s = io.StringIO()
    pstats.Stats(profiler, stream=s).sort_stats("cumulative").print_stats(50)
    print("\n--- cProfile Stats ---\n" + s.getvalue())
