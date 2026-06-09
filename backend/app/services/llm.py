"""Unified text generation: local Ollama (default) or cloud Gemini (optional).

Set LLM_PROVIDER=ollama for local GPU inference. For AWS, run Ollama on a GPU
instance or sidecar and set OLLAMA_BASE_URL to that internal endpoint.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.security import decrypt_secret
from app.services import gemini, ollama

logger = logging.getLogger(__name__)


def resolve_gemini_api_key(profile=None) -> str:
    """Cloud Gemini key — only used when LLM_PROVIDER=gemini."""
    if profile is not None:
        override = decrypt_secret(getattr(profile, "gemini_api_key_enc", "") or "")
        if override:
            return override.strip()
    return (settings.gemini_api_key or "").strip()


def llm_available(profile=None) -> bool:
    provider = (settings.llm_provider or "ollama").strip().lower()
    if provider == "gemini":
        return bool(resolve_gemini_api_key(profile))
    return bool((settings.ollama_base_url or "").strip() and (settings.ollama_model or "").strip())


async def llm_generate(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    api_key: Optional[str] = None,
    json_mode: bool = False,
) -> str:
    """Generate text using the configured provider (Ollama by default)."""
    provider = (settings.llm_provider or "ollama").strip().lower()
    if provider == "gemini":
        return await gemini.gemini_generate(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
        )
    return await ollama.ollama_generate(
        prompt,
        system=system,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )


async def llm_health() -> dict:
    provider = (settings.llm_provider or "ollama").strip().lower()
    if provider == "gemini":
        key = bool(settings.gemini_api_key)
        return {
            "provider": "gemini",
            "status": "configured" if key else "no_key",
            "model": settings.gemini_model,
        }
    return await ollama.ollama_health()
