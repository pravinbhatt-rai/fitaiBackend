"""
Groq cloud AI client — drop-in replacement for OllamaClient.
Uses llama-3.1-8b-instant for text and llama-3.2-11b-vision-preview for images.
No local model downloads required.
"""

from typing import AsyncGenerator, List, Optional, Union

from groq import AsyncGroq

from utils.config import settings
from utils.logger import get_logger

logger = get_logger("fitai.groq")

_TEXT_MODEL = "llama-3.1-8b-instant"
_VISION_MODEL = "llama-3.2-11b-vision-preview"


class GroqClient:
    def __init__(self) -> None:
        self._client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    async def is_healthy(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False

    async def ensure_models_pulled(self) -> None:
        """No-op for Groq — models are hosted in the cloud."""
        logger.info("Groq client ready — using cloud models (no download needed)")

    def _build_messages(
        self,
        messages: List[dict],
        images: Optional[List[str]],
    ) -> List[dict]:
        """
        Convert messages to Groq format.
        If images are provided, inject the first image into the last user message
        as a multipart content block.
        """
        if not images:
            return messages

        groq_messages = [m.copy() for m in messages]
        image_b64 = images[0]
        data_uri = f"data:image/jpeg;base64,{image_b64}"

        for i in range(len(groq_messages) - 1, -1, -1):
            if groq_messages[i].get("role") == "user":
                text = groq_messages[i].get("content") or ""
                groq_messages[i]["content"] = [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ]
                break

        return groq_messages

    async def chat(
        self,
        model: str,
        messages: List[dict],
        images: Optional[List[str]] = None,
        stream: bool = False,
    ) -> Union[str, AsyncGenerator[str, None]]:
        groq_model = _VISION_MODEL if images else _TEXT_MODEL
        groq_messages = self._build_messages(messages, images)

        if stream:
            async def _gen() -> AsyncGenerator[str, None]:
                resp = await self._client.chat.completions.create(
                    model=groq_model,
                    messages=groq_messages,
                    stream=True,
                    max_tokens=1024,
                    temperature=0.7,
                )
                async for chunk in resp:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content

            return _gen()

        response = await self._client.chat.completions.create(
            model=groq_model,
            messages=groq_messages,
            stream=False,
            max_tokens=1024,
            temperature=0.7,
        )
        return response.choices[0].message.content or ""

    async def close(self) -> None:
        pass  # AsyncGroq manages its own connection pool


groq_client = GroqClient()
