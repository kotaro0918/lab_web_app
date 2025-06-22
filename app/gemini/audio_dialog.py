# live_audio_chat.py  -- Gemini Live API × Streamlit-WebRTC 〈安定動作品＋debug〉
# ──────────────────────────────────────────────────────────────────────────
# - Mic 48 kHz/Opus → 16 kHz PCM で Gemini Live API に送信
# - 0.5 s 無音で audio_stream_end を送信（ターン終了）
# - 60 s 無操作で WebSocket を自動切断
# - Mic / Player が生成された瞬間・recv() 呼び出し回数をロギング
# - デバッグパネルに WebRTC state と Processor インスタンス ID を表示
# - 依存: streamlit, streamlit-webrtc (≥0.50), google-generativeai, av, numpy,
#        pyaudio, python-dotenv

import os, asyncio, threading, queue, time, logging, pathlib
import numpy as np
import av
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types
from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase

# ────────── logging ──────────────────────────────────────────────────────
LOG_FILE = pathlib.Path("gemini_live.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE, mode="w")],
)
logger = logging.getLogger("gemini-live")
logging.getLogger("google_genai._api_client").setLevel(logging.ERROR)  # warning 抑制

# ────────── API キー ────────────────────────────────────────────────────
load_dotenv("credential/.env")  # 無ければスキップ
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GOOGLE_API_KEY または GEMINI_API_KEY を設定してください")

# ────────── Gemini Live 設定 ────────────────────────────────────────────
MODEL = "models/gemini-2.5-flash-preview-native-audio-dialog"
client = genai.Client(api_key=API_KEY, http_options={"api_version": "v1beta"})

CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
        )
    ),
)

SEND_SR, RECV_SR = 16_000, 24_000
mic_q: queue.Queue[bytes] = queue.Queue(maxsize=400)
spk_q: queue.Queue[bytes] = queue.Queue(maxsize=400)


# ────────── utils ───────────────────────────────────────────────────────
def downsample_48k_to_16k(pcm48: bytes) -> bytes:
    data = np.frombuffer(pcm48, np.int16)
    return data[::3].tobytes()


def rms_db(pcm16: bytes) -> float:
    if not pcm16:
        return -120.0
    sig = np.frombuffer(pcm16, np.int16).astype(np.float32)
    rms = np.sqrt(np.mean(sig**2))
    return 20 * np.log10(rms / 32768.0 + 1e-9)


# ────────── Mic → Gemini ────────────────────────────────────────────────
class MicSender(AudioProcessorBase):
    silence = 0

    def __init__(self):
        super().__init__()
        logger.info(f"★★ MicSender constructed id={id(self)}")

    # async_processing=True では “frames” が list で渡る
    def recv(self, frames):
        if not isinstance(frames, list):
            frames = [frames]

        self.__dict__.setdefault("cnt", 0)
        self.__dict__["cnt"] += len(frames)

        try:
            for f in frames:
                pcm48 = f.to_ndarray().tobytes()
                pcm16 = downsample_48k_to_16k(pcm48)
                mic_q.put_nowait(pcm16)

            lvl = rms_db(pcm16)  # 最後のフレームでレベル算出
            MicSender.silence = 0 if lvl > -50 else MicSender.silence + 1
            logger.info(
                "▲ Mic  %5.1f dB  (%4d B, q=%d, id=%s, n=%d)",
                lvl,
                len(pcm16),
                mic_q.qsize(),
                id(self),
                self.__dict__["cnt"],
            )
        except queue.Full:
            logger.warning("Mic queue FULL")
        except Exception:
            logger.exception("MicSender error")
        return frames  # プレビューにそのまま返却


# ────────── Gemini → Speaker ────────────────────────────────────────────
class Player(AudioProcessorBase):
    def __init__(self):
        super().__init__()
        logger.info(f"★★ Player constructed id={id(self)}")

    def recv(self, frames):
        if spk_q.empty():
            return None

        self.__dict__.setdefault("cnt", 0)
        self.__dict__["cnt"] += 1

        try:
            pcm24 = spk_q.get_nowait()
            logger.info(
                "▶ Play %4d B  (q=%d, id=%s, n=%d)",
                len(pcm24),
                spk_q.qsize(),
                id(self),
                self.__dict__["cnt"],
            )

            samples = np.frombuffer(pcm24, np.int16)
            frame = av.AudioFrame.from_ndarray(
                samples.reshape(-1, 1), format="s16", layout="mono"
            )
            frame.sample_rate = RECV_SR
            return frame
        except Exception:
            logger.exception("Player error")
            return None


