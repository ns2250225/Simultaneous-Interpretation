from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import pyaudio
from rich.console import Console


@dataclass(slots=True)
class AudioDevice:
    index: int
    name: str
    channels: int


def enumerate_devices() -> Tuple[List[AudioDevice], List[AudioDevice]]:
    audio = pyaudio.PyAudio()
    input_devices: List[AudioDevice] = []
    output_devices: List[AudioDevice] = []
    try:
        for idx in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(idx)
            max_input = int(info.get("maxInputChannels", 0))
            max_output = int(info.get("maxOutputChannels", 0))
            name = str(info.get("name", f"Device {idx}"))
            if max_input > 0:
                input_devices.append(AudioDevice(idx, name, max_input))
            if max_output > 0:
                output_devices.append(AudioDevice(idx, name, max_output))
    finally:
        audio.terminate()
    return input_devices, output_devices


def print_devices(console: Console) -> None:
    inputs, outputs = enumerate_devices()
    console.print("#### INPUT DEVICES")
    for device in inputs:
        console.print(f"{device.index}: {device.name} (channels: {device.channels})")
    console.print("\n#### OUTPUT DEVICES")
    for device in outputs:
        console.print(f"{device.index}: {device.name} (channels: {device.channels})")
