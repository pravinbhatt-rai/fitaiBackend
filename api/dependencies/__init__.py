from fastapi import Request

from services.ollama.client import OllamaClient


def get_ollama(request: Request) -> OllamaClient:
    return request.app.state.ollama
