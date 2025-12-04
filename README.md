# 基于openai的实时同声传译应用

## 界面预览
![](./demo.png)

## 前置要求
- Python 3.10 或更高版本。
- PyAudio 需要 [PortAudio](http://www.portaudio.com/) 运行时环境。在 macOS 上，您可以使用 `brew install portaudio` 进行安装。
- 存储在环境变量中的 OpenAI API 密钥（设置 `OPENAI_API_KEY` 或创建一个 `.env` 文件）。

## 安装
```bash
pip install -r requirements.txt
```

## 配置
在运行 CLI 之前，创建一个 `.env` 文件或导出环境变量：
```bash
OPENAI_API_KEY=API-KEY
OPENAI_BASE_URL=可以是中转的url
OPENAI_TRANSLATION_MODEL=gpt-4o
OPENAI_TTS_MODEL=tts-1
```

## 使用方法
列出可用的麦克风和扬声器：
```bash
python -m src.siminterp --list-devices
```

启动同声传译会话（示例：将中文翻译成英文，播放合成语音，使用 GPU 加速推理）：
```bash
python -m src.siminterp --input-language zh --target-language en --input-device 1 --output-device 3 --translate --tts --voice alloy --transcriber faster-whisper --whisper-model large-v3 --whisper-device cuda
```

### 高级用法
**使用 Coqui TTS（离线/本地 TTS）：**
```bash
python -m src.siminterp --translate --tts --tts-provider coqui --input-language zh --target-language en
```

**调整停顿阈值（控制断句灵敏度）：**
```bash
python -m src.siminterp --pause-threshold 1.2 ...
```

**加载自定义术语字典：**
```bash
python -m src.siminterp --dictionary dictionary.txt ...
```

按 `CTRL+C` 停止。应用程序将优雅地关闭后台工作线程，并将带时间戳的转录文本保存到您的“tmp”文件夹中。

### 启动 GUI 界面
如果您更喜欢图形化界面，可以使用 `--gui` 参数启动：
```bash
python -m src.siminterp --gui --translate --tts --transcriber faster-whisper --whisper-model large-v3 --whisper-device auto
```
在 GUI 中，您可以方便地选择输入/输出设备、源语言/目标语言、TTS 引擎以及推理设备。

### 支持的whisper模型（一般选large-v3最好）
```
large-v3
large-v2
medium
tiny
base
small
```

### 支持的声音
```
alloy
ash
ballad
coral
echo
fable
nova
onyx
sage
shimmer
```

### 支持的语言
```
{
    'af': 'Afrikaans', 'am': 'Amharic', 'ar': 'Arabic', 'as': 'Assamese', 'az': 'Azerbaijani', 
    'ba': 'Bashkir', 'be': 'Belarusian', 'bg': 'Bulgarian', 'bn': 'Bengali', 'bo': 'Tibetan', 
    'br': 'Breton', 'bs': 'Bosnian', 'ca': 'Catalan', 'cs': 'Czech', 'cy': 'Welsh', 
    'da': 'Danish', 'de': 'German', 'el': 'Greek', 'en': 'English', 'es': 'Spanish', 
    'et': 'Estonian', 'eu': 'Basque', 'fa': 'Persian', 'fi': 'Finnish', 'fo': 'Faroese', 
    'fr': 'French', 'gl': 'Galician', 'gu': 'Gujarati', 'ha': 'Hausa', 'haw': 'Hawaiian', 
    'he': 'Hebrew', 'hi': 'Hindi', 'hr': 'Croatian', 'ht': 'Haitian Creole', 'hu': 'Hungarian', 
    'hy': 'Armenian', 'id': 'Indonesian', 'is': 'Icelandic', 'it': 'Italian', 'ja': 'Japanese', 
    'jw': 'Javanese', 'ka': 'Georgian', 'kk': 'Kazakh', 'km': 'Khmer', 'kn': 'Kannada', 
    'ko': 'Korean', 'la': 'Latin', 'lb': 'Luxembourgish', 'ln': 'Lingala', 'lo': 'Lao', 
    'lt': 'Lithuanian', 'lv': 'Latvian', 'mg': 'Malagasy', 'mi': 'Maori', 'mk': 'Macedonian', 
    'ml': 'Malayalam', 'mn': 'Mongolian', 'mr': 'Marathi', 'ms': 'Malay', 'mt': 'Maltese', 
    'my': 'Burmese', 'ne': 'Nepali', 'nl': 'Dutch', 'nn': 'Norwegian Nynorsk', 'no': 'Norwegian', 
    'oc': 'Occitan', 'pa': 'Punjabi', 'pl': 'Polish', 'ps': 'Pashto', 'pt': 'Portuguese', 
    'ro': 'Romanian', 'ru': 'Russian', 'sa': 'Sanskrit', 'sd': 'Sindhi', 'si': 'Sinhala', 
    'sk': 'Slovak', 'sl': 'Slovenian', 'sn': 'Shona', 'so': 'Somali', 'sq': 'Albanian', 
    'sr': 'Serbian', 'su': 'Sundanese', 'sv': 'Swedish', 'sw': 'Swahili', 'ta': 'Tamil', 
    'te': 'Telugu', 'tg': 'Tajik', 'th': 'Thai', 'tk': 'Turkmen', 'tl': 'Tagalog', 
    'tr': 'Turkish', 'tt': 'Tatar', 'uk': 'Ukrainian', 'ur': 'Urdu', 'uz': 'Uzbek', 
    'vi': 'Vietnamese', 'yi': 'Yiddish', 'yo': 'Yoruba', 'zh': 'Chinese', 'yue': 'Cantonese'
}
```