"""
Streamlit UI for real‑time voice chat with Gemini Live API
=========================================================
• Click **Start Conversation** to open your mic and begin talking.
• The assistant’s responses will be spoken back and simultaneously shown
  as text below.
• Click **Stop Conversation** to end the live session and release the mic.

> ⚠︎ Run this script locally. Most browsers/hosted services do not allow
> low‑level microphone access from Python.
> Ensure GOOGLE_API_KEY (or GEMINI_API_KEY) is set in credential/.env.

### Key improvements vs. Google sample
1. **No more truncated responses** – audio frames are *never* dropped and
   the playback queue is not cleared mid‑turn.
2. **Back‑pressure aware** – await queue.put() prevents overflow.
3. **Turn‑end sentinel (__END__)** – precise detection of Gemini’s turn
   completion; allows gapless playback without arbitrary sleeps.
4. **Python 3.10 support** via taskgroup / exceptiongroup back‑ports.
"""

from __future__ import annotations
import asyncio
import sys
import threading
from queue import Queue, Empty
from typing import Optional

import numpy as np
import sounddevice as sd
import streamlit as st
from google import genai

# Python 3.10 対応: TaskGroup 互換
if sys.version_info < (3, 11):
    import taskgroup  # pip install taskgroup
    import exceptiongroup  # pip install exceptiongroup

    asyncio.TaskGroup = taskgroup.TaskGroup  # type: ignore[attr-defined]
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup  # type: ignore[attr-defined]

# Constants
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_SIZE = 4096
MODEL = "gemini-2.5-flash-exp-native-audio-thinking-dialog"
CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": "You are a Japanese helpful assistant and answer in a friendly tone.answer in Japanese. and shortly.",
}

client = genai.Client()


# ★★★ 追加: オーディオデバイスのチェック ★★★
def check_audio_devices():
    """利用可能な入出力デバイスを確認し、なければエラーを発生させる"""
    try:
        sd.check_input_settings(samplerate=SEND_SAMPLE_RATE, channels=CHANNELS)
        print("[✅] Default input device is OK.")
    except Exception as e:
        print(f"[❌] No suitable input device found: {e}")
        raise RuntimeError("マイクが見つかりません。接続を確認してください。") from e

    try:
        sd.check_output_settings(samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS)
        print("[✅] Default output device is OK.")
    except Exception as e:
        print(f"[❌] No suitable output device found: {e}")
        raise RuntimeError(
            "スピーカーまたはヘッドホンが見つかりません。接続を確認してください。"
        ) from e


class AudioLoop:
    END_TOKEN: bytes = b"__END__"

    def __init__(self, *, text_queue: Optional[Queue] = None):
        self.text_queue = text_queue
        self.session: Optional[genai.aio.LiveSession] = None
        self.is_playing = asyncio.Event()
        # ★ 修正: out_queueは通常のキューでOK
        self.out_queue: Queue[dict] = Queue(maxsize=1000)
        self.audio_in_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self.last_played_frames: list[bytes] = []
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    # ★★★ 修正点: listen_audioをコールバック方式に変更 ★★★
    def _audio_callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        """sounddeviceから別スレッドで呼び出されるコールバック"""
        if status:
            print(f"[⚠️] Audio callback status: {status}")

        audio_bytes = indata.tobytes()

        # 再生中のエコーや無音を送信しない
        if self.is_playing.is_set() or audio_bytes in self.last_played_frames:
            return

        try:
            # out_queueは通常キューなのでput_nowaitでOK
            self.out_queue.put_nowait(
                {
                    "data": audio_bytes,
                    # ★★★ 修正: APIが要求するMIMEタイプ形式に変更 ★★★
                    "mime_type": f"audio/pcm;rate={SEND_SAMPLE_RATE}",
                }
            )
            print(f"[🎙] Captured and queued audio: {len(audio_bytes)} bytes")
        except asyncio.QueueFull:
            print("[⚠️] out_queue is full, dropping frame.")

    async def listen_audio(self) -> None:
        """マイクキャプチャを開始し、停止イベントを待つ"""
        print("[🎙] Starting microphone capture using callback...")
        loop = asyncio.get_running_loop()

        # InputStreamをコールバックモードで開く
        stream = sd.InputStream(
            samplerate=SEND_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            # loop.call_soon_threadsafeを使ってコールバックを登録
            callback=lambda *args: loop.call_soon_threadsafe(
                self._audio_callback, *args
            ),
        )
        with stream:
            # ストップイベントが発生するまで待機
            await self._stop_event.wait()
        print("[🎙] Microphone capture stopped.")

    async def send_realtime(self) -> None:
        print("[🚀] Starting realtime send loop...")
        loop = asyncio.get_running_loop()
        while not self._stop_event.is_set():
            try:
                # 通常キューから取得するためにrun_in_executorを使用
                msg = await loop.run_in_executor(None, self.out_queue.get, True, 0.1)
                print(f"[🚀] Sending frame: {len(msg['data'])} bytes")
                if self.session:
                    await self.session.send_realtime_input(audio=msg)
            except Empty:
                await asyncio.sleep(0.01)  # キューが空なら少し待つ

    async def receive_audio(self) -> None:
        print("[📥] Starting receive loop...")
        while not self._stop_event.is_set():
            try:
                async for resp in self.session.receive():
                    if self._stop_event.is_set():
                        break

                    # ★★★ 修正: 応答の構造を判別して処理する ★★★
                    if hasattr(resp, "parts"):
                        # マルチパート応答の場合
                        for part in resp.parts:
                            if part.audio and part.audio.data:
                                print(
                                    f"[📥] Received audio frame: {len(part.audio.data)} bytes"
                                )
                                await self.audio_in_queue.put(part.audio.data)
                            if part.text:
                                print(f"[📝] Received text: {part.text}")
                                if self.text_queue:
                                    self.text_queue.put_nowait(part.text)
                    else:
                        # シンプルな応答の場合
                        if resp.data:
                            print(f"[📥] Received audio frame: {len(resp.data)} bytes")
                            await self.audio_in_queue.put(resp.data)
                        if resp.text:
                            print(f"[📝] Received text: {resp.text}")
                            if self.text_queue:
                                self.text_queue.put_nowait(resp.text)

                # ターンが正常に終了した場合
                print("[📥] End of Gemini turn")
                await self.audio_in_queue.put(self.END_TOKEN)

            except asyncio.CancelledError:
                # タスクがキャンセルされた場合は静かに終了
                break
            except Exception as e:
                # 予期せぬエラーをキャッチしてログに出力
                print(f"[❌] FATAL ERROR in receive_audio: {e}")
                # エラーを再送出してTaskGroupに通知
                raise

    async def play_audio(self) -> None:
        print("[🔊] Starting audio playback...")
        try:
            with sd.OutputStream(
                samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16"
            ) as stream:
                while self.audio_in_queue.qsize() < 2 and not self._stop_event.is_set():
                    await asyncio.sleep(0.01)
                while not self._stop_event.is_set():
                    frame = await self.audio_in_queue.get()
                    if frame == self.END_TOKEN:
                        print("[🔊] Received END_TOKEN — turn complete")
                        await asyncio.sleep(0.3)
                        self.is_playing.clear()
                        continue
                    self.is_playing.set()
                    self.last_played_frames.append(frame)
                    if len(self.last_played_frames) > 400:
                        self.last_played_frames.pop(0)
                    print(f"[🔊] Playing audio frame: {len(frame)} bytes")
                    np_frame = np.frombuffer(frame, dtype="int16")
                    stream.write(np_frame)
        # ★★★ 追加: play_audio内のエラーをキャッチしてログに出力 ★★★
        except Exception as e:
            print(f"[❌] FATAL ERROR in play_audio: {e}")
            # エラーを再送出してTaskGroupに通知
            raise

    async def run(self) -> None:
        print("[⚙️] Connecting to Gemini live session...")
        async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
            self.session = session
            print("[✅] Connected to Gemini")
            async with asyncio.TaskGroup() as tg:
                self._tasks.extend(
                    [
                        tg.create_task(self.listen_audio()),
                        tg.create_task(self.send_realtime()),
                        tg.create_task(self.receive_audio()),
                        tg.create_task(self.play_audio()),
                    ]
                )

    def stop(self) -> None:
        print("[🛑] Stopping audio loop")
        self._stop_event.set()
        for t in self._tasks:
            t.cancel()


