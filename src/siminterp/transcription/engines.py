from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional, Protocol

from ..config import AppConfig


class Transcriber(Protocol):
    def transcribe_file(self, audio_path: Path, language: str) -> str:
        """Return the recognised text for the audio file."""


class WhisperCppTranscriber:
    def __init__(self, model: str, threads: Optional[int] = None):
        # NOTE: The 'whispercpp' python bindings are currently difficult to install on Windows
        # due to compilation requirements. We are disabling this backend for now.
        # Users should prefer 'faster-whisper'.
        raise RuntimeError(
            "The 'whispercpp' backend is currently unavailable on Windows due to installation issues. "
            "Please use '--transcriber faster-whisper' instead."
        )

    def transcribe_file(self, audio_path: Path, language: str) -> str:
        raise NotImplementedError("whispercpp backend is disabled.")


class FasterWhisperTranscriber:
    def __init__(self, model_size: str, threads: Optional[int] = None, device: str = "auto"):
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        
        # Attempt to add NVIDIA library paths for Windows if installed via pip
        if os.name == "nt":
            try:
                import nvidia.cudnn
                import nvidia.cublas
                
                # Safely get paths, handling potential None or missing attributes
                cudnn_dir = os.path.dirname(nvidia.cudnn.__file__) if hasattr(nvidia.cudnn, '__file__') and nvidia.cudnn.__file__ else None
                cublas_dir = os.path.dirname(nvidia.cublas.__file__) if hasattr(nvidia.cublas, '__file__') and nvidia.cublas.__file__ else None

                libs = []
                if cudnn_dir:
                    libs.append(cudnn_dir)
                    libs.append(os.path.join(cudnn_dir, "bin"))
                
                if cublas_dir:
                    libs.append(cublas_dir)
                    libs.append(os.path.join(cublas_dir, "bin"))

                for lib in libs:
                    if lib and os.path.exists(lib):
                        os.add_dll_directory(lib)
            except (ImportError, AttributeError):
                pass

        from faster_whisper import WhisperModel  # type: ignore

        # Determine device and compute type
        if device == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                else:
                    device = "cpu"
            except ImportError:
                device = "cpu"

        # Fallback for CUDA if no NVIDIA libs found
        if device == "cuda":
            try:
                import torch
                if not torch.cuda.is_available():
                    device = "cpu"
            except ImportError:
                device = "cpu"

        compute_type = "float16" if device == "cuda" else "int8"

        cpu_threads = threads or max(1, (os.cpu_count() or 2) // 2)
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
            num_workers=cpu_threads,
        )

    def transcribe_file(self, audio_path: Path, language: str) -> str:
        segments, _ = self.model.transcribe(
            str(audio_path), 
            language=language,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        return _segments_to_text(segments)


def _segments_to_text(result: Iterable) -> str:
    def extract_text(segment) -> str:
        if isinstance(segment, str):
            return segment
        if isinstance(segment, dict):
            return str(segment.get("text", ""))
        return str(getattr(segment, "text", ""))

    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        segments = result.get("segments", [])
        return "".join(extract_text(segment) for segment in segments)
    if hasattr(result, "__iter__"):
        return "".join(extract_text(segment) for segment in result)
    return str(result)


def create_transcriber(config: AppConfig) -> Transcriber:
    if config.transcriber == "whispercpp":
        return WhisperCppTranscriber(config.whisper_model, config.whisper_threads)
    return FasterWhisperTranscriber(
        config.whisper_model, 
        config.whisper_threads, 
        device=config.whisper_device
    )
