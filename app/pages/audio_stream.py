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
MODEL = "gemini-2.5-flash-preview-native-audio-dialog"
CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": "You are a Japanese helpful assistant and answer in a friendly tone.",
}

client = genai.Client()


class AudioLoop:
    END_TOKEN: bytes = b"__END__"

    def __init__(self, *, text_queue: Optional[Queue] = None):
        self.text_queue = text_queue
        self.session: Optional[genai.aio.LiveSession] = None
        self.is_playing = asyncio.Event()
        self.audio_in_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1000)
        self.out_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self.last_played_frames: list[bytes] = []
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def listen_audio(self) -> None:
        print("[🎙] Starting microphone capture...")
        with sd.InputStream(
            samplerate=SEND_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        ):
            while not self._stop_event.is_set():
                data = sd.rec(
                    CHUNK_SIZE,
                    samplerate=SEND_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                )
                sd.wait()
                audio_bytes = data.tobytes()
                if self.is_playing.is_set() or audio_bytes in self.last_played_frames:
                    continue
                print(f"[🎙] Captured audio frame: {len(audio_bytes)} bytes")
                await self.out_queue.put(
                    {
                        "data": audio_bytes,
                        "mime_type": "audio/pcm;encoding=linear16;sample_rate_hz=16000",
                    }
                )

    async def send_realtime(self) -> None:
        print("[🚀] Starting realtime send loop...")
        while not self._stop_event.is_set():
            print("[🚀] Waiting for audio frame...")
            msg = await self.out_queue.get()
            print(f"[🚀] Sending frame: {len(msg['data'])} bytes")
            await self.session.send_realtime_input(audio=msg)

    async def receive_audio(self) -> None:
        print("[📥] Starting receive loop...")
        while not self._stop_event.is_set():
            try:
                turn = await asyncio.wait_for(self.session.receive(), timeout=10)
                async for resp in turn:
                    if resp.data:
                        print(f"[📥] Received audio frame: {len(resp.data)} bytes")
                        await self.audio_in_queue.put(resp.data)
                    if resp.text:
                        print(f"[📝] Received text: {resp.text}")
                        if self.text_queue:
                            self.text_queue.put_nowait(resp.text)
                print("[📥] End of Gemini turn")
                await self.audio_in_queue.put(self.END_TOKEN)
            except asyncio.TimeoutError:
                print("[⏰] No response from Gemini within timeout window.")

    async def play_audio(self) -> None:
        print("[🔊] Starting audio playback...")
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
    loop = AudioLoop(text_queue=st.session_state.queue)

    def _runner() -> None:
        asyncio.run(loop.run())

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
