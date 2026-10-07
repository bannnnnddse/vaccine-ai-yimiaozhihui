from fastapi.testclient import TestClient

from app import main
from app.core.config import Settings
from app.rag.service import RetrievalTrace


def test_model_http_clients_ignore_broken_system_proxy_settings(monkeypatch) -> None:
    http_clients = []
    openai_kwargs = {}

    class FakeHttpClient:
        def __init__(self, **kwargs) -> None:
            self.trust_env = kwargs.get("trust_env")
            http_clients.append(self)

        async def aclose(self) -> None:
            return None

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            openai_kwargs.update(kwargs)

        async def close(self) -> None:
            return None

    monkeypatch.setattr(main.httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(main, "AsyncOpenAI", FakeOpenAI)

    app = main.create_app(Settings(dashscope_api_key="test-key"))
    with TestClient(app):
        pass

    assert openai_kwargs["http_client"] is http_clients[0]
    assert [client.trust_env for client in http_clients] == [False, False]


def test_production_rag_warmup_finishes_before_app_is_ready(monkeypatch) -> None:
    calls = []

    class FakeRagService:
        def warmup(self) -> RetrievalTrace:
            calls.append("warmup")
            return RetrievalTrace(
                pipeline="hybrid_v2",
                dense=[],
                lexical=[],
                fused=[],
                reranked=[],
                quality_adjusted=[],
                selected=[],
                timings_ms={"dense": 1.0, "lexical": 2.0, "reranker": 3.0},
            )

    fake_rag = FakeRagService()
    monkeypatch.setattr(
        main.RagService,
        "from_settings",
        classmethod(lambda cls, settings: fake_rag),
    )
    monkeypatch.setattr(main, "configure_cpu_threads", lambda *args: None)

    app = main.create_app(
        Settings(
            _env_file=None,
            dashscope_api_key=None,
            pubmed_enabled=False,
            rag_warmup_enabled=True,
        )
    )
    with TestClient(app):
        assert calls == ["warmup"]
        assert app.state.rag_semaphore._value == 1
