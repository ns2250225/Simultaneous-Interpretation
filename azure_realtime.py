import azure.cognitiveservices.speech as speechsdk
import time
import re
import os
from xml.sax.saxutils import escape

def start_voice_interpreter():
    speech_key = os.getenv("AZURE_SPEECH_KEY")
    service_region = os.getenv("AZURE_SERVICE_REGION")
    if not speech_key or not service_region:
        print("缺少 AZURE_SPEECH_KEY 或 AZURE_SERVICE_REGION 环境变量")
        return

    # 1. 翻译配置
    translation_config = speechsdk.translation.SpeechTranslationConfig(
        subscription=speech_key, region=service_region)
    translation_config.add_target_language("zh-Hans")
    translation_config.add_target_language("en")

    # 2. 自动语言检测配置
    # === 关键修改：把 en-US 放在第一位，增加英文识别权重 ===
    auto_detect_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
        languages=["en-US", "zh-CN"] 
    )

    # 3. 语音合成配置
    tts_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=tts_config)

    # 4. 识别器
    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
    recognizer = speechsdk.translation.TranslationRecognizer(
        translation_config=translation_config,
        audio_config=audio_config,
        auto_detect_source_language_config=auto_detect_config
    )

    # 【新增补丁】强制设置为“连续识别”模式
    # 告诉 Azure：每一句话都要重新猜语言，不要依赖惯性！
    recognizer.properties.set_property(
        property_id=speechsdk.PropertyId.SpeechServiceConnection_LanguageIdMode, 
        value='Continuous'
    )
    
    # === 播放函数 ===
    def play_translation(text, language_code):
        voice_map = {
            "en": "en-US-AvaNeural",
            "zh-Hans": "zh-CN-XiaoxiaoNeural"
        }
        voice_name = voice_map.get(language_code, "en-US-AvaNeural")
        ssml_string = f"""
        <speak version='1.0' xml:lang='{language_code}'>
            <voice name='{voice_name}'>{escape(text)}</voice>
        </speak>
        """
        speech_synthesizer.speak_ssml_async(ssml_string)

    # === 结果处理回调 ===
    def result_callback(evt):
        if evt.result.reason == speechsdk.ResultReason.TranslatedSpeech:
            src_lang = evt.result.properties.get(
                speechsdk.PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult
            )
            text = evt.result.text
            
            # 判断文本是否纯英文
            is_english_text = bool(re.search(r"[a-zA-Z]", text)) and not bool(re.search(r"[\u4e00-\u9fa5]", text))

            print(f"\n[Azure判断]: {src_lang} | [实际文本]: {text}")

            # --- 场景 1: Azure 识别正确 (说是英文，也是英文) ---
            if "en" in src_lang:
                target_lang = "zh-Hans"
                trans_text = evt.result.translations.get(target_lang, "")
                print(f"[翻译成功]: {trans_text}")
                play_translation(trans_text, target_lang)

            # --- 场景 2: Azure 识别正确 (说是中文，也是中文) ---
            elif "zh" in src_lang and not is_english_text:
                target_lang = "en"
                trans_text = evt.result.translations.get(target_lang, "")
                print(f"[翻译成功]: {trans_text}")
                play_translation(trans_text, target_lang)

            # --- 场景 3: Azure 误判 (说是中文，但实际是英文) ---
            # 这就是你遇到的情况：Azure以为是中文，所以没进行"英->中"翻译
            elif "zh" in src_lang and is_english_text:
                print(">> [系统警告]: 检测到英文，但Azure处于中文模式，导致未翻译。")
                print(">> [建议]: 请尝试说一个更长的英文句子，或者停顿一下再说。")
                # 这里我们不播放，避免播放出英文原文导致混淆
            
            else:
                print(">> [忽略]: 无法确定的语言状态。")

    recognizer.recognized.connect(result_callback)
    
    # 开始
    print("--------------------------------------------------")
    print("系统已启动。优先识别英文模式。")
    print("提示：如果切换语言失败，请尝试说长一点的句子。")
    print("--------------------------------------------------")
    recognizer.start_continuous_recognition()

    try:
        while True: time.sleep(0.5)
    except KeyboardInterrupt:
        recognizer.stop_continuous_recognition()

if __name__ == "__main__":
    start_voice_interpreter()

# 支持的翻译目标语种有：
# "语种","代码 (必填)","备注"
# "简体中文","zh-Hans","注意不是 zh-CN (这是源语言/TTS用的，翻译目标必须用 Hans)"
# "繁体中文","zh-Hant",""
# "英语","en","通用英语"
# "日语","ja",""
# "韩语","ko",""
# "法语","fr",""
# "德语","de",""
# "西班牙语","es",""
# "意大利语","it",""
# "俄语","ru",""
# "葡萄牙语","pt",""
# "泰语","th",""
# "越南语","vi",""
# "印尼语","id",""
# "阿拉伯语","ar",""

# ================================

# 支持的检测语种有：（主要一般最多只放10种检测语种，不然影响识别率）
# 🇨🇳 中文系列
# 语言名称	代码 (Locale ID)	备注
# 中文 (普通话 - 简体)	zh-CN	最常用
# 中文 (普通话 - 繁体/台湾)	zh-TW	
# 中文 (粤语 - 简体)	yue-CN	广东话识别
# 中文 (香港粤语)	zh-HK	
# 中文 (吴语/上海话)	wuu-CN	部分区域支持
# 中文 (四川话)	zh-CN-sichuan	部分区域支持
# 🇺🇸 英语系列
# 语言名称	代码	备注
# 英语 (美国)	en-US	最通用
# 英语 (英国)	en-GB	
# 英语 (澳大利亚)	en-AU	
# 英语 (印度)	en-IN	
# 英语 (加拿大)	en-CA	
# 🌏 亚洲其他
# 语言名称	代码
# 日语	ja-JP
# 韩语	ko-KR
# 泰语	th-TH
# 越南语	vi-VN
# 印尼语	id-ID
# 印度语 (印地语)	hi-IN
# 🌍 欧洲
# 语言名称	代码
# 法语 (法国)	fr-FR
# 德语 (德国)	de-DE
# 西班牙语 (西班牙)	es-ES
# 意大利语	it-IT
# 俄语	ru-RU
# 葡萄牙语 (巴西)	pt-BR