# ─────────────────────────────────────────────
# Streamlit UI
# ─────────────────────────────────────────────
st.set_page_config(page_title="Gemini Voice Chat", page_icon="🗣️")
st.title("🗣️ Gemini Voice Chat Demo")

if "app_state" not in st.session_state:
    st.session_state.app_state = "stopped"
    st.session_state.loop_thread: Optional[threading.Thread] = None
    st.session_state.audio_loop: Optional[AudioLoop] = None
    st.session_state.text_buffer = ""
    st.session_state.queue: Queue[str] = Queue()

status_placeholder = st.empty()
text_placeholder = st.empty()


def _start_chat() -> None:
    if st.session_state.app_state == "running":
        return

    # ★★★ 追加: チャット開始前にデバイスをチェック ★★★
    try:
        check_audio_devices()
    except RuntimeError as e:
        st.error(str(e))
        return

    loop = AudioLoop(text_queue=st.session_state.queue)

    def _runner() -> None:
        # ★★★ 修正: 詳細なエラーログを出力する ★★★
        try:
            asyncio.run(loop.run())
        except exceptiongroup.ExceptionGroup as eg:
            print("\n--- ERROR: ExceptionGroup caught in runner ---")
            for i, exc in enumerate(eg.exceptions):
                print(
                    f"  Sub-exception {i+1}/{len(eg.exceptions)}: {type(exc).__name__}"
                )
                print(f"  {exc}")
            print("---------------------------------------------\n")
        except Exception as e:
            print(f"\n--- ERROR: Unexpected exception in runner: {e} ---\n")

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    st.session_state.loop_thread = thread
    st.session_state.audio_loop = loop
    st.session_state.app_state = "running"


def _stop_chat() -> None:
    if st.session_state.app_state != "running":
        return
    st.session_state.audio_loop.stop()  # type: ignore
    st.session_state.app_state = "stopped"


with st.sidebar:
    st.header("Controls")
    st.button(
        "▶️ Start Conversation",
        on_click=_start_chat,
        disabled=st.session_state.app_state == "running",
    )
    st.button(
        "⏹️ Stop Conversation",
        on_click=_stop_chat,
        disabled=st.session_state.app_state != "running",
    )
    st.markdown("---")

if st.session_state.app_state == "running":
    status_placeholder.success("Conversation running… Speak into your microphone.")
else:
    status_placeholder.info("Click **Start Conversation** to begin.")

try:
    while True:
        chunk = st.session_state.queue.get_nowait()
        st.session_state.text_buffer += chunk
except Empty:
    pass

text_placeholder.markdown(st.session_state.text_buffer or "_No transcript yet…_")
