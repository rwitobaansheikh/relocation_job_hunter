"""Local LLM generation via Ollama (http://localhost:11434 by default).

Runs on your GPU with no per-token cloud fees. In production, point
OLLAMA_BASE_URL at an internal Ollama service (EC2 sidecar, ECS GPU task, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional

import httpx

from app.config import settings
from app.services import rate_limiter

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4
_BASE_DELAY_SECONDS = 2.0


def _base_url() -> str:
    return (settings.ollama_base_url or "http://localhost:11434").rstrip("/")


def _retry_delay(attempt: int) -> float:
    return min(_BASE_DELAY_SECONDS * (2 ** attempt) + random.uniform(0, 1), 30.0)


async def ollama_generate(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    json_mode: bool = False,
    model: Optional[str] = None,
) -> str:
    """Call Ollama's /api/chat endpoint and return assistant text."""
    chosen_model = (model or settings.ollama_model or "").strip()
    if not chosen_model:
        logger.warning("Ollama model not configured; returning empty text")
        return ""

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {
        "model": chosen_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if json_mode:
        payload["format"] = "json"

    url = f"{_base_url()}/api/chat"
    timeout = float(settings.ollama_timeout_seconds or 300)

    for attempt in range(_MAX_ATTEMPTS):
        try:
            await rate_limiter.acquire("llm")
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)

            if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
                delay = _retry_delay(attempt)
                logger.warning(
                    "Ollama returned %s; retrying in %.1fs (attempt %d/%d)",
                    response.status_code,
                    delay,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                )
                await asyncio.sleep(delay)
                continue

            response.raise_for_status()
            data = response.json()
            message = data.get("message") or {}
            content = (message.get("content") or "").strip()
            if not content:
                logger.warning("Ollama returned empty content for model %s", chosen_model)
            return content
        except httpx.HTTPStatusError as exc:
            body = ""
            try:
                body = exc.response.text[:300]
            except Exception:
                pass
            logger.error("Ollama generation failed (%s): %s", exc.response.status_code, body)
            return ""
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _retry_delay(attempt)
                logger.warning(
                    "Ollama request error (%s); retrying in %.1fs (attempt %d/%d)",
                    exc,
                    delay,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                )
                await asyncio.sleep(delay)
                continue
            logger.error("Ollama generation failed after retries: %s", exc)
            return ""
        except Exception as exc:
            logger.error("Ollama generation failed: %s", exc)
            return ""

    return ""


async def ollama_health() -> dict:
    """Check whether Ollama is reachable and the configured model is pulled."""
    base = _base_url()
    model = (settings.ollama_model or "").strip()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{base}/api/tags")
        if response.status_code != 200:
            return {
                "provider": "ollama",
                "status": "error",
                "base_url": base,
                "error": f"HTTP {response.status_code}",
            }
        names = [m.get("name", "") for m in response.json().get("models", [])]
        has_model = any(
            model == name or name.startswith(f"{model}:") or model.startswith(name)
            for name in names
        )
        return {
            "provider": "ollama",
            "status": "ok" if has_model else "model_missing",
            "base_url": base,
            "model": model,
            "models_available": len(names),
        }
    except Exception as exc:
        return {
            "provider": "ollama",
            "status": "unreachable",
            "base_url": base,
            "model": model,
            "error": str(exc),
        }
