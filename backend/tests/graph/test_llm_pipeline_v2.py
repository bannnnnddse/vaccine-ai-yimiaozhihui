import asyncio
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.graph.jobs import GraphJobRepository
from app.graph.llm_extractor import (
    LLMBatchExtraction,
    LLMEntityCandidate,
    LLMRelationCandidate,
    ValidatedChunkExtraction,
    ValidatedEntity,
    ValidatedRelation,
    validate_batch,
)
from app.graph.semantica_adapter import SemanticaGraphBuilderAdapter
from app.graph.snapshot import GraphSnapshotPipeline, _aggregate
from app.main import create_app
from app.rag.catalog import write_chunk_catalog
from app.rag.index_versions import activate_index, version_directory
from app.rag.models import TextChunk


def _chunk(text: str = "九价HPV疫苗可预防HPV16感染。") -> TextChunk:
    return TextChunk(
        id="chunk-1",
        file_name="中国HPV疫苗指南.md",
        relative_path="指南/中国HPV疫苗指南.md",
        page=7,
        chunk_index=0,
        text=text,
        source_hash="source-1",
        source_type="web",
        source_title="中国HPV疫苗指南",
        source_url="https://example.test/hpv",
        section="保护效果",
        parent_doc_id="doc-1",
        content_hash=sha256(text.encode()).hexdigest(),
        authority_level=3,
    )


def test_validator_accepts_supported_relation_and_rejects_negation() -> None:
    chunk = _chunk()
    entities = [
        LLMEntityCandidate(
            canonical_name="九价HPV疫苗", entity_type="Vaccine", aliases=[],
            surface_form="九价HPV疫苗", chunk_id=chunk.id,
        ),
        LLMEntityCandidate(
            canonical_name="HPV16", entity_type="Pathogen", aliases=["HPV-16"],
            surface_form="HPV16", chunk_id=chunk.id,
        ),
    ]
    valid = validate_batch(LLMBatchExtraction(
        entities=entities,
        relations=[LLMRelationCandidate(
            source_surface="九价HPV疫苗", target_surface="HPV16",
            relation_type="PREVENTS", evidence_quote=chunk.text,
            confidence=0.96, chunk_id=chunk.id,
        )],
    ), [chunk], 0.85)
    assert valid[0].relations[0].relation_type == "PREVENTS"

    negated_chunk = _chunk("九价HPV疫苗不能预防HPV16感染。")
    rejected = validate_batch(LLMBatchExtraction(
        entities=[item.model_copy(update={"chunk_id": negated_chunk.id}) for item in entities],
        relations=[LLMRelationCandidate(
            source_surface="九价HPV疫苗", target_surface="HPV16",
            relation_type="PREVENTS", evidence_quote=negated_chunk.text,
            confidence=0.99, chunk_id=negated_chunk.id,
        )],
    ), [negated_chunk], 0.85)
    assert rejected[0].relations == []
    assert "negated_statement" in rejected[0].rejected


def test_validator_admits_new_medical_entities_but_rejects_administrative_mistypes() -> None:
    medical_chunk = _chunk("乙肝疫苗可预防乙型肝炎。")
    medical = validate_batch(
        LLMBatchExtraction(
            entities=[
                LLMEntityCandidate(
                    canonical_name="乙肝疫苗",
                    entity_type="Vaccine",
                    aliases=[],
                    surface_form="乙肝疫苗",
                    chunk_id=medical_chunk.id,
                ),
                LLMEntityCandidate(
                    canonical_name="乙型肝炎",
                    entity_type="Disease",
                    aliases=[],
                    surface_form="乙型肝炎",
                    chunk_id=medical_chunk.id,
                ),
            ],
            relations=[
                LLMRelationCandidate(
                    source_surface="乙肝疫苗",
                    target_surface="乙型肝炎",
                    relation_type="PREVENTS",
                    evidence_quote=medical_chunk.text,
                    confidence=0.96,
                    chunk_id=medical_chunk.id,
                )
            ],
        ),
        [medical_chunk],
        0.85,
    )
    assert medical[0].relations[0].relation_type == "PREVENTS"

    administrative_chunk = _chunk("接种单位是指从事预防接种工作的医疗机构。")
    administrative = validate_batch(
        LLMBatchExtraction(
            entities=[
                LLMEntityCandidate(
                    canonical_name="接种单位",
                    entity_type="Vaccine",
                    aliases=[],
                    surface_form="接种单位",
                    chunk_id=administrative_chunk.id,
                ),
                LLMEntityCandidate(
                    canonical_name="从事预防接种工作的医疗机构",
                    entity_type="Vaccine",
                    aliases=[],
                    surface_form="从事预防接种工作的医疗机构",
                    chunk_id=administrative_chunk.id,
                ),
            ],
        ),
        [administrative_chunk],
        0.85,
    )
    assert administrative[0].relations == []
    assert "new_entity_type_lexical_mismatch" in administrative[0].rejected


