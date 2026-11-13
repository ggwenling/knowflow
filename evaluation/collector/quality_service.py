"""Local evaluation entry point using the product LangChain and budget path."""
from contextlib import aclosing
import hmac
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from fastapi import HTTPException, Request
import uvicorn

from knowflow_ai.answering import AnswerService, ReadOnlyRetriever
from knowflow_ai.app import create_app
from knowflow_ai.worker import IndexWorker

from capture import CaptureStore, CapturingRetriever


class OfflineEmbedding:
    async def embed(self, texts, *, request_id):
        def encode(text):
            text = "".join(re.findall(r"\w", text.lower()))
            vector = [0.0] * 1024
            for i in range(len(text) - 1):
                bucket = int.from_bytes(sha256(text[i:i + 2].encode()).digest()[:2], "big") % len(vector)
                vector[bucket] += 1.0
            if not any(vector):
                vector[0] = 1.0
            return vector

        return {"request_id": request_id, "model": "BAAI/bge-m3", "dimensions": 1024,
                "data": [{"index": i, "embedding": encode(text)} for i, text in enumerate(texts)]}

    async def aclose(self):
        pass


def create_quality_app():
    secret = os.environ["KNOWFLOW_EVALUATION_CONTROL_SECRET"]
    if len(secret) < 32:
        raise RuntimeError("EVALUATION_CONTROL_SECRET_INVALID")
    traces = CaptureStore()
    results = {}
    offline = os.environ.get("KNOWFLOW_OFFLINE_QUALITY") == "1"
    if offline:
        questions = json.loads((Path(__file__).resolve().parents[1] /
                                "data/seed-v2-reviewed/questions.json").read_bytes())
        gold = {row["question"]: row["evidence"] for row in questions}

        class OfflineAnswer:
            async def stream_content(self, question, evidence, *, request_id):
                # Extract only annotated spans actually present in retrieved chunks.
                used, claims = [], []
                for span in gold[question]:
                    for row in evidence:
                        if span["quote"] in row["text_content"]:
                            source_id = row["source_id"]
                            if source_id not in used:
                                used.append(source_id)
                            claims.extend(claim + f" [{source_id}]。"
                                          for claim in re.split(r"[。！？；]", span["quote"]) if claim.strip())
                            break
                yield json.dumps({"has_answer": bool(used), "answer": "".join(claims), "source_ids": used})

            async def aclose(self):
                pass

    def retriever(database_url, settings):
        return CapturingRetriever(ReadOnlyRetriever(database_url,
                                   embedding_factory=OfflineEmbedding if offline else None, embedding_settings=settings),
                                   traces, allow_followup=True)

    class RecordingService(AnswerService):
        async def stream(self, request):
            request_id = request["request_id"]
            answer, sources = [], None
            async with aclosing(super().stream(request)) as events:
                async for event in events:
                    if event["event"] == "delta":
                        answer.append(event["delta"])
                    if event["event"] == "sources":
                        sources = event
                    if event["event"] == "completed" and sources is not None:
                        results[request_id] = {
                            "request_id": request_id,
                            "trace": traces.take_nowait(request_id),
                            "response": {"request_id": request_id, "answer": "".join(answer),
                                         "sources": sources["sources"], "has_answer": sources["has_answer"]},
                        }
                    yield event

    def service(*args, **kwargs):
        return RecordingService(*args, **kwargs, **({"llm_factory": OfflineAnswer} if offline else {}))

    app = create_app(answer_service_factory=service, answer_retriever_factory=retriever,
                     worker_factory=(lambda gateway: IndexWorker(gateway, embedding_factory=OfflineEmbedding))
                     if offline else None, use_product_answer_model=not offline)

    @app.post("/internal/evaluation/results/{request_id}")
    async def take_result(request: Request, request_id: str):
        if (request.client is None or request.client.host not in ("127.0.0.1", "::1")
                or not hmac.compare_digest(request.headers.get("X-Evaluation-Secret", "").encode(), secret.encode())):
            raise HTTPException(403)
        if request_id not in results:
            raise HTTPException(404)
        return results.pop(request_id)

    return app


if __name__ == "__main__":
    uvicorn.run(create_quality_app(), host="127.0.0.1",
                port=int(os.environ.get("KNOWFLOW_EVALUATION_AI_PORT", "8000")), access_log=False)
