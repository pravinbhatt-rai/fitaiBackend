from fastapi import Request

from services.groq.client import GroqClient


def get_ollama(request: Request) -> GroqClient:
    return request.app.state.ollama
