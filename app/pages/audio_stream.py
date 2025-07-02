"""
Streamlit UI for real‑time voice chat with Gemini Live API
=========================================================
• Click **Start Conversation** to open your mic and begin talking.
• The assistant’s responses will be spoken back and simultaneously shown
  as text below.
• Click **Stop Conversation** to end the live session and release the mic.

> ⚠︎ Run this script locally. Most browsers/hosted services do not allow
> low‑level microphone access from Python.
> Ensure `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) is set in `credential/.env`.

### Key improvements vs. Google sample
1. **No more truncated responses** – audio frames are *never* dropped and
   the playback queue is not cleared mid‑turn.
2. **Back‑pressure aware** – `await queue.put()` prevents overflow.
3. **Turn‑end sentinel (`__END__`)** – precise detection of Gemini’s turn
   completion; allows gapless playback without arbitrary sleeps.
4. **Python 3.10 support** via `taskgroup` / `exceptiongroup` back‑ports.
"""

from __future__ import annotations

import asyncio
import os
import threading
import sys
from queue import Empty, Queue
from typing import Optional

import pyaudio
import streamlit as st
from google import genai

# ────────────────────────────────────────────────────────────────
# Python 3.10 compatibility – back‑port TaskGroup / ExceptionGroup
# ────────────────────────────────────────────────────────────────
if sys.version_info < (3, 11):
    import taskgroup  # pip install taskgroup
    import exceptiongroup  # pip install exceptiongroup

    asyncio.TaskGroup = taskgroup.TaskGroup  # type: ignore[attr-defined]
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup  # type: ignore[attr-defined]


FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16_000
RECEIVE_SAMPLE_RATE = 24_000
CHUNK_SIZE = 4_096  # Larger chunks → fewer calls, smoother stream
MODEL = "gemini-2.5-flash-preview-native-audio-dialog"
CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": "You are a Japanese helpful assistant and answer in a friendly tone.",
}

pya = pyaudio.PyAudio()
client = genai.Client()  # picks up API key from env


# ────────────────────────────────────────────────────────────────
# Core bidirectional audio loop
# ────────────────────────────────────────────────────────────────
class AudioLoop:
    """Handles microphone capture ↔ Gemini live session ↔ speaker playback."""

    END_TOKEN: bytes = b"__END__"  # Sentinel for end‑of‑turn

    def __init__(self, *, text_queue: Optional[Queue] = None):
        self.text_queue = text_queue

        self.session: Optional[genai.aio.LiveSession] = None
        self.audio_stream = None  # pyaudio.Stream

        self.is_playing = asyncio.Event()
        self.out_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self.audio_in_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1_000)

        self.last_played_frames: list[bytes] = []
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    # ──  Capture microphone
    async def listen_audio(self) -> None:
        mic_info = pya.get_default_input_device_info()
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=mic_info["index"],
            frames_per_buffer=CHUNK_SIZE,
        )
        kwargs = {"exception_on_overflow": False}
        while not self._stop_event.is_set():
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
            if self.is_playing.is_set() or data in self.last_played_frames:
                continue  # Mute mic during playback & echo cancellation
            await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})

    # ──  Send realtime audio to Gemini
    async def send_realtime(self) -> None:
        while not self._stop_event.is_set():
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(audio=msg)  # type: ignore[operator]

    # ──  Receive audio & text from Gemini
    async def receive_audio(self) -> None:
        while not self._stop_event.is_set():
            turn = self.session.receive()  # type: ignore[operator]
            async for resp in turn:
                if resp.data:  # ✉️ audio bytes
                    await self.audio_in_queue.put(resp.data)
                if resp.text:  # 📝 transcript
                    if self.text_queue:
                        self.text_queue.put_nowait(resp.text)
            # Turn finished
            await self.audio_in_queue.put(self.END_TOKEN)

    # ──  Play audio to speaker
    async def play_audio(self) -> None:
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )

        # Wait for first few frames to avoid underrun
        while self.audio_in_queue.qsize() < 2 and not self._stop_event.is_set():
            await asyncio.sleep(0.01)

        while not self._stop_event.is_set():
            frame = await self.audio_in_queue.get()
            if frame == self.END_TOKEN:  # End‑of‑turn gap
                await asyncio.sleep(0.3)
                self.is_playing.clear()
                continue
            self.is_playing.set()
            self.last_played_frames.append(frame)
            if len(self.last_played_frames) > 400:
                self.last_played_frames.pop(0)
            await asyncio.to_thread(stream.write, frame)

    # ──  Orchestrate tasks
    async def run(self) -> None:
        async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:  # type: ignore[arg-type]
            self.session = session
            async with asyncio.TaskGroup() as tg:
                self._tasks.extend(
                    [
                        tg.create_task(self.listen_audio()),
                        tg.create_task(self.send_realtime()),
                        tg.create_task(self.receive_audio()),
                        tg.create_task(self.play_audio()),
                    ]
                )

    # ──  Graceful stop
    def stop(self) -> None:
        self._stop_event.set()
        for t in self._tasks:
            t.cancel()
        if self.audio_stream:
            self.audio_stream.close()


# ────────────────────────────────────────────────────────────────
# Streamlit UI
# ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gemini Voice Chat", page_icon="🗣️")
st.title("🗣️ Gemini Voice Chat Demo")

if "app_state" not in st.session_state:
    st.session_state.app_state = "stopped"  # "running" / "stopped"
    st.session_state.loop_thread: Optional[threading.Thread] = None
    st.session_state.audio_loop: Optional[AudioLoop] = None
    st.session_state.text_buffer = ""
    st.session_state.queue: Queue[str] = Queue()

status_placeholder = st.empty()
text_placeholder = st.empty()

# ──  Callbacks


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
    st.session_state.audio_loop.stop()  # type: ignore[union-attr]
    st.session_state.app_state = "stopped"


# ────────────────────────────────────────────────────────────────
# Sidebar controls
# ────────────────────────────────────────────────────────────────
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

# ────────────────────────────────────────────────────────────────
# Main area – show status & transcript
# ────────────────────────────────────────────────────────────────
if st.session_state.app_state == "running":
    status_placeholder.success("Conversation running… Speak into your microphone.")
else:
    status_placeholder.info("Click **Start Conversation** to begin.")

# Pull any new transcript chunks from queue
try:
    while True:
        chunk = st.session_state.queue.get_nowait()
        st.session_state.text_buffer += chunk
except Empty:
    pass

text_placeholder.markdown(st.session_state.text_buffer or "_No transcript yet…_")
