# IT Helpdesk Assistant — Reference Implementation

Sistem referensi yang **sudah berfungsi penuh**, digunakan sebagai starter system
untuk Assignment 5 (AI System Evaluation, Safety & Optimization).

Sistem ini menggabungkan RAG (menjawab pertanyaan kebijakan/informasi) dan tool call
(mengecek status tiket) melalui satu router, dibungkus sebagai backend API FastAPI.

## Menjalankan Secara Lokal

```bash
pip install -r requirements.txt
cp .env.example .env   # lalu isi GEMINI_API_KEY di dalam .env
uvicorn app.main:app --reload
```

## Menjalankan dengan Docker

```bash
docker build -t it-helpdesk-reference .
docker run -p 8000:8000 --env-file .env it-helpdesk-reference
```

## Menguji Endpoint

```bash
# Pertanyaan FAQ (diarahkan ke RAG)
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "berapa jatah cuti tahunan saya?"}'

# Cek status tiket (diarahkan ke tool call)
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "apa status TICKET-0005?"}'
```

## Catatan

Sistem ini adalah starting point untuk Assignment 5 — tugasmu adalah **mengevaluasi**
sistem ini (atau sistem hasil Assignment 4 milikmu sendiri), bukan membangunnya dari awal.
Lihat Assignment Brief untuk instruksi evaluasi lengkap.
