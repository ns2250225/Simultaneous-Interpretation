from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from openai import OpenAI

from ..openai_models import RESPONSES_ONLY_MODELS


@dataclass(slots=True)
class OpenAITranslator:
    client: OpenAI
    model: str
    temperature: float = 0.0

    def translate(self, sentence: str, target_language: str, previous_chunks: Sequence[str], topic: str) -> str:
        user_prompt = self._build_prompt(sentence, target_language, previous_chunks, topic)
        if self.model in RESPONSES_ONLY_MODELS:
            return self._translate_with_responses(user_prompt)
        return self._translate_with_chat_completions(user_prompt)

    def _build_prompt(
        self, sentence: str, target_language: str, previous_chunks: Sequence[str], topic: str
    ) -> str:
        previous_context = "\n".join(chunk for chunk in previous_chunks if chunk).strip()
        if not previous_context:
            previous_context = "None"
        topic_line = topic or "General conversation"
        return (
            "Translate the following sentence into {language}. "
            "You must output ONLY the translation. Do not include any notes, explanations, or the original text.\n\n"
            "Sentence: {sentence}\n"
            "Previous Chunks: {previous}\n"
            "Topic: {topic}"
        ).format(language=target_language, sentence=sentence, previous=previous_context, topic=topic_line)

    def _translate_with_chat_completions(self, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional simultaneous interpreter. "
                        "Focus on faithful, natural-sounding translations and maintain tone. "
                        "Output ONLY the translation."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()

    def _translate_with_responses(self, user_prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You are a professional simultaneous interpreter. "
                                "Focus on faithful, natural-sounding translations and maintain tone. "
                                "Output ONLY the translation."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": user_prompt,
                        }
                    ],
                },
            ],
        )
        return self._extract_response_text(response)

    def _extract_response_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        data: Any
        if hasattr(response, "model_dump"):
            data = response.model_dump()
        elif hasattr(response, "to_dict"):
            data = response.to_dict()
        else:
            data = response

        if isinstance(data, dict):
            collected: list[str] = []
            output_items = data.get("output")
            if isinstance(output_items, list):
                for item in output_items:
                    collected.extend(self._collect_text_blocks(item.get("content")))

            if not collected and "choices" in data:
                for choice in data.get("choices", []):
                    if isinstance(choice, dict):
                        message = choice.get("message")
                        if isinstance(message, dict):
                            text = message.get("content")
                            if isinstance(text, str) and text.strip():
                                collected.append(text.strip())

            if collected:
                return "\n".join(part.strip() for part in collected if part).strip()

        raise ValueError("No text content returned from OpenAI response.")

    @staticmethod
    def _collect_text_blocks(content: Any) -> list[str]:
        if content is None:
            return []
        if isinstance(content, str):
            return [content]
        if isinstance(content, dict):
            texts: list[str] = []
            if "text" in content and isinstance(content["text"], str):
                texts.append(content["text"])
            if "content" in content:
                texts.extend(OpenAITranslator._collect_text_blocks(content["content"]))
            return texts
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                texts.extend(OpenAITranslator._collect_text_blocks(item))
            return texts
        return []
