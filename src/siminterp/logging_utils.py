from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel


@dataclass(slots=True)
class RichLogger:
    """Wrapper around Rich console logging with persistent transcripts."""

    log_file: Path
    console: Console = field(default_factory=Console)
    captured_output: List[str] = field(default_factory=list)

    def log_text(self, message: str) -> None:
        self.console.print(message)
        self.captured_output.append(message)
        self._write_line(message)

    def log_panel(self, message: str, title: str, style: str) -> None:
        panel = Panel(message, border_style=style, title=title)
        self.console.print(panel)
        self._write_line(f"{title}: {message}")

    def log_exception(self, error: Exception) -> None:
        self.log_panel(str(error), "ERROR", "red")
        tb = traceback.format_exc()
        self._write_line(tb)

    def _write_line(self, message: str) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} - {message}\n")

    def build_transcript(self) -> str:
        transcript_lines: List[str] = []
        translation_lines: List[str] = []
        for line in self.captured_output:
            if line.startswith("Translated:"):
                translation_lines.append(line.replace("Translated:", "", 1).strip())
            else:
                transcript_lines.append(line.strip())
        transcript = ["Transcript:"]
        transcript.extend(transcript_lines)
        transcript.append("")
        transcript.append("Translated:")
        transcript.extend(translation_lines)
        return "\n".join(transcript)

    def save_transcript(self, directory: Optional[Path] = None) -> Path:
        if directory is None:
            directory = Path.cwd() / "tmp"
        directory.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("%Y%m%d-%H%M%S.txt")
        destination = directory / filename
        destination.write_text(self.build_transcript(), encoding="utf-8")
        self.log_panel(f"Transcription saved to {destination}", "LOG", "bold green")
        return destination
