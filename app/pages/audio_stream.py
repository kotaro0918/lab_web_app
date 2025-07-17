"""
Streamlit UI for real‑time voice chat with Gemini Live API (WebRTC version)
===========================================================================
• This version runs entirely in the browser using streamlit-webrtc.
• Click the "START" button in the component below to begin.
• The assistant’s responses will be spoken back and simultaneously shown
  as text.
• Click "STOP" to end the session.

> Ensure GOOGLE_API_KEY (or GEMINI_API_KEY) is set in credential/.env.
"""

from __future__ import annotations
import asyncio
import logging
import threading  # ★ 追加
from queue import Queue, Empty
import time  # ★ 追加

import av
import numpy as np
import streamlit as st
from google import genai
from streamlit_webrtc import AudioProcessorBase, WebRtcMode, webrtc_streamer

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
MODEL = "gemini-2.5-flash-exp-native-audio-thinking-dialog"
CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": "You are a Japanese helpful assistant and answer in a friendly tone.answer in Japanese. and shortly.",
}

try:
    client = genai.Client()
except Exception as e:
    st.error(f"Geminiクライアントの初期化に失敗しました: {e}")
    st.stop()


# --- WebRTC オーディオプロセッサ ---
class GeminiAudioProcessor(AudioProcessorBase):
    # ★ 修正: __init__からtext_queueを削除
    def __init__(self):
        # ★ 修正: text_queueは後から設定されるのでNoneで初期化
        self.text_queue: Queue | None = None
        self.session: genai.aio.LiveSession | None = None
        self.in_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.out_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.is_playing = asyncio.Event()
        self.is_speaking = False

        # ★★★ 修正: イベントループとそれを実行するスレッドをセットアップ ★★★
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.task: asyncio.Task | None = None

    def _run_loop(self):
        """イベントループを別スレッドで実行する"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start(self):
        """非同期タスクを開始する"""
        if self.task is None or self.task.done():
            # スレッドセーフな方法でタスクをスケジュールする
            asyncio.run_coroutine_threadsafe(self._main_loop(), self.loop)
            logger.info("Audio processor task started.")

    def stop(self):
        """非同期タスクを停止する"""
        if self.task:
            self.task.cancel()
            try:
                self.loop.run_until_complete(self.task)
            except asyncio.CancelledError:
                pass
            finally:
                self.task = None
        self.loop.close()
        logger.info("Audio processor task stopped.")

    async def _main_loop(self):
        """Geminiとの通信とデータ中継を行うメインループ"""
        try:
            async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
                self.session = session
                logger.info("Gemini session connected.")
                # 送信タスクと受信タスクを並行実行
                await asyncio.gather(self._sender(), self._receiver())
        except Exception as e:
            logger.error(f"Error in main loop: {e}")

    async def _sender(self):
        """マイクからの音声をGeminiに送信する"""
        while True:
            try:
                chunk = await self.in_queue.get()
                # ★★★ 修正: is_playingがセットされている間は送信しない ★★★
                if self.session and not self.is_playing.is_set():
                    await self.session.send_realtime_input(
                        audio={
                            "data": chunk,
                            "mime_type": f"audio/pcm;rate={SEND_SAMPLE_RATE}",
                        }
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sender error: {e}")

    async def _receiver(self):
        """Geminiからの応答を受信し、再生キューとテキストキューに入れる"""
        while True:
            try:
                if not self.session:
                    await asyncio.sleep(0.1)
                    continue

                async for resp in self.session.receive():
                    # ★★★ 修正: 応答オブジェクトの構造を柔軟に処理 ★★★
                    def process_part(part):
                        if part.audio and part.audio.data:
                            self.out_queue.put_nowait(part.audio.data)
                        if self.text_queue and part.text:
                            self.text_queue.put_nowait(part.text)

                    if hasattr(resp, "parts") and resp.parts:
                        for part in resp.parts:
                            process_part(part)
                    else:
                        # partsがない場合、応答オブジェクト自体をチェック
                        process_part(resp)

                # ターンの終わりにNoneを入れて再生の区切りとする
                self.out_queue.put_nowait(None)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Receiver error: {e}")

    async def recv_queued(self, frames: list[av.AudioFrame]) -> list[av.AudioFrame]:
        """ブラウザからのマイク音声フレームを処理する"""
        # ★★★ 修正: is_playingがセットされている間はマイク入力を無視 ★★★
        if self.is_playing.is_set():
            return []

        # フレームをリサンプリングして16kHz, モノラル, 16bit PCMに変換
        resampler = av.AudioResampler(
            format="s16", layout="mono", rate=SEND_SAMPLE_RATE
        )
        processed_frames = []
        for frame in frames:
            processed_frames.extend(resampler.resample(frame))

        if not processed_frames:
            return []  # ★★★ 修正: Noneではなく空のリストを返す ★★★

        # 変換したフレームをバイトデータに変換して入力キューに入れる
        pcm_s16 = np.hstack([p.to_ndarray() for p in processed_frames])
        await self.in_queue.put(pcm_s16.tobytes())
        # recv_queued は何も返す必要がないので、空のリストを返す
        return []

    async def send_queued(self) -> list[av.AudioFrame]:
        """再生キューの音声データをブラウザに送る"""
        if not self.is_speaking:
            # 最初のフレームが来るまで待つ
            first_frame = await self.out_queue.get()
            if first_frame is None:
                self.is_playing.clear()
                return []  # ★ 修正: Noneではなく空のリストを返す
            self.is_playing.set()
            self.is_speaking = True
            chunk = first_frame
        else:
            try:
                # タイムアウト付きでキューから取得
                chunk = await asyncio.wait_for(self.out_queue.get(), timeout=0.1)
                if chunk is None:
                    self.is_speaking = False
                    self.is_playing.clear()
                    return []  # ★ 修正: Noneではなく空のリストを返す
            except asyncio.TimeoutError:
                return []  # ★ 修正: 無音を返す場合も空のリスト

        # 受け取ったPCMデータをav.AudioFrameに変換して返す
        np_frame = np.frombuffer(chunk, dtype=np.int16)
        new_frame = av.AudioFrame.from_ndarray(
            np_frame.reshape(1, -1), format="s16", layout="mono"
        )
        new_frame.sample_rate = RECEIVE_SAMPLE_RATE
        return [new_frame]  # ★ 修正: フレームをリストに入れて返す

    def on_ended(self):
        """WebRTCセッション終了時に呼ばれる"""
        self.stop()


# --- Streamlit UI ---
st.set_page_config(page_title="Gemini Voice Chat (WebRTC)", page_icon="🌐")
st.title("🌐 Gemini Voice Chat Demo (WebRTC)")
st.markdown("**Start**ボタンを押してマイクの使用を許可し、会話を始めてください。")

# ★★★ 修正: st.session_state の初期化をスクリプトの先頭に移動 ★★★
if "text_buffer" not in st.session_state:
    st.session_state.text_buffer = ""
if "processor_started" not in st.session_state:
    st.session_state.processor_started = False
if "audio_processor" not in st.session_state:
    st.session_state.audio_processor = None
if "webrtc_ctx" not in st.session_state:
    st.session_state.webrtc_ctx = None

# --- メインロジック ---
text_placeholder = st.empty()
audio_placeholder = st.empty()

# ★★★ 修正: UIとロジックを分離 ★★★
col1, col2 = st.columns([1, 1])
with col1:
    start_button = st.button(
        "▶️ Start Conversation", key="start", use_container_width=True
    )
with col2:
    stop_button = st.button("⏹️ Stop Conversation", key="stop", use_container_width=True)

if start_button:
    st.session_state.webrtc_ctx = webrtc_streamer(
        key="gemini-webrtc",
        mode=WebRtcMode.SENDONLY,  # ★★★ 修正: SENDONLYモードに変更
        audio_processor_factory=GeminiAudioProcessor,
        media_stream_constraints={"video": False, "audio": True},
        async_processing=True,
    )
    st.rerun()

if stop_button and st.session_state.webrtc_ctx:
    st.session_state.webrtc_ctx.stop()
    st.session_state.webrtc_ctx = None
    st.session_state.audio_processor = None
    st.session_state.processor_started = False
    st.session_state.text_buffer = ""
    st.rerun()


if st.session_state.webrtc_ctx and st.session_state.webrtc_ctx.state.playing:
    status_placeholder = st.success(
        "会話が実行中です… マイクに向かって話してください。"
    )
    if not st.session_state.processor_started:
        st.session_state.audio_processor = st.session_state.webrtc_ctx.audio_processor
        st.session_state.processor_started = True

    processor = st.session_state.audio_processor
    if processor:
        try:
            # ★★★ 修正: 音声再生ロジック ★★★
            audio_chunk = processor.out_queue.get_nowait()
            if audio_chunk is not None:
                # 再生用の完全な音声データを結合
                if "audio_buffer" not in st.session_state:
                    st.session_state.audio_buffer = b""
                st.session_state.audio_buffer += audio_chunk
            else:
                # Noneが来たら再生してバッファをクリア
                if "audio_buffer" in st.session_state and st.session_state.audio_buffer:
                    audio_placeholder.audio(
                        st.session_state.audio_buffer, sample_rate=RECEIVE_SAMPLE_RATE
                    )
                    st.session_state.audio_buffer = b""  # バッファをクリア
        except Empty:
            pass  # キューが空なら何もしない

        try:
            # ★★★ 修正: テキスト表示ロジック ★★★
            text_chunk = processor.text_queue.get_nowait()
            st.session_state.text_buffer += text_chunk
        except Empty:
            pass

    text_placeholder.markdown(
        st.session_state.text_buffer or "_会話の履歴はここに表示されます…_"
    )
    st.rerun()
else:
    status_placeholder = st.info("「Start Conversation」を押して会話を開始します。")
