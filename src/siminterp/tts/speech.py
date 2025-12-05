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
                # Accumulate audio to handle potential stream issues or resampling if needed
                # However, for true streaming, we should write chunk by chunk.
                # If invalid sample rate happens, we can't easily resample a stream on the fly without a buffer or complex logic.
                # For simplicity and robustness against -9997, we will buffer the whole sentence for OpenAI if stream fails?
                # Actually, the error happens at audio_interface.open(), BEFORE we write data.
                
                for chunk in response.iter_bytes(chunk_size=1024):
                    if stream:
                         stream.write(chunk)
        except OSError as e:
             # Handle "Invalid sample rate" error (Errno -9997) or -9999 by buffering and resampling
             # This block catches errors from audio_interface.open() if it was outside the loop?
             # No, open() is inside the try block.
             # If open() fails, we are here.
             
             if e.errno == -9997 or e.errno == -9999 or "Invalid sample rate" in str(e) or "Unanticipated host error" in str(e):
                 # We need to re-request or buffer the audio, then resample.
                 # Since we are already inside the "with client..." block or passed it? 
                 # Actually, if open() failed, we haven't started streaming from OpenAI effectively or we can restart it.
                 # But we can't easily restart the generator.
                 # Strategy: Since OpenAI TTS is fast, let's just use the non-streaming API or buffer it all if we detect this error?
                 # Or better: Resample logic requires numpy.
                 
                 # Let's fallback to a safe implementation that downloads the whole audio, resamples, and plays.
                 # We need to recreate the request because the previous response stream is consumed or we are in exception.
                 
                 fallback_rate = 48000
                 
                 # Re-create request to get full content (not streaming this time for simplicity in resampling)
                 # Note: response_format='pcm' gives raw 24kHz.
                 response = self.client.audio.speech.create(
                    model=self.model,
                    voice=self.voice,
                    input=text,
                    response_format="pcm",
                    speed=self.speed,
                 )
                 # This returns binary content directly
                 audio_data = response.content
                 
                 import numpy as np
                 wav_np = np.frombuffer(audio_data, dtype=np.int16)
                 
                 # Resample 24000 -> 48000
                 sample_rate = 24000
                 duration_s = len(wav_np) / sample_rate
                 new_num_samples = int(duration_s * fallback_rate)
                 
                 x_old = np.linspace(0, duration_s, len(wav_np))
                 x_new = np.linspace(0, duration_s, new_num_samples)
                 
                 wav_resampled = np.interp(x_new, x_old, wav_np)
                 wav_int16 = wav_resampled.astype(np.int16)
                 audio_data_resampled = wav_int16.tobytes()
                 
                 try:
                    stream = audio_interface.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=fallback_rate,
                        output=True,
                        output_device_index=output_device_index,
                    )
                 except OSError:
                     if output_device_index is not None:
                         stream = audio_interface.open(
                             format=pyaudio.paInt16,
                             channels=1,
                             rate=fallback_rate,
                             output=True,
                             output_device_index=None,
                         )
                     else:
                         raise
                 
                 stream.write(audio_data_resampled)
             else:
                 raise
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
            try:
                stream = audio_interface.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=sample_rate,
                    output=True,
                    output_device_index=output_device_index,
                )
                stream.write(audio_data)
            except OSError as e:
                # Handle "Invalid sample rate" error (Errno -9997) by resampling
                # Also handle -9999 "Unanticipated host error" which often happens with invalid sample rates on WASAPI
                if e.errno == -9997 or e.errno == -9999 or "Invalid sample rate" in str(e) or "Unanticipated host error" in str(e):
                    # Fallback to 48000Hz which is widely supported
                    fallback_rate = 48000
                    # If original was already 48000, try 44100
                    if sample_rate == fallback_rate:
                        fallback_rate = 44100
                    
                    # Resample using numpy linear interpolation
                    duration_s = len(wav_np) / sample_rate
                    new_num_samples = int(duration_s * fallback_rate)
                    
                    x_old = np.linspace(0, duration_s, len(wav_np))
                    x_new = np.linspace(0, duration_s, new_num_samples)
                    
                    wav_resampled = np.interp(x_new, x_old, wav_np)
                    wav_int16 = (wav_resampled * 32767).astype(np.int16)
                    audio_data = wav_int16.tobytes()
                    
                    try:
                        stream = audio_interface.open(
                            format=pyaudio.paInt16,
                            channels=1,
                            rate=fallback_rate,
                            output=True,
                            output_device_index=output_device_index,
                        )
                    except OSError:
                        # If still fails (possibly due to device index), try default device
                        if output_device_index is not None:
                            stream = audio_interface.open(
                                format=pyaudio.paInt16,
                                channels=1,
                                rate=fallback_rate,
                                output=True,
                                output_device_index=None,
                            )
                        else:
                            raise
                    stream.write(audio_data)
                else:
                    raise
        except Exception:
            raise
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            audio_interface.terminate()

