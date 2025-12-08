import asyncio
import websockets
import pyaudio
import json
import base64
import os
import uuid
import sys
import subprocess
from dotenv import load_dotenv
import argparse
from typing import Optional
import ssl
try:
    import certifi
    HAVE_CERTIFI = True
except Exception:
    HAVE_CERTIFI = False

# Protobuf imports (required for AST v4). We expect a local 'python_protogen' folder
# containing compiled protobuf modules.
PROTOGEN_PATH = os.environ.get("PROTOGEN_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "python_protogen"))
if PROTOGEN_PATH and os.path.isdir(PROTOGEN_PATH):
    sys.path.append(PROTOGEN_PATH)
try:
    from products.understanding.ast.ast_service_pb2 import TranslateRequest, TranslateResponse
    from common.events_pb2 import Type
    HAVE_PROTO = True
except Exception:
    HAVE_PROTO = False

# 加载 .env 文件
load_dotenv()

# ================= 配置区域 =================
# AST v4 WebSocket URL（参考 ast_demo.py）
WS_URL = os.environ.get(
    "VOLCENGINE_AST_WS_URL",
    "wss://openspeech.bytedance.com/api/v4/ast/v2/translate",
)

# Headers（参考 ast_demo.py）
APP_KEY = os.environ.get("VOLCENGINE_APP_KEY", "3492256663")
ACCESS_KEY = os.environ.get("VOLCENGINE_ACCESS_KEY", "_-CNOmlZnKYMgUSBJ-3naYWf60Ib7pYr")
RESOURCE_ID = os.environ.get("VOLCENGINE_RESOURCE_ID", "volc.service_type.10053")

# 5. 音频设置（输入 16kHz 单声道 pcm16，输出 24kHz）
RATE = 16000
OUTPUT_RATE = 24000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1280
# ===========================================

class DoubaoRealtimeTranslator:
    def __init__(self, input_language="Chinese", target_language="English"):
        self.input_language = input_language
        self.target_language = target_language
        self.p = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        self._recv_opus: Optional[bytearray] = bytearray()
        self._ffmpeg = None
        self._decode_task = None
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

    def _lang_to_code(self, name: str) -> str:
        n = (name or "").strip().lower()
        if n in ("chinese", "zh", "中文", "汉语"):
            return "zh"
        if n in ("english", "en", "英语"):
            return "en"
        return n[:2] or "zh"

    def setup_audio(self):
        """初始化音频流"""
        self.input_stream = self.p.open(
            format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK
        )
        self.output_stream = self.p.open(
            format=FORMAT, channels=CHANNELS, rate=OUTPUT_RATE, output=True, frames_per_buffer=CHUNK
        )

    async def send_audio_loop(self, ws):
        print(f"🎤 正在监听... (将 {self.input_language} 翻译为 {self.target_language})")
        if not HAVE_PROTO:
            print("缺少 Protobuf 模块，请将 python_protogen 放到项目根目录或设置 PROTOGEN_PATH。")
            return
        try:
            while True:
                data = await asyncio.to_thread(self.input_stream.read, CHUNK, exception_on_overflow=False)
                req = TranslateRequest()
                req.event = Type.TaskRequest
                req.request_meta.SessionID = self.session_id
                req.user.uid = "ast_py_client"
                req.user.did = "ast_py_client"
                req.source_audio.format = "wav"
                req.source_audio.rate = RATE
                req.source_audio.bits = 16
                req.source_audio.channel = 1
                req.source_audio.binary_data = data
                await ws.send(req.SerializeToString())
                await asyncio.sleep(0.08)
        except Exception as e:
            print(f"发送出错: {e}")
        finally:
            try:
                finish = TranslateRequest()
                finish.event = Type.FinishSession
                finish.request_meta.SessionID = self.session_id
                await ws.send(finish.SerializeToString())
            except Exception:
                pass

    async def receive_audio_loop(self, ws):
        print("🔊 准备播放翻译...")
        if not HAVE_PROTO:
            print("缺少 Protobuf 模块，无法解析二进制响应。")
            return
        try:
            async for message in ws:
                if not isinstance(message, (bytes, bytearray)):
                    try:
                        evt = json.loads(message)
                        ev = evt.get("event") or evt.get("type")
                        def _is(name: str) -> bool:
                            return isinstance(ev, str) and name in ev
                        # 字幕事件优先
                        if _is("SourceSubtitleStart"):
                            self._source_spk = bool(evt.get("spk_chg", False))
                        elif _is("SourceSubtitleResponse"):
                            self._emit_transcription(evt.get("text", ""), getattr(self, "_source_spk", False))
                        elif _is("SourceSubtitleEnd"):
                            text = (evt.get("text", "") or "").strip()
                            if text:
                                print(f"🟨 转录: {text}")
                                self._last_transcript_line = text
                            self._transcript_buffer = ""
                            self._transcript_printed = True
                            self._transcript_done = False
                        elif _is("TranslationSubtitleStart"):
                            self._translation_spk = bool(evt.get("spk_chg", False))
                        elif _is("TranslationSubtitleResponse"):
                            self._emit_translation(evt.get("text", ""), getattr(self, "_translation_spk", False))
                        elif _is("TranslationSubtitleEnd"):
                            text = (evt.get("text", "") or "").strip()
                            if text:
                                print(f"🟦 翻译: {text}")
                                self._last_translation_line = text
                            self._translation_buffer = ""
                            self._translation_printed = True
                            self._translation_done = False
                        # 兼容 response.* 事件（完成/增量）
                        elif _is("response.audio_transcript.done") or _is("response.input_audio_transcription.done"):
                            self._transcript_done = True
                            if evt.get("text"):
                                self._transcript_buffer = evt.get("text")
                            self._flush_transcription()
                        elif _is("response.input_audio_translation.done"):
                            self._translation_done = True
                            if evt.get("text"):
                                self._translation_buffer = evt.get("text")
                            self._flush_translation()
                        elif isinstance(ev, str) and "transcript" in ev and ("delta" in ev or "response" in ev):
                            self._emit_transcription(evt.get("text", ""), False)
                        elif isinstance(ev, str) and "translation" in ev and ("delta" in ev or "response" in ev):
                            self._emit_translation(evt.get("text", ""), False)
                        else:
                            print(f"ℹ️ 事件: {json.dumps(evt, ensure_ascii=False)}")
                    except Exception:
                        pass
                    continue
                resp = TranslateResponse()
                try:
                    resp.ParseFromString(message)
                except Exception as e:
                    print(f"解析二进制响应失败: {e}")
                    continue
                if resp.event == Type.UsageResponse:
                    continue
                if resp.event == Type.SessionFailed or resp.event == Type.SessionCanceled:
                    print(f"会话失败: {resp.response_meta.Message}")
                    break
                if resp.event == Type.SessionFinished:
                    break
                # Protobuf 文本回退路径：仅在完成信号触发打印
                if getattr(resp, "text", None):
                    txt = resp.text
                    is_source = self._is_source_text(txt)
                    if is_source:
                        self._emit_transcription(txt, getattr(resp, "spk_chg", False))
                    else:
                        self._emit_translation(txt, getattr(resp, "spk_chg", False))
                if getattr(resp, "spk_chg", False):
                    self._transcript_done = True
                    self._translation_done = True
                    self._flush_transcription()
                    self._flush_translation()
                if resp.data and getattr(self, "_ffmpeg", None) and self._ffmpeg.stdin:
                    try:
                        await asyncio.to_thread(self._ffmpeg.stdin.write, resp.data)
                        await asyncio.to_thread(self._ffmpeg.stdin.flush)
                    except Exception as e:
                        print(f"写入 ffmpeg 失败: {e}")
        except Exception as e:
            print(f"接收出错: {e}")

    async def run(self):
        self.setup_audio()
        
        headers = {
            "X-Api-App-Key": APP_KEY,
            "X-Api-Access-Key": ACCESS_KEY,
            "X-Api-Resource-Id": RESOURCE_ID,
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }

        print(f"🔗 连接 AST v4 服务...")
        ssl_ctx = ssl.create_default_context()
        custom_cafile = os.environ.get("VOLCENGINE_CA_CERT") or os.environ.get("SSL_CERT_FILE")
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
        async with websockets.connect(WS_URL, additional_headers=headers, max_size=1000000000, ping_interval=None, ssl=ssl_ctx) as ws:
            print("✅ 连接成功！")
            if not HAVE_PROTO:
                raise RuntimeError("缺少 Protobuf 模块，请将 python_protogen 放到项目根目录或设置 PROTOGEN_PATH。")

            self.session_id = str(uuid.uuid4())
            start = TranslateRequest()
            start.event = Type.StartSession
            start.request_meta.SessionID = self.session_id
            start.user.uid = "ast_py_client"
            start.user.did = "ast_py_client"
            start.source_audio.format = "wav"
            start.source_audio.rate = RATE
            start.source_audio.bits = 16
            start.source_audio.channel = 1
            start.target_audio.format = "ogg_opus"
            start.target_audio.rate = OUTPUT_RATE
            start.request.mode = "s2s"
            start.request.source_language = self._lang_to_code(self.input_language)
            start.request.target_language = self._lang_to_code(self.target_language)
            await ws.send(start.SerializeToString())

            try:
                self._ffmpeg = subprocess.Popen(
                    [
                        "ffmpeg",
                        "-v", "fatal",
                        "-hide_banner",
                        "-nostdin",
                        "-i", "-",           # read Ogg Opus from stdin
                        "-f", "s16le",
                        "-acodec", "pcm_s16le",
                        "-ac", str(CHANNELS),
                        "-ar", str(OUTPUT_RATE),
                        "-",                   # write raw PCM to stdout
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                )
                self._decode_task = asyncio.create_task(self._ffmpeg_decode_playback())
            except Exception as e:
                print(f"启动 ffmpeg 失败，无法进行流式解码: {e}")

            # 2. 启动双向任务
            await asyncio.gather(
                self.send_audio_loop(ws),
                self.receive_audio_loop(ws)
            )
            try:
                if getattr(self, "_ffmpeg", None) and self._ffmpeg.stdin:
                    self._ffmpeg.stdin.close()
                if getattr(self, "_decode_task", None):
                    await self._decode_task
                if getattr(self, "_ffmpeg", None):
                    try:
                        self._ffmpeg.wait(timeout=2)
                    except Exception:
                        pass
                self._flush_transcription()
                self._flush_translation()
            except Exception:
                pass


    def close(self):
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
        try:
            if getattr(self, "_ffmpeg", None):
                if self._ffmpeg.stdin:
                    try:
                        self._ffmpeg.stdin.close()
                    except Exception:
                        pass
                self._ffmpeg.terminate()
        except Exception:
            pass
        self.p.terminate()

    async def _ffmpeg_decode_playback(self):
        if not getattr(self, "_ffmpeg", None) or not self._ffmpeg.stdout:
            return
        try:
            while True:
                chunk = await asyncio.to_thread(self._ffmpeg.stdout.read, 4096)
                if not chunk:
                    break
                try:
                    self.output_stream.write(chunk)
                except Exception as e:
                    print(f"播放错误: {e}")
                    break
        except Exception as e:
            print(f"解码播放任务错误: {e}")

    def _emit_transcription(self, chunk: str, spk_chg: bool) -> None:
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

    def _emit_translation(self, chunk: str, spk_chg: bool) -> None:
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

    def _has_cjk(self, s: str) -> bool:
        for ch in s:
            code = ord(ch)
            if (
                0x4E00 <= code <= 0x9FFF or
                0x3400 <= code <= 0x4DBF or
                0x20000 <= code <= 0x2A6DF or
                0x2A700 <= code <= 0x2B73F or
                0x2B740 <= code <= 0x2B81F or
                0x2B820 <= code <= 0x2CEAF or
                0xF900 <= code <= 0xFAFF or
                0x2F800 <= code <= 0x2FA1F or
                0x3040 <= code <= 0x30FF or
                0x31F0 <= code <= 0x31FF or
                0xAC00 <= code <= 0xD7AF
            ):
                return True
        return False

    def _is_source_text(self, s: str) -> bool:
        src = self._lang_to_code(self.input_language)
        if src in ("zh", "ja", "ko"):
            return self._has_cjk(s)
        if src == "en":
            return not self._has_cjk(s)
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Doubao Realtime Translator")
    parser.add_argument("--input-language", default="Chinese", help="Input language (default: Chinese)")
    parser.add_argument("--target-language", default="English", help="Target language (default: English)")
    args = parser.parse_args()

    translator = DoubaoRealtimeTranslator(input_language=args.input_language, target_language=args.target_language)
    try:
        asyncio.run(translator.run())
    except KeyboardInterrupt:
        print("\n👋 程序已停止")
    except Exception as e:
        print(f"\n❌ 发生异常: {e}")
        print("提示: 请检查 ENDPOINT_ID 是否正确，以及是否开通了 Realtime 权限。")
    finally:
        translator.close()
