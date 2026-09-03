import asyncio

import pytest

from app.core.config import Settings
from app.graph.llm_extractor import GraphExtractionError, LLMGraphExtractor
from app.rag.models import TextChunk


class _Completions:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_kwargs):
        self.calls += 1
        return type("Response", (), {"choices": [type("Choice", (), {
            "message": type("Message", (), {"content": "not-json"})()
        })()]})()


def _chunk() -> TextChunk:
    return TextChunk(
        id="chunk", file_name="test.md", relative_path="test.md", page=None,
        chunk_index=0, text="乙肝疫苗可预防乙型肝炎。", source_hash="source",
    )


def test_json_schema_failure_retries_with_all_backoff_slots(monkeypatch, tmp_path) -> None:
    completions = _Completions()
    client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    extractor = LLMGraphExtractor(
        Settings(_env_file=None, graph_snapshot_dir=tmp_path / "graph"), client
    )

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr("app.graph.llm_extractor.asyncio.sleep", no_wait)
    with pytest.raises(GraphExtractionError, match="graph extraction request failed") as error:
        asyncio.run(extractor._request_batch([_chunk()]))

    assert error.value.kind == "json_schema"
    assert completions.calls == 4
