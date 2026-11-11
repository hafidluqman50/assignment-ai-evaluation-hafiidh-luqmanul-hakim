"""
Router — intent detection + routing ke RAG atau tool call.

Perubahan dari reference system (lihat README):
- Greeting ditangani tanpa LLM/RAG                                   -> ISSUE-03
- Intent LLM hanya dipanggil jika query menyebut "tiket/ticket"      -> ISSUE-02, ISSUE-03
- Error provider ditangkap, dicatat, dan dijawab dengan pesan ramah   -> ISSUE-05
"""

import asyncio
import logging
import re

from app import llm
from app.rag import answer_from_knowledge_base
from app.tools import get_ticket_status

log = logging.getLogger("helpdesk.router")

TICKET_ID_PATTERN = re.compile(r"TICKET-\d{4}", re.IGNORECASE)
TICKET_WORD_PATTERN = re.compile(r"tiket|ticket", re.IGNORECASE)
GREETING_PATTERN = re.compile(
    r"^\s*(halo|hallo|hai|hi|hello|hey|p|selamat\s+(pagi|siang|sore|malam)|assalamualaikum)[\s!.,?]*$",
    re.IGNORECASE,
)

GREETING_REPLY = (
    "Halo! Saya asisten IT Helpdesk. Saya bisa membantu soal cuti, akses & password, "
    "perangkat, onboarding/HR, kebijakan kerja, dan cek status tiket (sebutkan ID, mis. TICKET-0005)."
)
UNAVAILABLE_REPLY = (
    "Layanan AI sedang sibuk atau tidak merespons. Silakan coba lagi sebentar lagi, "
    "atau hubungi tim IT Support jika mendesak."
)


async def detect_intent(query: str) -> str:
    """
    Menentukan intent: 'faq' atau 'ticket_status'.
    Urutan: (1) ID tiket eksplisit, (2) tidak ada kata tiket/ticket => faq tanpa LLM,
    (3) baru klasifikasi LLM untuk kasus ambigu.
    """
    if TICKET_ID_PATTERN.search(query):
        return "ticket_status"
    if not TICKET_WORD_PATTERN.search(query):
        return "faq"

    prompt = f"""Klasifikasikan pertanyaan berikut ke dalam salah satu kategori:
'faq' (pertanyaan informasi/kebijakan umum seputar cuti, akses, perangkat, HR, dsb)
atau 'ticket_status' (permintaan mengecek status tiket tertentu).

Jawab HANYA dengan satu kata: faq atau ticket_status.

Pertanyaan: {query}"""

    text = await asyncio.to_thread(llm.generate, prompt, 0.0, 8, query)
    intent = text.strip().lower()

    if intent not in ("faq", "ticket_status"):
        return "faq"  # default fallback yang lebih aman daripada 'unknown'
    return intent


def extract_ticket_id(query: str) -> str:
    """Mengekstrak ticket_id dari teks query menggunakan regex."""
    match = TICKET_ID_PATTERN.search(query)
    if match:
        return match.group(0).upper()
    return ""


async def handle_query(query: str) -> dict:
    """Fungsi utama yang dipanggil oleh endpoint /ask."""
    try:
        if GREETING_PATTERN.match(query):
            return {"status": "success", "intent": "greeting", "data": GREETING_REPLY}

        intent = await detect_intent(query)

        if intent == "ticket_status":
            ticket_id = extract_ticket_id(query)
            if not ticket_id:
                return {
                    "status": "error",
                    "intent": "ticket_status",
                    "data": "Mohon sertakan ID tiket (format: TICKET-XXXX) pada pertanyaan Anda.",
                }
            data = get_ticket_status(ticket_id)
            return {"status": "success", "intent": "ticket_status", "data": data}

        else:  # intent == "faq"
            data = await answer_from_knowledge_base(query)
            return {"status": "success", "intent": "faq", "data": data}

    except llm.LLMUnavailable as e:
        log.error("llm_unavailable cause=%s query=%r", e, query[:80])
        return {"status": "error", "intent": "unknown", "data": UNAVAILABLE_REPLY}
    except Exception as e:
        log.exception("handle_query_failed query=%r", query[:80])
        return {
            "status": "error",
            "intent": "unknown",
            "data": f"Terjadi kesalahan saat memproses permintaan Anda. Silakan coba lagi. ({type(e).__name__})",
        }
