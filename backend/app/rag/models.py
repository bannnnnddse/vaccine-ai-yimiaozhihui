from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PageDocument:
    file_name: str
    relative_path: str
    page: int | None
    text: str
    source_hash: str
    source_type: str = "pdf"
    corpus_source_type: str = "unknown"
    source_title: str | None = None
    source_url: str | None = None
    section: str | None = None
    doc_id: str | None = None
    title: str | None = None
    section_path: tuple[str, ...] = ()
    authority_level: int = 0
    evidence_level: str = "unknown"
    publication_date: str | None = None
    publication_year: int | None = None
    effective_date: str | None = None
    version: str = "unknown"
    is_superseded: bool = False
    block_index: int = 0
    block_type: str = "text"
    atomic: bool = False


@dataclass(frozen=True, slots=True)
class TextChunk:
    id: str
    file_name: str
    relative_path: str
    page: int | None
    chunk_index: int
    text: str
    source_hash: str
    source_type: str = "pdf"
    corpus_source_type: str = "unknown"
    source_title: str | None = None
    source_url: str | None = None
    section: str | None = None
    parent_doc_id: str | None = None
    section_path: tuple[str, ...] = ()
    content_hash: str | None = None
    title: str | None = None
    authority_level: int = 0
    evidence_level: str = "unknown"
    publication_date: str | None = None
    publication_year: int | None = None
    effective_date: str | None = None
    version: str = "unknown"
    is_superseded: bool = False
    embedding_text: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievedChunk(TextChunk):
    similarity: float = 0.0
    dense_rank: int | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
    rrf_score: float | None = None
    fused_rank: int | None = None
    reranker_score: float | None = None
    relevance_score: float | None = None
    quality_adjustment: float = 0.0
    final_score: float | None = None
    final_rank: int | None = None


@dataclass(frozen=True, slots=True)
class RagSource:
    file_name: str
    page: int | None
    content: str
    source_type: str = "pdf"
    source_title: str | None = None
    source_url: str | None = None
    section: str | None = None
    document_id: str | None = field(default=None, compare=False)
    pages: tuple[int, ...] = field(default=(), compare=False)


@dataclass(slots=True)
class IndexReport:
    pdf_files_seen: int = 0
    unique_pdf_files: int = 0
    duplicate_pdf_files: list[str] = field(default_factory=list)
    pages_seen: int = 0
    pages_indexed: int = 0
    chunks_indexed: int = 0
    markdown_files_seen: int = 0
    unique_markdown_files: int = 0
    duplicate_markdown_files: list[str] = field(default_factory=list)
    markdown_sections_indexed: int = 0
    docling_files_seen: int = 0
    docling_files_loaded: int = 0
    docx_files_seen: int = 0
    docx_sections_indexed: int = 0
    documents_skipped_review: int = 0
    warnings: list[str] = field(default_factory=list)