# ────────── Gemini セッション ──────────────────────────────────────────
IDLE_TIMEOUT = 60  # s


async def live_session(stop_evt: asyncio.Event):
    async with client.aio.live.connect(model=MODEL, config=CONFIG) as sess:
        logger.info("Gemini session opened")
        last_act = time.monotonic()

        async def sender():
            nonlocal last_act
            while not stop_evt.is_set():
                pcm16 = await asyncio.to_thread(mic_q.get)
                last_act = time.monotonic()

                await sess.send_realtime_input(
                    audio=types.Blob(data=pcm16, mime_type="audio/pcm;rate=16000")
                )
                logger.info("↑ Sent %4d B", len(pcm16))

                # 無音でターンを閉じる
                if MicSender.silence >= 20 and time.monotonic() - last_act > 0.5:
                    await sess.send_realtime_input(audio_stream_end=True)
                    logger.info("↑ Sent audio_stream_end")
                    MicSender.silence = 0

        async def receiver():
            nonlocal last_act
            while not stop_evt.is_set():
                turn = sess.receive()
                async for resp in turn:
                    last_act = time.monotonic()
                    if resp.data:
                        spk_q.put_nowait(resp.data)
                        logger.info("↓ Recv %4d B", len(resp.data))
                    if resp.text:
                        logger.info("↓ Text %s", resp.text.strip())

        async def watchdog():
            while not stop_evt.is_set():
                await asyncio.sleep(5)
                if time.monotonic() - last_act > IDLE_TIMEOUT:
                    logger.info("Idle %ds → close", IDLE_TIMEOUT)
                    stop_evt.set()

        await asyncio.gather(sender(), receiver(), watchdog())
    logger.info("Gemini session closed")


def start_live() -> asyncio.Event:
    stop_evt = asyncio.Event()
    loop = asyncio.new_event_loop()
    threading.Thread(
        target=loop.run_until_complete,
        args=(live_session(stop_evt),),
        daemon=True,
    ).start()
    return stop_evt


# ────────── Streamlit UI ────────────────────────────────────────────────
st.set_page_config(layout="wide", page_title="Gemini Live Chat")

status = st.empty()
status.success("🟡 接続待ち")

col_mic, col_spk = st.columns(2)

with col_mic:
    st.caption("🎤 Mic")
    ctx_mic = webrtc_streamer(
        key="mic",
        mode=WebRtcMode.SENDRECV,
        audio_processor_factory=MicSender,
        async_processing=True,  # ★ 非同期モード
        media_stream_constraints={"audio": True, "video": False},
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
        desired_playing_state=st.session_state.get("live_on", False),
        audio_html_attrs={"controls": False},
    )

with col_spk:
    st.caption("🔊 Speaker")
    ctx_spk = webrtc_streamer(
        key="spk",
        mode=WebRtcMode.RECVONLY,
        audio_processor_factory=Player,
        async_processing=True,
        audio_receiver_size=256,
        media_stream_constraints={"audio": True, "video": False},
        desired_playing_state=st.session_state.get("live_on", False),
        audio_html_attrs={"controls": False},
    )

toggle = st.toggle("🎙  Live セッション ON / OFF", key="toggle")

if toggle and not st.session_state.get("live_on"):
    st.session_state.stop_evt = start_live()
    st.session_state.live_on = True
    status.success("🟢 会話中")

elif not toggle and st.session_state.get("live_on"):
    st.session_state.stop_evt.set()
    st.session_state.live_on = False
    status.warning("🔴 停止中")

# ────────── デバッグパネル ────────────────────────────────────────────
with st.expander("Debug", expanded=False):
    st.write("Mic queue         :", mic_q.qsize())
    st.write("Spk queue         :", spk_q.qsize())
    st.write("silence_cnt       :", MicSender.silence)
    st.write("live_on           :", st.session_state.get("live_on", False))
    st.write("ctx_mic.state     :", getattr(ctx_mic, "state", None))
    st.write("ctx_mic.processor :", id(getattr(ctx_mic, "processor", None)))
    st.write("ctx_spk.state     :", getattr(ctx_spk, "state", None))
    st.write("ctx_spk.processor :", id(getattr(ctx_spk, "processor", None)))
