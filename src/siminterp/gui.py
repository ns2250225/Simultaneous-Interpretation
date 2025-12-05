import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import os
from typing import Optional

from openai import OpenAI
from dotenv import load_dotenv

from .config import AppConfig
from .audio.devices import enumerate_devices
from .pipeline import InterpretationPipeline
from .logging_utils import RichLogger
from .transcription.engines import create_transcriber
from .dictionary import load_dictionary
from .openai_models import TRANSLATION_MODELS
from .__main__ import build_translator, build_tts_engine

# TTS Voice Options
TTS_VOICES = {
    "openai": [
        "alloy", "ash", "ballad", "coral", "echo", 
        "fable", "nova", "onyx", "sage", "shimmer"
    ],
    "edge-tts": [
        "zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-YunjianNeural",
        "zh-CN-YunxiNeural", "zh-CN-YunxiaNeural", "zh-CN-YunyangNeural",
        "zh-CN-liaoning-XiaobeiNeural", "zh-CN-shaanxi-XiaoniNeural",
        "zh-HK-HiuGaaiNeural", "zh-HK-HiuMaanNeural",
        "en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural" # Added common EN voices just in case
    ],
    "coqui": [
        "Ana Florence"
    ]
}

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
        self.root.geometry("900x650") # Set default size (wider for side-by-side layout)
        self.config = config
        self.pipeline: Optional[InterpretationPipeline] = None
        
        self.input_devices, self.output_devices = enumerate_devices()
        
        # Setup Notebook (Tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both')
        
        self.main_tab = tk.Frame(self.notebook)
        self.settings_tab = tk.Frame(self.notebook)
        
        self.notebook.add(self.main_tab, text='主界面')
        self.notebook.add(self.settings_tab, text='设置')
        
        self._create_main_tab()
        self._create_settings_tab()
        
        # Initialize UI state
        self._on_tts_provider_change(None)
        
    def _create_main_tab(self):
        # Main container for 2-column layout
        container = ttk.Frame(self.main_tab, padding="10")
        container.pack(fill="both", expand=True)

        # Left Panel: Settings
        settings_frame = ttk.Frame(container)
        settings_frame.pack(side=tk.LEFT, fill="both", expand=False, padx=(0, 10))
        
        # Configure grid weights for settings
        settings_frame.columnconfigure(1, weight=1)

        # Right Panel: Logs
        log_frame = ttk.Frame(container)
        log_frame.pack(side=tk.LEFT, fill="both", expand=True)
        
        self.row_counter = 0
        
        def add_setting(label_text, component, col=1, sticky="ew"):
            # Label (Right aligned)
            if label_text:
                ttk.Label(settings_frame, text=label_text + (":" if not label_text.startswith("---") else "")).grid(
                    row=self.row_counter, column=0, padx=5, pady=5, sticky="e"
                )
            # Component
            component.grid(row=self.row_counter, column=col, padx=5, pady=5, sticky=sticky)
            self.row_counter += 1

        def add_separator(title):
            ttk.Separator(settings_frame, orient="horizontal").grid(
                row=self.row_counter, column=0, columnspan=2, sticky="ew", pady=(15, 5)
            )
            self.row_counter += 1
            ttk.Label(settings_frame, text=title, font=("", 9, "bold")).grid(
                row=self.row_counter, column=0, columnspan=2, sticky="w", padx=5, pady=2
            )
            self.row_counter += 1

        # --- Device Settings ---
        add_separator("设备设置")

        # Input Device
        self.input_device_var = tk.StringVar()
        self.input_combo = ttk.Combobox(settings_frame, textvariable=self.input_device_var, state="readonly")
        self.input_combo['values'] = [f"{d.index}: {d.name}" for d in self.input_devices]
        if self.config.input_device_index is not None:
            for val in self.input_combo['values']:
                if val.startswith(f"{self.config.input_device_index}:"):
                    self.input_combo.set(val)
                    break
        if not self.input_combo.get() and self.input_devices:
             self.input_combo.current(0)
        add_setting("输入设备", self.input_combo)

        # Output Device
        self.output_device_var = tk.StringVar()
        self.output_combo = ttk.Combobox(settings_frame, textvariable=self.output_device_var, state="readonly")
        self.output_combo['values'] = [f"{d.index}: {d.name}" for d in self.output_devices]
        if self.config.output_device_index is not None:
            for val in self.output_combo['values']:
                if val.startswith(f"{self.config.output_device_index}:"):
                    self.output_combo.set(val)
                    break
        if not self.output_combo.get() and self.output_devices:
            self.output_combo.current(0)
        add_setting("输出设备", self.output_combo)

        # --- Language & Model Settings ---
        add_separator("语言与模型")

        # Input Language
        self.input_lang_var = tk.StringVar(value=self.config.input_language)
        self.input_lang_combo = ttk.Combobox(settings_frame, textvariable=self.input_lang_var)
        self.input_lang_combo['values'] = ['en', 'zh', 'fr', 'es', 'de', 'ja', 'ko']
        add_setting("输入语言", self.input_lang_combo)

        # Target Language
        self.target_lang_var = tk.StringVar(value=self.config.translation_language)
        self.target_lang_combo = ttk.Combobox(settings_frame, textvariable=self.target_lang_var)
        self.target_lang_combo['values'] = ['en', 'zh', 'fr', 'es', 'de', 'ja', 'ko']
        add_setting("目标语言", self.target_lang_combo)

        # Translation Model
        self.translation_model_var = tk.StringVar(value=self.config.openai_model)
        self.translation_model_combo = ttk.Combobox(settings_frame, textvariable=self.translation_model_var)
        self.translation_model_combo['values'] = list(TRANSLATION_MODELS)
        add_setting("翻译模型", self.translation_model_combo)

        # --- Advanced Settings ---
        add_separator("高级参数")

        # Pause Threshold
        self.pause_threshold_var = tk.StringVar(value=str(self.config.pause_threshold))
        self.pause_threshold_entry = tk.Entry(settings_frame, textvariable=self.pause_threshold_var)
        add_setting("停顿阈值 (秒)", self.pause_threshold_entry)

        # TTS Speed
        self.tts_speed_var = tk.StringVar(value=str(self.config.tts_speed))
        self.tts_speed_entry = tk.Entry(settings_frame, textvariable=self.tts_speed_var)
        add_setting("TTS 语速", self.tts_speed_entry)

        # Inference Device
        self.device_var = tk.StringVar(value=self.config.whisper_device)
        self.device_combo = ttk.Combobox(settings_frame, textvariable=self.device_var, state="readonly")
        self.device_combo['values'] = ['auto', 'cpu', 'cuda']
        add_setting("推理设备", self.device_combo)

        # --- TTS Settings ---
        add_separator("TTS 设置")

        # TTS Provider
        self.tts_provider_var = tk.StringVar(value=self.config.tts_provider)
        self.tts_provider_combo = ttk.Combobox(settings_frame, textvariable=self.tts_provider_var, state="readonly")
        self.tts_provider_combo['values'] = ['openai', 'coqui', 'edge-tts']
        self.tts_provider_combo.bind("<<ComboboxSelected>>", self._on_tts_provider_change)
        add_setting("TTS 引擎", self.tts_provider_combo)

        # TTS Voice (Initially hidden/dynamic)
        # We create the widgets but don't grid them yet. 
        # _on_tts_provider_change needs to know where to grid them.
        # We'll store the row index for dynamic insertion or just reserve a slot.
        # For simplicity, let's just add them to the grid but manage visibility via _on_tts_provider_change
        # Actually, our helper function grids immediately. Let's handle this manually.
        
        self.tts_voice_label = ttk.Label(settings_frame, text="TTS 语音:")
        self.tts_voice_var = tk.StringVar(value=self.config.tts_voice)
        self.tts_voice_combo = ttk.Combobox(settings_frame, textvariable=self.tts_voice_var)
        
        # We will grid these in _on_tts_provider_change. We save the row index to use.
        self.tts_voice_row = self.row_counter
        self.row_counter += 1
        
        # --- Controls ---
        btn_frame = ttk.Frame(settings_frame)
        btn_frame.grid(row=self.row_counter, column=0, columnspan=2, pady=20)
        self.row_counter += 1
        
        self.start_btn = tk.Button(btn_frame, text="🟢 开始收音", command=self.start_listening)
        if self.root.tk.call('tk', 'windowingsystem') != 'aqua':
             self.start_btn.config(bg="green", fg="white")
        self.start_btn.pack(side=tk.LEFT, padx=10)
        
        self.stop_btn = tk.Button(btn_frame, text="🛑 停止", command=self.stop_listening, state=tk.DISABLED)
        if self.root.tk.call('tk', 'windowingsystem') != 'aqua':
             self.stop_btn.config(bg="red", fg="white")
        self.stop_btn.pack(side=tk.LEFT, padx=10)

        # --- Log Area ---
        ttk.Label(log_frame, text="输出/日志：").pack(anchor="w", pady=(0, 5))

        self.log_area = scrolledtext.ScrolledText(log_frame, width=40, height=10, wrap="word", relief="groove")
        self.log_area.pack(fill="both", expand=True)

    def _create_settings_tab(self):
        tk.Label(self.settings_tab, text="编辑 .env 配置文件：").pack(anchor="w", padx=5, pady=5)
        
        self.env_text = scrolledtext.ScrolledText(self.settings_tab, width=80, height=25)
        self.env_text.pack(expand=True, fill="both", padx=5, pady=5)
        
        # Load .env content
        if os.path.exists(".env"):
            try:
                with open(".env", "r", encoding="utf-8") as f:
                    content = f.read()
                    self.env_text.insert(tk.END, content)
            except Exception as e:
                self.env_text.insert(tk.END, f"# Error loading .env: {e}")
        else:
             self.env_text.insert(tk.END, "# .env file not found. Create one here.\n")
             self.env_text.insert(tk.END, "OPENAI_API_KEY=your_key_here\n")

        btn_frame = tk.Frame(self.settings_tab)
        btn_frame.pack(pady=10)
        
        self.save_env_btn = tk.Button(btn_frame, text="保存配置", command=self.save_settings)
        if self.root.tk.call('tk', 'windowingsystem') != 'aqua':
             self.save_env_btn.config(bg="blue", fg="white")
        self.save_env_btn.pack()

    def _on_tts_provider_change(self, event):
        provider = self.tts_provider_var.get()
        
        # Hide first
        self.tts_voice_label.grid_forget()
        self.tts_voice_combo.grid_forget()
        
        if provider in TTS_VOICES:
            # Show and populate
            self.tts_voice_label.grid(row=self.tts_voice_row, column=0, padx=10, pady=5, sticky="e")
            self.tts_voice_combo.grid(row=self.tts_voice_row, column=1, padx=10, pady=5, sticky="ew")
            self.tts_voice_combo['values'] = TTS_VOICES[provider]
            
            # Set default if current value is not valid for new provider
            current_val = self.tts_voice_var.get()
            if current_val not in TTS_VOICES[provider]:
                self.tts_voice_combo.current(0)
        else:
            # Fallback or other providers? Keep hidden or show entry?
            # For now, if not in our list, we hide it or show generic entry?
            # Let's hide it as per requirement "default hidden, show when selected"
            # But wait, if user selects something else, they might need to type it manually?
            # The requirement says "Gui界面的TTS 语音默认隐藏， 选择TTS 引擎的时候显示".
            # It implies we should show it if a valid engine is selected.
            # If the provider is not in our map, maybe we should allow manual entry?
            # But the current map covers all 3 options.
            pass

    def save_settings(self):
        content = self.env_text.get("1.0", tk.END).strip()
        try:
            with open(".env", "w", encoding="utf-8") as f:
                f.write(content)
            
            # Reload environment variables
            load_dotenv(override=True)
            
            # Update config
            self.config.api_key = os.getenv("OPENAI_API_KEY", self.config.api_key)
            self.config.base_url = os.getenv("OPENAI_BASE_URL", self.config.base_url)
            
            messagebox.showinfo("成功", "配置已保存并重新加载。")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败: {e}")

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
        self.config.openai_model = self.translation_model_var.get()
        self.config.whisper_device = self.device_var.get()
        self.config.tts_provider = self.tts_provider_var.get()
        self.config.tts_voice = self.tts_voice_var.get()
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
        self.translation_model_combo.config(state=tk.DISABLED)
        self.pause_threshold_entry.config(state=tk.DISABLED)
        self.tts_speed_entry.config(state=tk.DISABLED)
        self.device_combo.config(state=tk.DISABLED)
        self.tts_provider_combo.config(state=tk.DISABLED)
        self.tts_voice_combo.config(state=tk.DISABLED)
        
        # Clear log area
        self.log_area.delete('1.0', tk.END)
        self.log_area.insert(tk.END, "正在初始化... 请稍候。\n")
        self.log_area.see(tk.END)

        # Switch to main tab to show logs
        self.notebook.select(self.main_tab)

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
        self.translation_model_combo.config(state=tk.NORMAL)
        self.pause_threshold_entry.config(state=tk.NORMAL)
        self.tts_speed_entry.config(state=tk.NORMAL)
        self.device_combo.config(state="readonly")
        self.tts_provider_combo.config(state="readonly")
        self.tts_voice_combo.config(state="readonly") # was state=tk.NORMAL in previous, but should be readonly for combo usually, or normal if editable
        self.tts_voice_combo.config(state=tk.NORMAL)

def run_gui(config: AppConfig):
    root = tk.Tk()
    app = SimInterpGUI(root, config)
    root.mainloop()
