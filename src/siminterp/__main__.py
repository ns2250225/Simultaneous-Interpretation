from __future__ import annotations

from openai import OpenAI
from rich.console import Console

from .audio.devices import print_devices
from .cli import parse_args
from .config import AppConfig, build_config
from .dictionary import load_dictionary
from .logging_utils import RichLogger
from .pipeline import InterpretationPipeline
from .transcription.engines import create_transcriber
from .translation.openai_translator import OpenAITranslator
from .tts.speech import OpenAITTSEngine


def build_translator(config: AppConfig, client: OpenAI) -> OpenAITranslator | None:
    if not config.enable_translation:
        return None
    return OpenAITranslator(client=client, model=config.openai_model, temperature=config.translation_temperature)


def build_tts_engine(config: AppConfig, client: OpenAI) -> OpenAITTSEngine | None:
    if not config.enable_tts:
        return None
    return OpenAITTSEngine(client=client, model=config.tts_model, voice=config.tts_voice, speed=config.tts_speed)


def main() -> None:
    args = parse_args()

    if args.list_devices:
        console = Console()
        print_devices(console)
        return

    config = build_config(args)
    logger = RichLogger(log_file=config.log_file)

    dictionary = load_dictionary(config.dictionary_path)
    if dictionary:
        logger.log_panel(
            f"Loaded {len(dictionary)} custom terms from {config.dictionary_path}",
            "INFO",
            "cyan",
        )

    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    transcriber = create_transcriber(config)
    translator = build_translator(config, client)
    tts_engine = build_tts_engine(config, client)

    if config.enable_translation and translator is None:
        logger.log_panel("Translation disabled because no translator could be created.", "WARN", "yellow")
    if config.enable_tts and tts_engine is None:
        logger.log_panel("TTS disabled because no engine could be created.", "WARN", "yellow")

    pipeline = InterpretationPipeline(
        config=config,
        logger=logger,
        transcriber=transcriber,
        dictionary=dictionary,
        translator=translator,
        tts_engine=tts_engine,
    )
    pipeline.run()


if __name__ == "__main__":
    main()
