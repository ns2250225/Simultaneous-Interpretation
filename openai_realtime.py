import os
import asyncio
import base64
import json
import websockets
import pyaudio
import ssl
import time
from array import array
from urllib.parse import urlparse
try:
    import certifi
    HAVE_CERTIFI = True
except Exception:
    HAVE_CERTIFI = False

# --- 配置部分 ---
API_KEY = os.environ.get("OPENAI_API_KEY", "sk-7zp54GI1xp4alaQuydzcxMLhZW47jJAcIJSJksEo7Vfp18Rd")

MODEL_NAME = os.environ.get("OPENAI_TRANSLATION_MODEL", "gpt-4o-realtime-preview")

BASE_URL = os.environ.get("OPENAI_BASE_URL", "ws://jeniya.top")
URL = f"{BASE_URL}/v1/realtime?model={MODEL_NAME}"

# 音频设置
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000  # Realtime API 默认通常推荐 24kHz
CHUNK = 1024  # 每次读取的音频帧大小

class RealtimeTranslator:
    def __init__(self, target_language="English"):
        self.target_language = target_language
        self.p = pyaudio.PyAudio()
        self.audio_in_stream = None
        self.audio_out_stream = None
        self._transcript_buffer = ""
        self._translation_buffer = ""
        self._last_transcript_line = ""
        self._last_translation_line = ""
        self._last_transcript_chunk = ""
        self._last_translation_chunk = ""
        self._transcript_printed = False
        self._translation_printed = False
        self._transcript_done = False
        self._translation_done = False

    def setup_audio(self):
        """初始化麦克风输入和扬声器输出流"""
        # 输入流 (麦克风)
        self.audio_in_stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
        # 输出流 (扬声器)
        self.audio_out_stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            frames_per_buffer=CHUNK
        )

    async def send_audio(self, websocket):
        """持续读取麦克风数据并发送给 API"""
        print("🎤 开始通过麦克风录音...")
        try:
            vad_enabled = (os.environ.get("OPENAI_VAD_ENABLED", "1").strip().lower() in ("1", "true", "yes"))
            silence_ms = int(os.environ.get("OPENAI_VAD_SILENCE_MS", "500") or "500")
            min_speech_ms = int(os.environ.get("OPENAI_VAD_MIN_SPEECH_MS", "300") or "300")
            threshold = int(os.environ.get("OPENAI_VAD_THRESHOLD", "500") or "500")
            commit_interval_ms = int(os.environ.get("OPENAI_COMMIT_INTERVAL_MS", "1200") or "1200")
            last_commit = time.monotonic()
            speaking = False
            seg_start = 0.0
            last_voice = time.monotonic()
            while True:
                # 1. 从麦克风读取原始 PCM 数据 (非阻塞方式读取稍微复杂，这里用简单的阻塞读取配合 asyncio.to_thread 更好，但在循环中直接读也可以)
                # 为了避免阻塞 asyncio 事件循环，这里使用 await asyncio.sleep(0) 让出控制权，或者使用 run_in_executor
                data = await asyncio.to_thread(self.audio_in_stream.read, CHUNK, exception_on_overflow=False)
                
                # 2. Base64 编码
                base64_audio = base64.b64encode(data).decode("utf-8")
                
                # 3. 发送给 OpenAI
                event = {
                    "type": "input_audio_buffer.append",
                    "audio": base64_audio
                }
                await websocket.send(json.dumps(event))
                
                now = time.monotonic()
                if vad_enabled:
                    samples = array('h')
                    samples.frombytes(data)
                    peak = max((abs(x) for x in samples), default=0)
                    if peak >= threshold:
                        last_voice = now
                        if not speaking:
                            speaking = True
                            seg_start = now
                    elif speaking and (now - last_voice) * 1000 >= silence_ms and (now - seg_start) * 1000 >= min_speech_ms:
                        try:
                            await websocket.send(json.dumps({"type": "input_audio_buffer.commit"}))
                            await websocket.send(json.dumps({"type": "response.create"}))
                        except Exception:
                            pass
                        speaking = False
                        seg_start = 0.0
                else:
                    if (now - last_commit) * 1000 >= commit_interval_ms:
                        try:
                            await websocket.send(json.dumps({"type": "input_audio_buffer.commit"}))
                            await websocket.send(json.dumps({"type": "response.create"}))
                        except Exception:
                            pass
                        last_commit = now
                await asyncio.sleep(0)
        except Exception as e:
            print(f"发送音频出错: {e}")

    async def receive_audio(self, websocket):
        """接收 API 返回的数据并播放"""
        print("🔊 准备接收翻译音频...")
        try:
            async for message in websocket:
                event = json.loads(message)
                event_type = event.get("type")

                # 处理返回的音频增量数据
                if event_type == "response.audio.delta":
                    audio_content = event.get("delta")
                    if audio_content:
                        # 解码 base64 并写入扬声器流
                        audio_data = base64.b64decode(audio_content)
                        self.audio_out_stream.write(audio_data)
                
                elif event_type == "response.audio_transcript.delta":
                    self._emit_transcription(event.get("delta", ""))
                elif event_type == "response.audio_transcript.done":
                    self._transcript_done = True
                    self._flush_transcription()
                
                elif event_type == "response.output_text.delta":
                    self._emit_translation(event.get("delta", ""))
                elif event_type == "response.output_text.done":
                    self._translation_done = True
                    self._flush_translation()
                
                elif event_type == "response.text.delta":
                    self._emit_translation(event.get("delta", ""))
                elif event_type == "response.text.done":
                    self._translation_done = True
                    self._flush_translation()
                
                elif event_type == "error":
                    print(f"\n❌ API 错误: {event.get('error')}")

        except Exception as e:
            print(f"接收音频出错: {e}")

    async def run(self):
        self.setup_audio()
        
        if not API_KEY:
            raise RuntimeError("缺少 OPENAI_API_KEY 环境变量")

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        }

        print(f"🔗 正在连接到 {MODEL_NAME} ...")
        ssl_ctx = ssl.create_default_context()
        custom_cafile = os.environ.get("OPENAI_CA_CERT") or os.environ.get("SSL_CERT_FILE")
        if isinstance(custom_cafile, str) and os.path.isfile(custom_cafile):
            try:
                ssl_ctx.load_verify_locations(cafile=custom_cafile)
            except Exception:
                pass
        elif HAVE_CERTIFI:
            try:
                ssl_ctx.load_verify_locations(cafile=certifi.where())
            except Exception:
                pass
        allow_insecure = (os.environ.get("ALLOW_INSECURE_SSL", "").strip().lower() in ("1", "true", "yes"))
        if allow_insecure:
            try:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
            except Exception:
                pass

        parsed = urlparse(URL)
        ws_kwargs = {
            "additional_headers": headers,
            "ping_interval": None,
            "ping_timeout": None,
            "max_size": 1000000000,
        }
        if parsed.scheme == "wss":
            ws_kwargs["ssl"] = ssl_ctx
        async with websockets.connect(URL, **ws_kwargs) as websocket:
            print("✅ 连接成功！请开始说话 (按 Ctrl+C 停止)")

            # 1. 发送 Session 配置：设置 VAD (自动说话检测) 和 系统指令
            session_update = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": (
                        "You are a professional simultaneous interpreter. "
                        f"Your task is to translate whatever the user says into {self.target_language} immediately. "
                        "Do not answer the user's question, just translate the content. "
                        f"If the user speaks {self.target_language}, repeat it clearly or improve the phrasing slightly."
                    ),
                    "voice": "alloy",  # 可选: alloy, echo, shimmer
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": {
                        "type": "server_vad", # 启用服务端语音活动检测，说完话自动回复
                    }
                }
            }
            await websocket.send(json.dumps(session_update))

            # 2. 并行运行 发送 和 接收 任务
            await asyncio.gather(
                self.send_audio(websocket),
                self.receive_audio(websocket)
            )

    def close(self):
        if self.audio_in_stream:
            self.audio_in_stream.stop_stream()
            self.audio_in_stream.close()
        if self.audio_out_stream:
            self.audio_out_stream.stop_stream()
            self.audio_out_stream.close()
        self.p.terminate()

    def _append_incremental(self, buf: str, chunk: str) -> str:
        s = (chunk or "").strip()
        if not s:
            return buf
        if s in buf:
            return buf
        max_overlap = min(len(buf), len(s))
        for k in range(max_overlap, 0, -1):
            if buf[-k:] == s[:k]:
                return buf + s[k:]
        return buf + s

    def _emit_transcription(self, chunk: str) -> None:
        if not chunk:
            return
        if chunk == self._last_transcript_chunk:
            return
        self._last_transcript_chunk = chunk
        new_buf = self._append_incremental(self._transcript_buffer, chunk)
        if new_buf != self._transcript_buffer:
            self._transcript_printed = False
            self._transcript_buffer = new_buf
        if self._transcript_done and not self._transcript_printed:
            line = self._transcript_buffer.strip()
            if line and line != self._last_transcript_line:
                print(f"🟨 转录: {line}")
                self._last_transcript_line = line
            self._transcript_buffer = ""
            self._transcript_printed = True
            self._transcript_done = False

    def _emit_translation(self, chunk: str) -> None:
        if not chunk:
            return
        if chunk == self._last_translation_chunk:
            return
        self._last_translation_chunk = chunk
        new_buf = self._append_incremental(self._translation_buffer, chunk)
        if new_buf != self._translation_buffer:
            self._translation_printed = False
            self._translation_buffer = new_buf
        if self._translation_done and not self._translation_printed:
            line = self._translation_buffer.strip()
            if line:
                last = self._last_translation_line
                if not last or (line != last and not line.startswith(last) and not last.startswith(line)):
                    print(f"🟦 翻译: {line}")
                    self._last_translation_line = line
            self._translation_buffer = ""
            self._translation_printed = True
            self._translation_done = False

    def _flush_transcription(self) -> None:
        if not self._transcript_printed and self._transcript_buffer.strip() and self._transcript_buffer.strip() != self._last_transcript_line:
            print(f"🟨 转录: {self._transcript_buffer.strip()}")
            self._last_transcript_line = self._transcript_buffer.strip()
        self._transcript_buffer = ""
        self._transcript_printed = True
        self._transcript_done = False

    def _flush_translation(self) -> None:
        line = self._translation_buffer.strip()
        if line and not self._translation_printed:
            last = self._last_translation_line
            if not last or (line != last and not line.startswith(last) and not last.startswith(line)):
                print(f"🟦 翻译: {line}")
                self._last_translation_line = line
        self._translation_buffer = ""
        self._translation_printed = True
        self._translation_done = False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OpenAI Realtime Translator")
    parser.add_argument("--target-language", default="English", help="Target language for translation (default: English)")
    args = parser.parse_args()

    translator = RealtimeTranslator(target_language=args.target_language)
    try:
        asyncio.run(translator.run())
    except KeyboardInterrupt:
        print("\n👋 程序已停止")
    finally:
        translator.close()
