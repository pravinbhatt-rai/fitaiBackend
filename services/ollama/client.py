import json
from typing import AsyncGenerator, List, Optional, Union

import httpx

from utils.config import settings
from utils.logger import get_logger

logger = get_logger("fitai.ollama")


class OllamaClient:
    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=None, write=60.0, pool=30.0)
        )

    async def is_healthy(self) -> bool:
        try:
            resp = await self._client.get(f"{self.base_url}/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def _list_local_models(self) -> List[str]:
        try:
            resp = await self._client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"].split(":")[0] for m in data.get("models", [])]
        except Exception:
            return []

    async def _pull_model(self, model: str) -> None:
        logger.info(f"Pulling model '{model}' — this may take several minutes")
        async with self._client.stream(
            "POST",
            f"{self.base_url}/api/pull",
            json={"name": model, "stream": True},
        ) as resp:
            resp.raise_for_status()
            async for raw in resp.aiter_lines():
                if not raw:
                    continue
                try:
                    chunk = json.loads(raw)
                    status = chunk.get("status", "")
                    completed = chunk.get("completed")
                    total = chunk.get("total")
                    if completed is not None and total and total > 0:
                        pct = completed / total * 100
                        logger.info(f"  {model}: {status} {pct:.1f}%")
                    elif status:
                        logger.info(f"  {model}: {status}")
                except json.JSONDecodeError:
                    pass
        logger.info(f"Model '{model}' ready")

    async def ensure_models_pulled(self) -> None:
        required = ["llama3", "llava"]
        available = await self._list_local_models()
        for model in required:
            if model in available:
                logger.info(f"Model '{model}' already available")
            else:
                try:
                    await self._pull_model(model)
                except Exception as exc:
                    logger.error(f"Failed to pull model '{model}': {exc}")

    async def generate(
        self,
        model: str,
        prompt: str,
        stream: bool = False,
    ) -> Union[str, AsyncGenerator[str, None]]:
        payload = {"model": model, "prompt": prompt, "stream": stream}

        if stream:
            async def _gen() -> AsyncGenerator[str, None]:
                async with self._client.stream(
                    "POST", f"{self.base_url}/api/generate", json=payload
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if text := data.get("response"):
                                yield text
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue

            return _gen()

        resp = await self._client.post(
            f"{self.base_url}/api/generate",
            json={**payload, "stream": False},
        )
        resp.raise_for_status()
        return resp.json()["response"]

    async def chat(
        self,
        model: str,
        messages: List[dict],
        images: Optional[List[str]] = None,
        stream: bool = False,
    ) -> Union[str, AsyncGenerator[str, None]]:
        msgs = [m.copy() for m in messages]
        if images:
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i].get("role") == "user":
                    msgs[i]["images"] = images
                    break

        payload = {"model": model, "messages": msgs, "stream": stream}

        if stream:
            async def _gen() -> AsyncGenerator[str, None]:
                async with self._client.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if text := data.get("message", {}).get("content"):
                                yield text
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue

            return _gen()

        resp = await self._client.post(
            f"{self.base_url}/api/chat",
            json={**payload, "stream": False},
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    async def close(self) -> None:
        await self._client.aclose()


ollama_client = OllamaClient()
