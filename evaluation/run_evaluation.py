"""
Skrip evaluasi: menjalankan skenario terhadap sistem (in-process) dan mencatat
response, latency per tahap, serta token usage.

Cara pakai (dari root repo):
    set -a; source system/.env; set +a
    PYTHONPATH=system .venv/bin/python evaluation/run_evaluation.py \
        --scenarios evaluation/evaluation_test_scenarios.csv \
        --out evaluation/evaluation_results.csv

Instrumentasi hanya MEMBUNGKUS pemanggilan client Gemini (embed / generate) dan
semantic_search; logika sistem tidak diubah sehingga angka yang tercatat adalah
perilaku sistem apa adanya.
"""

import argparse
import asyncio
import time

import pandas as pd

from app import rag, router


class Recorder:
    def __init__(self):
        self.reset()

    def reset(self):
        self.calls = []  # (stage, seconds, tokens_in, tokens_out)
        self.retrieved = []
        self.failed = 0

    def total(self, stage, idx):
        return sum(c[idx] for c in self.calls if c[0] == stage)


REC = Recorder()


def _wrap_generate(client):
    orig = client.models.generate_content

    def wrapped(*args, **kwargs):
        contents = kwargs.get("contents", "")
        stage = "intent_llm" if str(contents).startswith("Klasifikasikan") else "answer_llm"
        t0 = time.perf_counter()
        try:
            resp = orig(*args, **kwargs)
        except Exception:
            REC.calls.append((stage, time.perf_counter() - t0, 0, 0))
            REC.failed += 1
            raise
        dt = time.perf_counter() - t0
        u = resp.usage_metadata
        tin = (u.prompt_token_count or 0) if u else 0
        tout = ((u.candidates_token_count or 0) + (u.thoughts_token_count or 0)) if u else 0
        REC.calls.append((stage, dt, tin, tout))
        return resp

    client.models.generate_content = wrapped


def _wrap_embed(client):
    orig = client.models.embed_content

    def wrapped(*args, **kwargs):
        t0 = time.perf_counter()
        resp = orig(*args, **kwargs)
        REC.calls.append(("embed", time.perf_counter() - t0, 0, 0))
        return resp

    client.models.embed_content = wrapped


def _wrap_search():
    orig = rag.semantic_search

    def wrapped(query, top_k=3):
        res = orig(query, top_k)
        REC.retrieved = res
        return res

    rag.semantic_search = wrapped


async def run(scenarios_path, out_path, only=None, repeat=1):
    # Kompatibel dengan kode sebelum perbaikan (client di rag/router) dan sesudahnya (app.llm.client).
    try:
        from app import llm
        clients = [llm.client]
    except ImportError:
        clients = [rag._client] + ([router._client] if router._client is not rag._client else [])
    for c in clients:
        _wrap_generate(c)
        _wrap_embed(c)
    _wrap_search()

    t0 = time.perf_counter()
    rag.build_index()
    build_s = time.perf_counter() - t0
    print(f"build_index: {build_s:.2f}s")

    df = pd.read_csv(scenarios_path)
    df = df[df["scenario_id"].astype(str).str.startswith("EVAL")]
    if only:
        df = df[df["scenario_id"].isin(only)]
    rows = []
    for _, sc in [x for x in df.iterrows() for _ in range(repeat)]:
        REC.reset()
        t0 = time.perf_counter()
        result = await router.handle_query(sc["query"])
        total = time.perf_counter() - t0
        top = REC.retrieved[0] if REC.retrieved else None
        rows.append({
            "scenario_id": sc["scenario_id"],
            "category": sc["category"],
            "query": sc["query"],
            "intent": result["intent"],
            "status": result["status"],
            "actual_response": result["data"],
            "latency_total_s": round(total, 2),
            "latency_intent_llm_s": round(REC.total("intent_llm", 1), 2),
            "latency_embed_s": round(REC.total("embed", 1), 2),
            "latency_answer_llm_s": round(REC.total("answer_llm", 1), 2),
            "llm_calls": sum(1 for c in REC.calls if c[0] != "embed"),
            "failed_api_calls": REC.failed,
            "tokens_in": REC.total("intent_llm", 2) + REC.total("answer_llm", 2),
            "tokens_out": REC.total("intent_llm", 3) + REC.total("answer_llm", 3),
            "top1_faq": top["question"] if top else "",
            "top1_distance": round(top["distance"], 3) if top else "",
            "observation": "",
        })
        r = rows[-1]
        print(f"{r['scenario_id']} {r['latency_total_s']}s in={r['tokens_in']} out={r['tokens_out']} intent={r['intent']}")

    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"ditulis: {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", help="daftar scenario_id dipisah koma, mis. EVAL-11,EVAL-12")
    ap.add_argument("--repeat", type=int, default=1)
    a = ap.parse_args()
    asyncio.run(run(a.scenarios, a.out, a.only.split(",") if a.only else None, a.repeat))
