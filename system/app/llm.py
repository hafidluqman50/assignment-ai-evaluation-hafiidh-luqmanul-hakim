"""
Klien Gemini bersama: timeout eksplisit, fallback model, dan penanganan response kosong.

Dibuat karena evaluasi menemukan satu panggilan LLM bisa menggantung 190-225 detik saat
provider membalas 503 "high demand" (lihat README, ISSUE-02). Total waktu terburuk sekarang
dibatasi: 2 percobaan x LLM_TIMEOUT_MS.
"""

import logging
import os
import time

from google import genai
from google.genai import errors, types

log = logging.getLogger("helpdesk.llm")

GEN_MODEL = os.environ.get("GEN_MODEL", "gemini-3.1-flash-lite")
GEN_FALLBACK_MODEL = os.environ.get("GEN_FALLBACK_MODEL", "gemini-3.5-flash-lite")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "gemini-embedding-001")
TIMEOUT_MS = int(os.environ.get("LLM_TIMEOUT_MS", "10000"))

# attempts=1 mematikan retry internal SDK yang menyebabkan tunggu ratusan detik;
# retry kita kendalikan sendiri (primary -> fallback).
client = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY"),
    http_options=types.HttpOptions(
        timeout=TIMEOUT_MS,
        retry_options=types.HttpRetryOptions(attempts=1),
    ),
)


class LLMUnavailable(Exception):
    """Semua percobaan ke provider gagal (timeout / 5xx / 429)."""


def _is_retryable(exc: Exception) -> bool:
    # Error 4xx selain 429 (mis. input tidak valid) tidak akan sembuh dengan retry.
    return not (isinstance(exc, errors.ClientError) and getattr(exc, "code", None) != 429)


def generate(prompt: str, temperature: float, max_output_tokens: int | None = None, ctx: str = "") -> str:
    """Memanggil LLM; coba model utama lalu fallback. Mengembalikan "" jika model tidak memberi teks."""
    config = types.GenerateContentConfig(temperature=temperature, max_output_tokens=max_output_tokens)
    last = None
    for model in (GEN_MODEL, GEN_FALLBACK_MODEL):
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            return (resp.text or "").strip()
        except Exception as e:  # noqa: BLE001 - dicatat lalu diputuskan retry/tidak
            last = e
            log.warning("llm_call_failed model=%s after=%.1fs err=%s ctx=%r", model, time.perf_counter() - t0, type(e).__name__, ctx[:60])
            if not _is_retryable(e):
                raise
    raise LLMUnavailable(type(last).__name__) from last


def embed(text: str, ctx: str = ""):
    """Embedding dengan timeout dan satu kali retry."""
    last = None
    for _ in range(2):
        try:
            return client.models.embed_content(model=EMBED_MODEL, contents=text).embeddings[0].values
        except Exception as e:  # noqa: BLE001
            last = e
            log.warning("embed_failed err=%s ctx=%r", type(e).__name__, ctx[:60])
            if not _is_retryable(e):
                raise
    raise LLMUnavailable(type(last).__name__) from last
