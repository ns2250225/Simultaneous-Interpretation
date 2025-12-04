from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .openai_models import DEFAULT_TTS_MODEL, DEFAULT_TRANSLATION_MODEL


@dataclass(slots=True)
class AppConfig:
    """Container for user configurable runtime options."""

    api_key: str
    base_url: Optional[str]
    input_device_index: Optional[int]

    output_device_index: Optional[int]
    input_language: str
    translation_language: str
    enable_translation: bool
    enable_tts: bool
    dictionary_path: Optional[Path]
    topic: str
    openai_model: str
    tts_voice: str
    tts_provider: str
    tts_model: str
    transcriber: str
    whisper_model: str
    whisper_threads: Optional[int]
    whisper_device: str
    chunk_history: int
    phrase_time_limit: int
    pause_threshold: float
    ambient_duration: float
    tts_speed: float
    log_file: Path
    translation_temperature: float


def load_environment() -> None:
    """Load environment variables from .env files if present."""

    load_dotenv(override=False)


def build_config(args) -> AppConfig:
    """Create an :class:`AppConfig` instance from parsed CLI arguments."""

    load_environment()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable not set. Configure it in your environment or .env file."
        )

    base_url = getattr(args, "base_url", None) or os.getenv("OPENAI_BASE_URL")

    dictionary_path: Optional[Path] = None
    if getattr(args, "dictionary", None):
        dictionary_path = Path(args.dictionary).expanduser()
        if not dictionary_path.exists():
            raise FileNotFoundError(f"Dictionary file not found: {dictionary_path}")

    log_file = Path(getattr(args, "log_file", "logfile.txt")).expanduser()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    whisper_threads = getattr(args, "whisper_threads", None)
    if whisper_threads is not None and whisper_threads <= 0:
        raise ValueError("--whisper-threads must be a positive integer if provided")

    chunk_history = max(1, getattr(args, "history", 10))

    # Priority: CLI args > Environment variables > Default values
    openai_model = (
        getattr(args, "model", None)
        or os.getenv("OPENAI_TRANSLATION_MODEL")
        or DEFAULT_TRANSLATION_MODEL
    )
    tts_model = (
        getattr(args, "tts_model", None)
        or os.getenv("OPENAI_TTS_MODEL")
        or DEFAULT_TTS_MODEL
    )

    return AppConfig(
        api_key=api_key,
        base_url=base_url,
        input_device_index=getattr(args, "input_device", None),
        output_device_index=getattr(args, "output_device", None),
        input_language=getattr(args, "input_language", "en"),
        translation_language=getattr(args, "target_language", "fr"),
        enable_translation=bool(getattr(args, "translate", False)),
        enable_tts=bool(getattr(args, "tts", False)),
        dictionary_path=dictionary_path,
        topic=getattr(args, "topic", ""),
        openai_model=openai_model,
        tts_voice=getattr(args, "voice", "alloy"),
        tts_provider=getattr(args, "tts_provider", "openai"),
        tts_model=tts_model,
        transcriber=getattr(args, "transcriber", "faster-whisper"),
        whisper_model=getattr(args, "whisper_model", "base.en"),
        whisper_threads=whisper_threads,
        whisper_device=getattr(args, "whisper_device", "auto"),
        chunk_history=chunk_history,
        phrase_time_limit=max(1, int(getattr(args, "phrase_time_limit", 8))),
        pause_threshold=max(0.1, float(getattr(args, "pause_threshold", 0.8))),
        ambient_duration=max(0.0, float(getattr(args, "ambient_duration", 2.0))),
        tts_speed=max(0.25, float(getattr(args, "tts_speed", 1.0))),
        log_file=log_file,
        translation_temperature=float(getattr(args, "temperature", 0.0)),
    )
