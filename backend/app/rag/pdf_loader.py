from hashlib import sha256
from pathlib import Path

import pymupdf

from app.rag.models import IndexReport, PageDocument
from app.rag.text import clean_text


def load_pdf_pages(
    source_dir: Path,
    *,
    minimum_page_chars: int = 50,
) -> tuple[list[PageDocument], IndexReport]:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"RAG source directory does not exist: {source_dir}")
    report = IndexReport()
    pages: list[PageDocument] = []
    seen_hashes: set[str] = set()
    for path in sorted(source_dir.rglob("*.pdf"), key=lambda item: item.as_posix()):
        report.pdf_files_seen += 1
        source_hash = sha256(path.read_bytes()).hexdigest()
        relative_path = path.relative_to(source_dir).as_posix()
        if source_hash in seen_hashes:
            report.duplicate_pdf_files.append(relative_path)
            continue
        seen_hashes.add(source_hash)
        report.unique_pdf_files += 1
        try:
            with pymupdf.open(path) as document:
                report.pages_seen += document.page_count
                for page_index, page in enumerate(document):
                    text = clean_text(page.get_text("text", sort=True))
                    page_number = page_index + 1
                    if len(text) < minimum_page_chars:
                        message = (
                            f"{relative_path} 第{page_number}页文本不足"
                            f"{minimum_page_chars}字符，已跳过"
                        )
                        report.warnings.append(message)
                        continue
                    pages.append(PageDocument(
                        file_name=path.name,
                        relative_path=relative_path,
                        page=page_number,
                        text=text,
                        source_hash=source_hash,
                    ))
                    report.pages_indexed += 1
        except pymupdf.FileDataError:
            report.warnings.append(f"{relative_path} 无法解析，已跳过")
    return pages, report
