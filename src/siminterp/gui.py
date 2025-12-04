import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
from typing import Optional

from openai import OpenAI

from .config import AppConfig
from .audio.devices import enumerate_devices
from .pipeline import InterpretationPipeline
from .logging_utils import RichLogger
from .transcription.engines import create_transcriber
from .dictionary import load_dictionary
from .__main__ import build_translator, build_tts_engine

class GuiLogger(RichLogger):
    def __init__(self, log_file, text_widget):
        super().__init__(log_file)
        self.text_widget = text_widget

    def log_text(self, message: str) -> None:
        super().log_text(message)
        self._append_text(message + "\n")

    def log_panel(self, message: str, title: str, style: str) -> None:
        super().log_panel(message, title, style)
        self._append_text(f"[{title}] {message}\n")
    
    def _append_text(self, text):
        def _update():
            self.text_widget.insert(tk.END, text)
            self.text_widget.see(tk.END)
        self.text_widget.after(0, _update)

class SimInterpGUI:
    def __init__(self, root: tk.Tk, config: AppConfig):
        self.root = root
        self.root.title("同声传译")
        self.config = config
        self.pipeline: Optional[InterpretationPipeline] = None
        
        self.input_devices, self.output_devices = enumerate_devices()
        
        self._create_widgets()
        
    def _create_widgets(self):
        # Input Device
        tk.Label(self.root, text="输入设备：").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.input_device_var = tk.StringVar()
        self.input_combo = ttk.Combobox(self.root, textvariable=self.input_device_var, state="readonly")
        self.input_combo['values'] = [f"{d.index}: {d.name}" for d in self.input_devices]
        if self.config.input_device_index is not None:
            for val in self.input_combo['values']:
                if val.startswith(f"{self.config.input_device_index}:"):
                    self.input_combo.set(val)
                    break
        if not self.input_combo.get() and self.input_devices:
             self.input_combo.current(0)
        self.input_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Output Device
        tk.Label(self.root, text="输出设备：").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.output_device_var = tk.StringVar()
        self.output_combo = ttk.Combobox(self.root, textvariable=self.output_device_var, state="readonly")
        self.output_combo['values'] = [f"{d.index}: {d.name}" for d in self.output_devices]
        if self.config.output_device_index is not None:
            for val in self.output_combo['values']:
                if val.startswith(f"{self.config.output_device_index}:"):
                    self.output_combo.set(val)
                    break
        if not self.output_combo.get() and self.output_devices:
            self.output_combo.current(0)
        self.output_combo.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # Input Language
        tk.Label(self.root, text="输入语言：").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.input_lang_var = tk.StringVar(value=self.config.input_language)
        self.input_lang_combo = ttk.Combobox(self.root, textvariable=self.input_lang_var)
        self.input_lang_combo['values'] = ['en', 'zh', 'fr', 'es', 'de', 'ja', 'ko']  # Common languages
        self.input_lang_combo.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # Target Language
        tk.Label(self.root, text="目标语言：").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.target_lang_var = tk.StringVar(value=self.config.translation_language)
        self.target_lang_combo = ttk.Combobox(self.root, textvariable=self.target_lang_var)
        self.target_lang_combo['values'] = ['en', 'zh', 'fr', 'es', 'de', 'ja', 'ko']  # Common languages
        self.target_lang_combo.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # Pause Threshold
        tk.Label(self.root, text="停顿阈值 (秒)：").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.pause_threshold_var = tk.StringVar(value=str(self.config.pause_threshold))
        self.pause_threshold_entry = tk.Entry(self.root, textvariable=self.pause_threshold_var)
        self.pause_threshold_entry.grid(row=4, column=1, padx=5, pady=5, sticky="ew")

        # TTS Speed
        tk.Label(self.root, text="TTS 语速：").grid(row=5, column=0, padx=5, pady=5, sticky="w")
        self.tts_speed_var = tk.StringVar(value=str(self.config.tts_speed))
        self.tts_speed_entry = tk.Entry(self.root, textvariable=self.tts_speed_var)
        self.tts_speed_entry.grid(row=5, column=1, padx=5, pady=5, sticky="ew")

        # Inference Device
        tk.Label(self.root, text="推理设备：").grid(row=6, column=0, padx=5, pady=5, sticky="w")
        self.device_var = tk.StringVar(value=self.config.whisper_device)
        self.device_combo = ttk.Combobox(self.root, textvariable=self.device_var, state="readonly")
        self.device_combo['values'] = ['auto', 'cpu', 'cuda']
        self.device_combo.grid(row=6, column=1, padx=5, pady=5, sticky="ew")

        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=10)
        
        self.start_btn = tk.Button(btn_frame, text="开始收音", command=self.start_listening, bg="green", fg="white")
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(btn_frame, text="停止", command=self.stop_listening, state=tk.DISABLED, bg="red", fg="white")
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # Log Area
        self.log_area = scrolledtext.ScrolledText(self.root, width=80, height=20)
        self.log_area.grid(row=8, column=0, columnspan=2, padx=5, pady=5)

        self.root.columnconfigure(1, weight=1)

    def _get_device_index(self, combo_value: str) -> int:
        return int(combo_value.split(":")[0])

    def start_listening(self):
        # Update config from UI first (Main Thread)
        input_val = self.input_combo.get()
        output_val = self.output_combo.get()
        input_idx = self._get_device_index(input_val) if input_val else None
        output_idx = self._get_device_index(output_val) if output_val else None
        
        self.config.input_device_index = input_idx
        self.config.output_device_index = output_idx
        self.config.input_language = self.input_lang_var.get()
        self.config.translation_language = self.target_lang_var.get()
        self.config.whisper_device = self.device_var.get()
        try:
            self.config.pause_threshold = float(self.pause_threshold_var.get())
            self.config.tts_speed = float(self.tts_speed_var.get())
        except ValueError:
            self.log_area.insert(tk.END, "错误：阈值或语速格式无效。\n")
            return

        # Disable inputs immediately to prevent multiple clicks
        self.start_btn.config(state=tk.DISABLED)
        self.input_combo.config(state=tk.DISABLED)
        self.output_combo.config(state=tk.DISABLED)
        self.input_lang_combo.config(state=tk.DISABLED)
        self.target_lang_combo.config(state=tk.DISABLED)
        self.pause_threshold_entry.config(state=tk.DISABLED)
        self.tts_speed_entry.config(state=tk.DISABLED)
        self.device_combo.config(state=tk.DISABLED)
        
        # Clear log area
        self.log_area.delete('1.0', tk.END)
        self.log_area.insert(tk.END, "正在初始化... 请稍候。\n")

        threading.Thread(target=self._start_background, daemon=True).start()

    def _start_background(self):
        try:
            # Initialize components (Background Thread)
            # Note: GuiLogger uses root.after so it's thread-safe
            logger = GuiLogger(self.config.log_file, self.log_area)
            logger.log_text("开始初始化...")
            
            client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)
            logger.log_text("OpenAI 客户端已初始化。")
            
            # Heavy lifting: loading models
            logger.log_text("正在加载转录模型... (可能需要一些时间)")
            transcriber = create_transcriber(self.config)
            logger.log_text("转录模型已加载。")

            translator = build_translator(self.config, client)
            tts_engine = build_tts_engine(self.config, client)
            dictionary = load_dictionary(self.config.dictionary_path)

            self.pipeline = InterpretationPipeline(
                config=self.config,
                logger=logger,
                transcriber=transcriber,
                dictionary=dictionary,
                translator=translator,
                tts_engine=tts_engine,
            )
            
            logger.log_text("流水线已创建。正在启动...")
            
            # Enable stop button (Main Thread update)
            self.root.after(0, lambda: self.stop_btn.config(state=tk.NORMAL))
            
            # Start pipeline (this method blocks until stop is called? No, we changed it to non-blocking start)
            self.pipeline.start()
            
        except Exception as e:
            # Schedule error update on main thread
            print(f"Background thread error: {e}")  # Print to console for debugging
            self.root.after(0, lambda error=e: self._handle_start_error(error))

    def _handle_start_error(self, e):
        self.log_area.insert(tk.END, f"启动错误：{str(e)}\n")
        self.log_area.see(tk.END)
        self.stop_listening() # Reset UI state

    def stop_listening(self):
        if self.pipeline:
            self.pipeline.stop()
            self.pipeline = None
        
        self.log_area.delete('1.0', tk.END)
        
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.input_combo.config(state="readonly")
        self.output_combo.config(state="readonly")
        self.input_lang_combo.config(state=tk.NORMAL)
        self.target_lang_combo.config(state=tk.NORMAL)
        self.pause_threshold_entry.config(state=tk.NORMAL)
        self.tts_speed_entry.config(state=tk.NORMAL)
        self.device_combo.config(state="readonly")

def run_gui(config: AppConfig):
    root = tk.Tk()
    app = SimInterpGUI(root, config)
    root.mainloop()
