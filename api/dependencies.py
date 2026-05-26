from fastapi import Request

from services.groq.client import GroqClient as OllamaClient


def get_ollama(request: Request) -> OllamaClient:
    return request.app.state.ollama
