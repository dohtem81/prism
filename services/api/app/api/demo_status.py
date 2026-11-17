from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from shared.local_llm import local_model
from shared.logging_utils import get_logger

router = APIRouter(prefix="/v1/demo", tags=["demo"])
logger = get_logger("prism.api.demo_status")


class OllamaStatus(BaseModel):
    processor: Literal["cpu", "gpu", "mixed", "idle", "unavailable"]


@router.get("/ollama-status", response_model=OllamaStatus)
def ollama_status() -> OllamaStatus:
    try:
        response = httpx.get("http://ollama:11434/api/ps", timeout=2.0)
        response.raise_for_status()
        models = response.json()["models"]
        if not isinstance(models, list):
            raise ValueError("Invalid Ollama model list")
        name = local_model()
        for model in models:
            if model["name"] not in (name, f"{name}:latest"):
                continue
            size, vram = model["size"], model["size_vram"]
            if not isinstance(size, int) or not isinstance(vram, int) or size <= 0 or not 0 <= vram <= size:
                raise ValueError("Invalid Ollama processor sizes")
            return OllamaStatus(processor="cpu" if vram == 0 else "gpu" if vram == size else "mixed")
        return OllamaStatus(processor="idle")
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        logger.exception("ollama_status_unavailable")
        return OllamaStatus(processor="unavailable")
