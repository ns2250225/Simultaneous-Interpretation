from __future__ import annotations

from pathlib import Path
from typing import Dict, Mapping, Optional


def load_dictionary(path: Optional[Path]) -> Dict[str, str]:
    """Load domain specific terminology mappings from ``term=translation`` lines."""

    if path is None:
        return {}

    custom: Dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if "=" not in line:
                continue
            term, translation = line.split("=", 1)
            term = term.strip()
            translation = translation.strip()
            if term:
                custom[term] = translation
    return custom


def preprocess_text(text: str, mapping: Mapping[str, str]) -> str:
    """Replace occurrences of dictionary keys with the mapped translation."""

    if not mapping:
        return text

    processed = text
    for term, translation in mapping.items():
        processed = processed.replace(term, translation)
    return processed