def test_validator_rejects_conflicting_types_and_new_canonical_rewrites() -> None:
    chunk = _chunk("乙肝疫苗可预防乙型肝炎。")
    result = validate_batch(
        LLMBatchExtraction(
            entities=[
                LLMEntityCandidate(
                    canonical_name="乙型肝炎疫苗",
                    entity_type="Vaccine",
                    aliases=[],
                    surface_form="乙肝疫苗",
                    chunk_id=chunk.id,
                ),
                LLMEntityCandidate(
                    canonical_name="乙肝疫苗",
                    entity_type="Disease",
                    aliases=[],
                    surface_form="乙肝疫苗",
                    chunk_id=chunk.id,
                ),
            ]
        ),
        [chunk],
        0.85,
    )
    assert result[0].entities == []
    assert "conflicting_entity_types" in result[0].rejected


def test_showcase_validator_preserves_unknown_source_surface_and_schema_excludes_reserved_relations(
) -> None:
    chunk = _chunk("重组乙型肝炎疫苗可预防乙型肝炎。")
    payload = LLMBatchExtraction(
        entities=[
            LLMEntityCandidate(
                canonical_name="乙肝疫苗",
                entity_type="Vaccine",
                aliases=[],
                surface_form="重组乙型肝炎疫苗",
                chunk_id=chunk.id,
            ),
            LLMEntityCandidate(
                canonical_name="乙肝",
                entity_type="Disease",
                aliases=[],
                surface_form="乙型肝炎",
                chunk_id=chunk.id,
            ),
        ],
        relations=[
            LLMRelationCandidate(
                source_surface="重组乙型肝炎疫苗",
                target_surface="乙型肝炎",
                relation_type="PREVENTS",
                evidence_quote=chunk.text,
                confidence=0.96,
                chunk_id=chunk.id,
            )
        ],
    )
    result = validate_batch(payload, [chunk], 0.85)
    assert [entity.canonical_name for entity in result[0].entities] == [
        "重组乙型肝炎疫苗",
        "乙型肝炎",
    ]
    assert result[0].relations[0].relation_type == "PREVENTS"

    with pytest.raises(ValidationError):
        LLMRelationCandidate(
            source_surface="重组乙型肝炎疫苗",
            target_surface="乙型肝炎",
            relation_type="IS_A",
            evidence_quote=chunk.text,
            confidence=0.96,
            chunk_id=chunk.id,
        )


def test_validator_repairs_only_an_explicit_same_sentence_evidence_quote() -> None:
    chunk = _chunk("乙肝疫苗可预防乙型肝炎。乙肝疫苗应按程序接种。")
    payload = LLMBatchExtraction(
        entities=[
            LLMEntityCandidate(
                canonical_name="乙肝疫苗",
                entity_type="Vaccine",
                aliases=[],
                surface_form="乙肝疫苗",
                chunk_id=chunk.id,
            ),
            LLMEntityCandidate(
                canonical_name="乙型肝炎",
                entity_type="Disease",
                aliases=[],
                surface_form="乙型肝炎",
                chunk_id=chunk.id,
            ),
        ],
        relations=[
            LLMRelationCandidate(
                source_surface="乙肝疫苗",
                target_surface="乙型肝炎",
                relation_type="PREVENTS",
                evidence_quote="可预防乙型肝炎。",
                confidence=0.96,
                chunk_id=chunk.id,
            )
        ],
    )
    result = validate_batch(payload, [chunk], 0.85)
    assert result[0].relations[0].evidence_quote == "乙肝疫苗可预防乙型肝炎。"


def test_validator_repairs_a_nonverbatim_model_quote_from_explicit_source_sentence() -> None:
    chunk = _chunk("乙肝疫苗可预防乙型肝炎。")
    payload = LLMBatchExtraction(
        entities=[
            LLMEntityCandidate(
                canonical_name="乙肝疫苗",
                entity_type="Vaccine",
                aliases=[],
                surface_form="乙肝疫苗",
                chunk_id=chunk.id,
            ),
            LLMEntityCandidate(
                canonical_name="乙型肝炎",
                entity_type="Disease",
                aliases=[],
                surface_form="乙型肝炎",
                chunk_id=chunk.id,
            ),
        ],
        relations=[
            LLMRelationCandidate(
                source_surface="乙肝疫苗",
                target_surface="乙型肝炎",
                relation_type="PREVENTS",
                evidence_quote="乙肝疫苗可以预防乙型肝炎。",
                confidence=0.80,
                chunk_id=chunk.id,
            )
        ],
    )
    result = validate_batch(payload, [chunk], 0.78)
    assert result[0].relations[0].evidence_quote == chunk.text


