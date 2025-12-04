from __future__ import annotations

import queue
import threading
import time
import tempfile
from collections import deque
from pathlib import Path
from typing import Deque, Dict, Optional

import speech_recognition as sr

from .config import AppConfig
from .dictionary import preprocess_text
from .logging_utils import RichLogger
from .transcription.engines import Transcriber
from .translation.openai_translator import OpenAITranslator
from .tts.speech import OpenAITTSEngine


class InterpretationPipeline:
    def __init__(
        self,
        config: AppConfig,
        logger: RichLogger,
        transcriber: Transcriber,
        dictionary: Optional[Dict[str, str]] = None,
        translator: Optional[OpenAITranslator] = None,
        tts_engine: Optional[OpenAITTSEngine] = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.transcriber = transcriber
        self.dictionary = dictionary or {}
        self.translator = translator
        self.tts_engine = tts_engine

        self.recognizer = sr.Recognizer()
        self.transcription_queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self.translation_queue: Optional["queue.Queue[Optional[str]]"] = (
            queue.Queue() if translator is not None and config.enable_translation else None
        )
        self.tts_queue: Optional["queue.Queue[Optional[str]]"] = (
            queue.Queue() if tts_engine is not None and config.enable_tts else None
        )
        self.previous_chunks: Deque[str] = deque(maxlen=config.chunk_history)
        self.threads: list[threading.Thread] = []

    def run(self) -> None:
        microphone = sr.Microphone(device_index=self.config.input_device_index)
        with microphone as source:
            self.logger.log_panel(
                f"Adjusting for ambient noise... (Language: {self.config.input_language})",
                "ACTION",
                "blue1",
            )
            self.recognizer.adjust_for_ambient_noise(source, duration=self.config.ambient_duration)

        self._start_workers()
        stop_listening = self.recognizer.listen_in_background(
            sr.Microphone(device_index=self.config.input_device_index),
            self._callback,
            phrase_time_limit=self.config.phrase_time_limit,
        )
        self.logger.log_panel("Start speaking. Press CTRL+C to exit", "ACTION", "green1")

        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.logger.log_panel("Stopping listening...", "ACTION", "magenta3")
        finally:
            stop_listening(wait_for_stop=False)
            self._shutdown_workers()
            self.logger.save_transcript()

    def _start_workers(self) -> None:
        transcription_thread = threading.Thread(target=self._transcription_worker, daemon=True)
        transcription_thread.start()
        self.threads.append(transcription_thread)

        if self.translation_queue is not None and self.translator:
            translation_thread = threading.Thread(target=self._translation_worker, daemon=True)
            translation_thread.start()
            self.threads.append(translation_thread)

        if self.tts_queue is not None and self.tts_engine:
            tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
            tts_thread.start()
            self.threads.append(tts_thread)

    def _shutdown_workers(self) -> None:
        self.transcription_queue.put(None)
        if self.translation_queue is not None:
            self.translation_queue.put(None)
        if self.tts_queue is not None:
            self.tts_queue.put(None)
        for thread in self.threads:
            thread.join()

    def _callback(self, recognizer: sr.Recognizer, audio: sr.AudioData) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as buffer:
            buffer.write(audio.get_wav_data())
            temp_path = Path(buffer.name)

        try:
            text = self.transcriber.transcribe_file(temp_path, self.config.input_language)
            text = preprocess_text(text, self.dictionary)
            cleaned = text.strip()
            if cleaned:
                self.transcription_queue.put(cleaned)
        except Exception as error:  # pragma: no cover - runtime safety
            self.logger.log_exception(error)
        finally:
            temp_path.unlink(missing_ok=True)

    def _transcription_worker(self) -> None:
        while True:
            text = self.transcription_queue.get()
            if text is None:
                self.transcription_queue.task_done()
                break
            self.logger.log_text(text)
            if self.translation_queue is not None:
                self.translation_queue.put(text)
            self.transcription_queue.task_done()

    def _translation_worker(self) -> None:
        assert self.translation_queue is not None
        assert self.translator is not None
        while True:
            text = self.translation_queue.get()
            if text is None:
                self.translation_queue.task_done()
                break
            try:
                translated = self.translator.translate(
                    sentence=text,
                    target_language=self.config.translation_language,
                    previous_chunks=self.previous_chunks,
                    topic=self.config.topic,
                )
                message = f"Translated: {translated}"
                self.logger.log_text(message)
                self.previous_chunks.append(translated)
                if self.tts_queue is not None:
                    self.tts_queue.put(translated)
            except Exception as error:  # pragma: no cover - runtime safety
                self.logger.log_exception(error)
            finally:
                self.translation_queue.task_done()

    def _tts_worker(self) -> None:
        assert self.tts_queue is not None
        assert self.tts_engine is not None
        while True:
            text = self.tts_queue.get()
            if text is None:
                self.tts_queue.task_done()
                break
            try:
                self.tts_engine.speak(text, self.config.output_device_index)
            except Exception as error:  # pragma: no cover - runtime safety
                self.logger.log_exception(error)
            finally:
                self.tts_queue.task_done()
