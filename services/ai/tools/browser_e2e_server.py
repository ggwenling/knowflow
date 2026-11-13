"""Run the real AI service with local deterministic adapters for browser E2E."""
import argparse
import asyncio
from functools import partial
import json
import os


class BrowserE2ELlm:
    def __init__(self, *_args, **_kwargs):
        pass

    @staticmethod
    def answer(question, evidence):
        if question.startswith("[e2e:refusal]"):
            return {"answer": "合成拒答草稿不得显示", "has_answer": False, "source_ids": []}
        source_id = evidence[0]["source_id"]
        return {"answer": f"本地合成验证：{question} [{source_id}]",
                "has_answer": True, "source_ids": [source_id]}

    async def generate(self, question, evidence, *, request_id):
        return self.answer(question, evidence)

    async def stream_content(self, question, evidence, *, request_id):
        if question.startswith(("[e2e:error]", "[e2e:cancelled]", "[e2e:slow]", "[e2e:timeout]")):
            # Only this test entrypoint installs the synthetic adapter.
            yield '{"has_answer":true,"answer":"合成中断片段'
            await asyncio.sleep(0.1)
            if question.startswith("[e2e:error]"):
                from knowflow_ai.adapters import ProcessingError
                raise ProcessingError("MODEL_FAILURE", 502, retryable=False)
            if question.startswith("[e2e:cancelled]"):
                raise asyncio.CancelledError
            if question.startswith("[e2e:timeout]"):
                # Let the real request deadline expire while awaiting model data.
                await asyncio.sleep(60)
            for _ in range(40):
                yield "。"
                await asyncio.sleep(0.1)
            source_id = evidence[0]["source_id"]
            yield f' [{source_id}]","source_ids":' + json.dumps([source_id]) + "}"
            return
        payload = json.dumps(self.answer(question, evidence), ensure_ascii=False,
                             separators=(",", ":"))
        for position in range(0, len(payload), 8):
            yield payload[position:position + 8]
            await asyncio.sleep(0.02)

    async def aclose(self):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    os.environ.setdefault("KNOWFLOW_EMBEDDING_KEY_ENV", "KNOWFLOW_E2E_DUMMY_EMBEDDING_KEY")
    os.environ.setdefault("KNOWFLOW_E2E_DUMMY_EMBEDDING_KEY", "e" * 64)
    os.environ.setdefault("KNOWFLOW_LLM_KEY_ENV", "KNOWFLOW_E2E_DUMMY_LLM_KEY")
    os.environ.setdefault("KNOWFLOW_E2E_DUMMY_LLM_KEY", "f" * 64)

    import knowflow_ai.answering as answering
    import knowflow_ai.worker as worker
    from local_backend_e2e import SyntheticEmbedding

    answering.SiliconFlowEmbeddingAdapter = SyntheticEmbedding
    worker.SiliconFlowEmbeddingAdapter = SyntheticEmbedding

    import uvicorn
    from knowflow_ai.app import create_app

    uvicorn.run(create_app(answer_service_factory=partial(answering.AnswerService, llm_factory=BrowserE2ELlm)),
                host=args.host, port=args.port,
                log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
