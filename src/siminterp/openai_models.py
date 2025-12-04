"""Canonical OpenAI model identifiers used by the CLI."""

from __future__ import annotations

from typing import Tuple

# Translation/chat models that are known to work well with the interpreter pipeline.
TRANSLATION_MODELS: Tuple[str, ...] = (
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-4o",
    "gpt-4o-mini",
    "deepseek-chat",
    "deepseek-reasoner",
)

# Default translation model keeps compatibility with previous releases while
# allowing users to upgrade explicitly.
DEFAULT_TRANSLATION_MODEL = "gpt-4o"

# Models that require the Responses API instead of the legacy Chat Completions endpoint.
RESPONSES_ONLY_MODELS = frozenset({
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
})

# Latest text-to-speech models available from OpenAI.
TTS_MODELS: Tuple[str, ...] = (
    "tts-1",
    "tts-1-hd",
    "gpt-4o-mini-tts",
    "gpt-4.1-tts",
    "gpt-4.1-mini-tts",
)

DEFAULT_TTS_MODEL = "tts-1"
