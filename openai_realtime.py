import os
import asyncio
import base64
import json
import websockets
import pyaudio

# --- 配置部分 ---
# 请将你的 API Key 设置在环境变量 OPENAI_API_KEY 中，或者直接填在这里
API_KEY = "sk-7zp54GI1xp4alaQuydzcxMLhZW47jJAcIJSJksEo7Vfp18Rd"

# 模型名称，目前通常是 gpt-4o-mini-realtime-preview
# 请根据 OpenAI 文档确认最新的模型名称
MODEL_NAME = "gpt-4o-realtime-preview"

# WebSocket URL
URL = f"ws://jeniya.top/v1/realtime?model={MODEL_NAME}"

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
                
                # 给其他任务一点时间执行
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
                
                # 打印一下当前的转录文本 (可选，方便调试)
                elif event_type == "response.audio_transcript.delta":
                    print(event.get("delta"), end="", flush=True)
                
                elif event_type == "response.audio_transcript.done":
                    print("\n") # 换行
                
                elif event_type == "error":
                    print(f"\n❌ API 错误: {event.get('error')}")

        except Exception as e:
            print(f"接收音频出错: {e}")

    async def run(self):
        self.setup_audio()
        
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        }

        print(f"🔗 正在连接到 {MODEL_NAME} ...")
        
        async with websockets.connect(URL, additional_headers=headers) as websocket:
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