class EdgeTTSEngine:
    """Microsoft Edge TTS engine."""

    def __init__(self, voice: str = "en-US-AriaNeural", speed: float = 1.0) -> None:
        self.voice = voice
        self.speed = speed

    def speak(self, text: str, output_device_index: Optional[int]) -> None:
        if not text:
            return

        try:
            import edge_tts
            import miniaudio
            import asyncio
        except ImportError as exc:
            raise RuntimeError(
                "edge-tts or miniaudio package not installed. Install them with 'pip install edge-tts miniaudio'."
            ) from exc

        # Calculate rate string
        rate_val = int((self.speed - 1.0) * 100)
        sign = "+" if rate_val >= 0 else ""
        rate_str = f"{sign}{rate_val}%"

        async def _generate_audio():
            communicate = edge_tts.Communicate(text, self.voice, rate=rate_str)
            mp3_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_data += chunk["data"]
            return mp3_data

        mp3_data = None
        import time
        # Retry up to 3 times for network resilience
        for attempt in range(3):
            try:
                mp3_data = asyncio.run(_generate_audio())
                if mp3_data:
                    break
            except Exception as e:
                # Log or print error if needed, but we are inside a worker usually.
                # If it's the last attempt, re-raise.
                if attempt == 2:
                    raise
                # Wait briefly before retrying
                time.sleep(1.0)

        if not mp3_data:
            return

        # Decode MP3 to PCM
        try:
            decoded = miniaudio.decode(
                mp3_data, 
                nchannels=1, 
                sample_rate=24000, 
                output_format=miniaudio.SampleFormat.SIGNED16
            )
        except Exception:
            raise

        audio_interface = pyaudio.PyAudio()
        stream = None
        try:
            try:
                stream = audio_interface.open(
                    format=pyaudio.paInt16,
                    channels=decoded.nchannels,
                    rate=decoded.sample_rate,
                    output=True,
                    output_device_index=output_device_index,
                )
                # Ensure data is bytes, decoded.samples might be memoryview or array
                audio_data = decoded.samples
                if hasattr(audio_data, "tobytes"):
                     audio_data = audio_data.tobytes()
                stream.write(audio_data)
            except OSError as e:
                 # Handle "Invalid sample rate" error (Errno -9997) or "Unanticipated host error" (-9999) by resampling
                if e.errno == -9997 or e.errno == -9999 or "Invalid sample rate" in str(e) or "Unanticipated host error" in str(e):
                    # Fallback to 48000Hz
                    fallback_rate = 48000
                    sample_rate = decoded.sample_rate
                    if sample_rate == fallback_rate:
                        fallback_rate = 44100
                    
                    # Get audio data as numpy array for resampling
                    import numpy as np
                    audio_data_bytes = decoded.samples
                    if hasattr(audio_data_bytes, "tobytes"):
                        audio_data_bytes = audio_data_bytes.tobytes()
                    
                    # Convert bytes back to numpy int16
                    wav_np = np.frombuffer(audio_data_bytes, dtype=np.int16)
                    
                    # Resample
                    duration_s = len(wav_np) / sample_rate
                    new_num_samples = int(duration_s * fallback_rate)
                    
                    x_old = np.linspace(0, duration_s, len(wav_np))
                    x_new = np.linspace(0, duration_s, new_num_samples)
                    
                    wav_resampled = np.interp(x_new, x_old, wav_np)
                    wav_int16 = wav_resampled.astype(np.int16)
                    audio_data_resampled = wav_int16.tobytes()
                    
                    try:
                        stream = audio_interface.open(
                            format=pyaudio.paInt16,
                            channels=decoded.nchannels,
                            rate=fallback_rate,
                            output=True,
                            output_device_index=output_device_index,
                        )
                    except OSError:
                         # If still fails (possibly due to device index), try default device
                        if output_device_index is not None:
                            stream = audio_interface.open(
                                format=pyaudio.paInt16,
                                channels=decoded.nchannels,
                                rate=fallback_rate,
                                output=True,
                                output_device_index=None,
                            )
                        else:
                            raise
                    stream.write(audio_data_resampled)
                else:
                    raise
        except Exception:
            raise
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            audio_interface.terminate()
