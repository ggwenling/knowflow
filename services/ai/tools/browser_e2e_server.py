"""Run the real AI service with local deterministic adapters for browser E2E."""
import argparse
import asyncio
import json
import os


class BrowserE2ELlm:
    def __init__(self, *_args, **_kwargs):
        pass

    @staticmethod
    def answer(question, evidence):
        source_id = evidence[0]["source_id"]
        return {"answer": f"本地合成验证：{question} [{source_id}]",
                "has_answer": True, "source_ids": [source_id]}

    async def generate(self, question, evidence, *, request_id):
        return self.answer(question, evidence)

    async def stream_content(self, question, evidence, *, request_id):
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
    answering.DeepSeekAdapter = BrowserE2ELlm
    worker.SiliconFlowEmbeddingAdapter = SyntheticEmbedding

    import uvicorn
    from knowflow_ai.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port,
                log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
