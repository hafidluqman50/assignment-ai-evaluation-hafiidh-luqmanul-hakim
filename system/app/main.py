"""
Entry point aplikasi FastAPI — IT Helpdesk Assistant (Reference Implementation).
"""

from fastapi import FastAPI
from pydantic import BaseModel, field_validator

from app.router import handle_query
from app.rag import build_index

app = FastAPI(title="IT Helpdesk Assistant API")


MAX_QUERY_CHARS = 500  # FAQ helpdesk pendek; skenario terpanjang (EVAL-11) ~170 karakter


class AskRequest(BaseModel):
    query: str

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Pertanyaan tidak boleh kosong.")
        if len(v) > MAX_QUERY_CHARS:
            raise ValueError(f"Pertanyaan terlalu panjang (maksimal {MAX_QUERY_CHARS} karakter).")
        return v


class AskResponse(BaseModel):
    status: str
    intent: str
    data: str


@app.on_event("startup")
async def startup_event():
    """Membangun index FAISS sekali saat aplikasi start, bukan di setiap request."""
    build_index()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    result = await handle_query(request.query)
    return AskResponse(**result)
