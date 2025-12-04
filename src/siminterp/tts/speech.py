from __future__ import annotations

from typing import Optional, Protocol

import pyaudio
from openai import OpenAI


class TTSEngineProtocol(Protocol):
    def speak(self, text: str, output_device_index: Optional[int]) -> None: ...

class OpenAITTSEngine:
    """Stream OpenAI text-to-speech audio through PyAudio."""

    def __init__(self, client: OpenAI, model: str, voice: str, speed: float) -> None:
        self.client = client
        self.model = model
        self.voice = voice
        self.speed = speed

    def speak(self, text: str, output_device_index: Optional[int]) -> None:
        if not text:
            return

        audio_interface = pyaudio.PyAudio()
        stream = None
        try:
            try:
                stream = audio_interface.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=24000,
                    output=True,
                    output_device_index=output_device_index,
                )
            except OSError as e:
                if e.errno == -9999 or "Unanticipated host error" in str(e):
                    # Retry once with default device if specified device fails with host error
                    if output_device_index is not None:
                        stream = audio_interface.open(
                            format=pyaudio.paInt16,
                            channels=1,
                            rate=24000,
                            output=True,
                            output_device_index=None,
                        )
                    else:
                        raise
                else:
                    raise

            with self.client.audio.speech.with_streaming_response.create(
                model=self.model,
                voice=self.voice,
                input=text,
                response_format="pcm",
                speed=self.speed,
            ) as response:
                for chunk in response.iter_bytes(chunk_size=1024):
                    stream.write(chunk)
        except Exception:
            # Re-raise other exceptions to be logged by the worker
            raise
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            audio_interface.terminate()

class CoquiTTSEngine:
    """Local TTS using Coqui TTS."""
    
    def __init__(self, model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2", speaker: Optional[str] = None, speed: float = 1.0):
        try:
            from TTS.api import TTS
        except ImportError as exc:
            raise RuntimeError(
                "Coqui TTS package not installed. Install it with 'pip install TTS'."
            ) from exc
            
        # Check for GPU availability
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self.tts = TTS(model_name).to(device)
        self.speaker = speaker
        self.speed = speed
        self.model_name = model_name
        
        # Default speakers for multi-speaker models if none provided
        if not self.speaker and self.tts.is_multi_speaker:
            # Try to find a reasonable default or let TTS handle it (it usually requires one)
            # For XTTS v2, we might need a speaker wav or name.
            # Let's grab the first one if available
            if hasattr(self.tts.tts, 'speaker_manager') and self.tts.tts.speaker_manager:
                 speakers = list(self.tts.tts.speaker_manager.speakers.keys())
                 if speakers:
                     self.speaker = speakers[0]
            # Fallback: if speaker is still None but model needs it, 
            # we might need to provide a reference wav for XTTS if it's not in speaker_manager.
            # However, XTTS usually comes with some default speakers.
            # If self.speaker is still None, we might fail later.

    def speak(self, text: str, output_device_index: Optional[int]) -> None:
        if not text:
            return
            
        # Coqui TTS generation (returns raw wav data usually, or we save to file/stream)
        # For low latency, we want streaming, but standard Coqui API is often file-based or full-gen.
        # We will use the standard generation and play it via PyAudio.
        
        # Since Coqui outputs varying sample rates depending on the model, we need to check.
        # XTTS v2 is usually 24000Hz.
        
        # Note: Coqui's python API 'tts_to_file' saves to file. 'tts' returns waveform.
        
        # Handle language argument dynamically if needed. 
        # If model is multilingual, language is required. If monolingual, it should be None.
        language = None
        if self.tts.is_multi_lingual:
            language = "en"

        # For XTTS, if no speaker is set, we often need to provide a reference audio file path (speaker_wav).
        # But the simple API `tts()` usually handles speaker names if they are in the model.
        # If we are here and self.speaker is None, and it's XTTS, we might be in trouble unless we use speaker_wav.
        # Let's assume for now we found a speaker name or the user provided one.
        
        kwargs = {}
        if self.speaker:
            kwargs['speaker'] = self.speaker
        
        # If it's XTTS and we still have no speaker, we MUST provide one.
        # Many XTTS models have 'Ana Florence' or similar as defaults in their config but need it passed.
        if not self.speaker and "xtts" in self.model_name.lower():
             # Hard fallback: Try to use 'Ana Florence' which is common in XTTS v2
             kwargs['speaker'] = "Ana Florence"

        if self.tts.is_multi_lingual and language:
            kwargs['language'] = language

        wav = self.tts.tts(text=text, **kwargs) 
        # NOTE: Language handling might need to be dynamic based on target language config, 
        # but Coqui's XTTS often infers or needs explicit lang. 
        # For now we assume English or rely on model defaults. 
        # XTTS requires language arg.
        
        import numpy as np
        
        # Convert to int16 for PyAudio
        # Coqui output is usually float32 in [-1, 1] list or numpy array
        wav_np = np.array(wav)
        wav_int16 = (wav_np * 32767).astype(np.int16)
        audio_data = wav_int16.tobytes()
        
        sample_rate = self.tts.synthesizer.output_sample_rate

        audio_interface = pyaudio.PyAudio()
        stream = None
        try:
            stream = audio_interface.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                output=True,
                output_device_index=output_device_index,
            )
            stream.write(audio_data)
        except Exception:
            raise
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            audio_interface.terminate()
