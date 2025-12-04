# 基于openai的实时同声传译应用

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

启动同声传译会话（示例：将中文翻译成英文，播放合成语音，并使用 faster-whisper 模型）：
```bash
python -m src.siminterp --input-language zh --target-language en --input-device 1 --output-device 3 --translate --tts --voice alloy --transcriber faster-whisper --whisper-model base
```
按 `CTRL+C` 停止。应用程序将优雅地关闭后台工作线程，并将带时间戳的转录文本保存到您的“tmp”文件夹中。

### 支持的whisper模型（一般选large-v3最好）
```
large-v3
large-v2
medium
tiny
base
small
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