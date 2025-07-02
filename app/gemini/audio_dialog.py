# -*- coding: utf-8 -*-
# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
## Setup

To install the dependencies for this script, run:

brew install portaudio
pip install -U google-genai pyaudio


## API key

Ensure the GOOGLE_API_KEY environment variable is set to the api-key
you obtained from Google AI Studio.

## Run

To run the script:

python Get_started_LiveAPI_NativeAudio.py


Start talking to Gemini
"""

import asyncio
import sys
import traceback
import os
import logging
import pyaudio
from google import genai
from dotenv import load_dotenv

# === Logging configuration ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv("credential/.env")

# Compatibility for Python < 3.11
if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup

    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 2048

pya = pyaudio.PyAudio()

client = genai.Client()  # Requires GOOGLE_API_KEY as env variable

MODEL = "gemini-2.5-flash-preview-native-audio-dialog"
CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": "You are a Japanese helpful assistant and answer in a friendly tone.",
}


class AudioLoop:
    def __init__(self):
        self.audio_in_queue = None
        self.out_queue = None

        self.session = None
        self.audio_stream = None
        self.last_played_frames = []

        self.is_playing = asyncio.Event()  # 🔑 再生中フラグ

    async def listen_audio(self):
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

        kwargs = {"exception_on_overflow": False} if __debug__ else {}

        while True:
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)

            if data in self.last_played_frames:
                continue

            if self.is_playing.is_set():
                logger.debug("🎙️ マイク入力抑制中（再生中）")
                continue

            await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})

    async def send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(audio=msg)

    async def receive_audio(self):
        while True:
            turn = self.session.receive()
            async for response in turn:
                if data := response.data:
                    self.audio_in_queue.put_nowait(data)
                    continue
                if text := response.text:
                    print(text, end="")

            # Clear residual audio queue to handle interruptions properly
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()

    async def play_audio(self):
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )

        # 初期バッファが貯まるまで待機
        while self.audio_in_queue.qsize() < 3:
            await asyncio.sleep(0.01)

        while True:
            if self.audio_in_queue.empty():
                await asyncio.sleep(0.01)
                continue

            self.is_playing.set()
            logger.info("🔊 再生開始")

            while not self.audio_in_queue.empty():
                bytestream = await self.audio_in_queue.get()
                self.last_played_frames.append(bytestream)

                if len(self.last_played_frames) > 200:
                    self.last_played_frames.pop(0)

                await asyncio.to_thread(stream.write, bytestream)

            logger.info("⏱️ 再生終了、0.5秒待機中")
            await asyncio.sleep(0.5)

            self.is_playing.clear()
            logger.info("🎙️ マイク入力再開許可")

    async def run(self):
        try:
            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session

                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=20)

                tg.create_task(self.send_realtime())
                tg.create_task(self.listen_audio())
                tg.create_task(self.receive_audio())
                tg.create_task(self.play_audio())

        except asyncio.CancelledError:
            pass
        except ExceptionGroup as EG:
            if self.audio_stream:
                self.audio_stream.close()
            traceback.print_exception(EG)


if __name__ == "__main__":
    loop = AudioLoop()
    asyncio.run(loop.run())
