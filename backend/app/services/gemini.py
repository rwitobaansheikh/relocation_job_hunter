"""Shared Google Gemini text-generation helper."""

import asyncio
import logging
import random
from typing import Optional

import httpx

from app.config import settings
from app.security import decrypt_secret
from app.services import rate_limiter

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Transient statuses worth retrying: rate limit (429) and server errors (5xx).
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 8
_BASE_DELAY_SECONDS = 3.0
_MAX_DELAY_SECONDS = 45.0


def resolve_gemini_api_key(profile=None) -> str:
    """Shared app key from .env, or the user's encrypted override from Settings."""
    if profile is not None:
        override = decrypt_secret(getattr(profile, "gemini_api_key_enc", "") or "")
        if override:
            return override.strip()
    return (settings.gemini_api_key or "").strip()


def _retry_delay(attempt: int, response: Optional[httpx.Response]) -> float:
    """Honor the server's Retry-After header when present, else exponential backoff."""
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    # Exponential backoff with jitter, capped so we don't wait forever.
    delay = _BASE_DELAY_SECONDS * (2 ** attempt) + random.uniform(0, 1.5)
    return min(delay, _MAX_DELAY_SECONDS)


async def gemini_generate(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    disable_thinking: bool = True,
    api_key: Optional[str] = None,
) -> str:
    """Call Gemini's generateContent endpoint and return the text, or '' on
    failure / when no API key is configured.

    Retries transient failures (HTTP 429 rate limits and 5xx) with exponential
    backoff so a temporary rate limit doesn't silently fall back to untailored
    output.

    By default thinking is disabled. Gemini 2.5 models spend "thinking" tokens
    out of the same maxOutputTokens budget, which can consume the whole budget
    and return an empty/truncated body (producing blank documents). These are
    straightforward writing tasks that don't need reasoning tokens.
    """
    key = (api_key or settings.gemini_api_key or "").strip()
    if not key:
        logger.warning("Gemini API key not configured; returning empty text")
        return ""

    url = f"{GEMINI_BASE}/models/{settings.gemini_model}:generateContent"
    generation_config: dict = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if disable_thinking:
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}
    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    if system:
        payload["system_instruction"] = {"parts": [{"text": system}]}

    for attempt in range(_MAX_ATTEMPTS):
        try:
            # Global pace across all users (shared key) before each call.
            await rate_limiter.acquire("llm")
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, params={"key": key}, json=payload)

            if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
                delay = _retry_delay(attempt, response)
                logger.warning(
                    "Gemini returned %s; retrying in %.1fs (attempt %d/%d)",
                    response.status_code, delay, attempt + 1, _MAX_ATTEMPTS,
                )
                await asyncio.sleep(delay)
                continue

            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                logger.warning("Gemini returned no candidates")
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts).strip()
        except httpx.HTTPStatusError as exc:
            logger.error("Gemini generation failed: %s", exc)
            return ""
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _retry_delay(attempt, None)
                logger.warning(
                    "Gemini request error (%s); retrying in %.1fs (attempt %d/%d)",
                    exc, delay, attempt + 1, _MAX_ATTEMPTS,
                )
                await asyncio.sleep(delay)
                continue
            logger.error("Gemini generation failed after retries: %s", exc)
            return ""
        except Exception as exc:
            logger.error("Gemini generation failed: %s", exc)
            return ""

    logger.error("Gemini generation exhausted retries (rate limited)")
    return ""