def test_validator_backfills_only_explicit_same_sentence_typed_relation() -> None:
    chunk = _chunk("乙肝疫苗可预防乙型肝炎。")
    payload = LLMBatchExtraction(
        entities=[
            LLMEntityCandidate(
                canonical_name="乙肝疫苗",
                entity_type="Vaccine",
                aliases=[],
                surface_form="乙肝疫苗",
                chunk_id=chunk.id,
            ),
            LLMEntityCandidate(
                canonical_name="乙型肝炎",
                entity_type="Disease",
                aliases=[],
                surface_form="乙型肝炎",
                chunk_id=chunk.id,
            ),
        ]
    )
    result = validate_batch(payload, [chunk], 0.85)
    assert [
        (item.source.canonical_name, item.relation_type, item.target.canonical_name)
        for item in result[0].relations
    ] == [
        ("乙肝疫苗", "PREVENTS", "乙型肝炎")
    ]


def test_validator_admits_lexical_fallback_only_for_explicit_medical_endpoint() -> None:
    chunk = _chunk("流脑疫苗可预防流脑。")
    payload = LLMBatchExtraction(
        entities=[
            LLMEntityCandidate(
                canonical_name="流脑疫苗",
                entity_type="Vaccine",
                aliases=[],
                surface_form="流脑疫苗",
                chunk_id=chunk.id,
            ),
            LLMEntityCandidate(
                canonical_name="流脑",
                entity_type="Disease",
                aliases=[],
                surface_form="流脑",
                chunk_id=chunk.id,
            ),
        ],
        relations=[
            LLMRelationCandidate(
                source_surface="流脑疫苗",
                target_surface="流脑",
                relation_type="PREVENTS",
                evidence_quote=chunk.text,
                confidence=0.96,
                chunk_id=chunk.id,
            )
        ],
    )
    result = validate_batch(payload, [chunk], 0.85)
    assert [
        (item.source.canonical_name, item.target.canonical_name)
        for item in result[0].relations
    ] == [
        ("流脑疫苗", "流脑")
    ]

    administrative = _chunk("接种单位可预防儿童疾病。")
    rejected = validate_batch(
        LLMBatchExtraction(
            entities=[
                LLMEntityCandidate(
                    canonical_name="接种单位",
                    entity_type="Vaccine",
                    aliases=[],
                    surface_form="接种单位",
                    chunk_id=administrative.id,
                ),
                LLMEntityCandidate(
                    canonical_name="儿童疾病",
                    entity_type="Disease",
                    aliases=[],
                    surface_form="儿童疾病",
                    chunk_id=administrative.id,
                ),
            ],
            relations=[
                LLMRelationCandidate(
                    source_surface="接种单位",
                    target_surface="儿童疾病",
                    relation_type="PREVENTS",
                    evidence_quote=administrative.text,
                    confidence=0.96,
                    chunk_id=administrative.id,
                )
            ],
        ),
        [administrative],
        0.85,
    )
    assert [entity.surface_form for entity in rejected[0].entities] == ["儿童疾病"]
    assert rejected[0].relations == []
    assert "new_entity_type_lexical_mismatch" in rejected[0].rejected


def test_validator_keeps_non_administrative_contextual_entity_for_visual_coverage() -> None:
    chunk = _chunk("儿童接种流脑疫苗可获得免疫保护。")
    result = validate_batch(
        LLMBatchExtraction(
            entities=[
                LLMEntityCandidate(
                    canonical_name="流脑",
                    entity_type="Disease",
                    aliases=[],
                    surface_form="流脑",
                    chunk_id=chunk.id,
                )
            ]
        ),
        [chunk],
        0.70,
    )
    assert result[0].entities[0].canonical_name == "流脑"


