from typing import Protocol

from openai import OpenAI


class LLMProvider(Protocol):
    def call(self, system: str, user_content: str) -> str:
        ...


class OpenAIProvider:
    def __init__(self, api_key: str, model: str, temperature: float = 0.0) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._temperature = temperature

    def call(self, system: str, user_content: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=self._temperature,
        )
        return response.choices[0].message.content or ""