def test_visual_associations_are_bounded_and_never_replace_factual_edges() -> None:
    chunk = _chunk("乙肝疫苗、儿童和乙型肝炎的接种信息。")
    entities = [
        ValidatedEntity(
            canonical_name="乙肝疫苗",
            entity_type="Vaccine",
            aliases=[],
            surface_form="乙肝疫苗",
            chunk_id=chunk.id,
        ),
        ValidatedEntity(
            canonical_name="儿童",
            entity_type="Population",
            aliases=[],
            surface_form="儿童",
            chunk_id=chunk.id,
        ),
        ValidatedEntity(
            canonical_name="乙型肝炎",
            entity_type="Disease",
            aliases=[],
            surface_form="乙型肝炎",
            chunk_id=chunk.id,
        ),
    ]
    extraction = ValidatedChunkExtraction(
        chunk_id=chunk.id,
        content_hash=chunk.content_hash or "",
        entities=entities,
    )
    _nodes, edges, _provenance = _aggregate(
        [chunk],
        [extraction],
        visual_max_per_chunk=2,
        visual_max_degree=1,
    )
    visual = [edge for edge in edges.values() if edge.visual_only]
    assert len(visual) == 1
    assert visual[0].relation_type == "CO_MENTIONED"


class _FakeBuilder:
    def __init__(self, **options):
        assert options == {"merge_entities": False, "resolve_conflicts": False}

    def build(self, payload, **options):
        assert options == {
            "extract": False, "extract_relations": False, "extract_triplets": False,
        }
        return payload


def test_snapshot_and_public_api_follow_one_active_pointer(tmp_path: Path) -> None:
    settings = Settings(
        dashscope_api_key=None,
        pubmed_enabled=False,
        pubmed_create_knowledge_gap=False,
        app_database_path=tmp_path / "app.db",
        rag_index_dir=tmp_path / "rag-index",
        graph_snapshot_dir=tmp_path / "graph",
    )
    index_version = "index-v2"
    index_dir = version_directory(settings.rag_index_dir, index_version)
    index_dir.mkdir(parents=True)
    (index_dir / "manifest.json").write_text("{}", encoding="utf-8")
    chunk = _chunk()
    write_chunk_catalog(index_dir / "chunks.jsonl", [chunk])
    entity_a = ValidatedEntity(
        canonical_name="九价HPV疫苗", entity_type="Vaccine", aliases=[],
        surface_form="九价HPV疫苗", chunk_id=chunk.id,
    )
    entity_b = ValidatedEntity(
        canonical_name="HPV16", entity_type="Pathogen", aliases=["HPV-16"],
        surface_form="HPV16", chunk_id=chunk.id,
    )
    extraction = ValidatedChunkExtraction(
        chunk_id=chunk.id,
        content_hash=chunk.content_hash or "",
        entities=[entity_a, entity_b],
        relations=[ValidatedRelation(
            source=entity_a, target=entity_b, relation_type="PREVENTS",
            evidence_quote=chunk.text, confidence=0.97, chunk_id=chunk.id,
        )],
    )
    pipeline = GraphSnapshotPipeline(
        settings,
        None,
        semantica=SemanticaGraphBuilderAdapter(
            builder=_FakeBuilder(merge_entities=False, resolve_conflicts=False)
        ),
    )

    async def fake_extract(_chunks, *, force=False, **_kwargs):
        return [extraction], {"reused_chunks": 0, "extracted_chunks": 1}

    pipeline.extractor.extract_chunks = fake_extract
    metadata = asyncio.run(pipeline.build_for_index(index_dir, index_version, mode="full"))
    activate_index(settings.rag_index_dir, index_version, metadata["graph_version"])

    with TestClient(create_app(settings)) as client:
        meta = client.get("/api/v1/knowledge-graph/meta")
        graph = client.get("/api/v1/knowledge-graph?center=九价HPV疫苗&depth=1&limit=25")
        search = client.get("/api/v1/knowledge-graph/search?q=HPV-16")
        node_id = next(
            item["id"]
            for item in graph.json()["nodes"]
            if item["label"] == "九价HPV疫苗"
        )
        detail = client.get(f"/api/v1/knowledge-graph/nodes/{node_id}")

    assert meta.status_code == 200
    assert meta.headers["cache-control"] == "no-store"
    assert graph.json()["version"] == metadata["graph_version"]
    assert {item["relation"] for item in graph.json()["edges"]} == {"PREVENTS"}
    assert search.json()["items"][0]["label"] == "HPV16"
    assert detail.json()["sources"][0]["chunk_id"] == "chunk-1"


def test_graph_jobs_deduplicate_and_claim(tmp_path: Path) -> None:
    repository = GraphJobRepository(tmp_path / "jobs.db")

    async def scenario():
        first = await repository.enqueue("rebuild", {"mode": "full"}, signature="same")
        duplicate = await repository.enqueue("rebuild", {"mode": "full"}, signature="same")
        claimed = await repository.claim(60)
        return first, duplicate, claimed

    first, duplicate, claimed = asyncio.run(scenario())
    assert duplicate.id == first.id
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempts == 1
