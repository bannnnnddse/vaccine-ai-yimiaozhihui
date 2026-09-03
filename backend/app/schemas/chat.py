from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("history content cannot be blank")
        return stripped


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatHistoryItem] = Field(default_factory=list)
    session_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question cannot be blank")
        return stripped

    @field_validator("session_id")
    @classmethod
    def strip_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("session_id cannot be blank")
        return stripped

    @model_validator(mode="after")
    def keep_recent_history(self) -> "ChatRequest":
        self.history = self.history[-10:]
        return self


class ChatSource(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    page: int | None = Field(default=None, ge=1)
    content: str = Field(min_length=1, max_length=1200)
    source_type: Literal["web", "pubmed", "curated"] | None = None
    source_title: str | None = Field(default=None, max_length=300)
    source_url: str | None = Field(default=None, max_length=2048)
    section: str | None = Field(default=None, max_length=300)
    title: str | None = Field(default=None, max_length=1000)
    pmid: str | None = Field(default=None, pattern=r"^\d{1,10}$")
    journal: str | None = Field(default=None, max_length=500)
    year: int | None = Field(default=None, ge=1800, le=2200)
    doi: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2048)
    snippet: str | None = Field(default=None, max_length=1200)

    @field_validator("file_name", "content")
    @classmethod
    def strip_source_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("source text cannot be blank")
        return stripped

    @field_validator("source_title", "section", "title", "journal", "doi", "snippet")
    @classmethod
    def strip_optional_source_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("source_url", "url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        parsed = urlparse(stripped)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an http(s) URL")
        return stripped

    @model_validator(mode="after")
    def validate_pubmed_contract(self) -> "ChatSource":
        if self.source_type == "pubmed":
            if self.page is not None:
                raise ValueError("PubMed sources cannot have a PDF page")
            if not all([self.title, self.pmid, self.url, self.snippet]):
                raise ValueError("PubMed sources require title, PMID, URL, and snippet")
        return self


class ChatResponse(BaseModel):
    answer: str
    model: str
    is_vaccine_related: bool
    session_id: str = Field(min_length=1)
    sources: list[ChatSource] = Field(default_factory=list)

    @field_validator("session_id")
    @classmethod
    def strip_session_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("session_id cannot be blank")
        return stripped


class ConversationTitleRequest(BaseModel):
    messages: list[ChatHistoryItem] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def require_user_and_assistant(self) -> "ConversationTitleRequest":
        roles = {message.role for message in self.messages}
        if roles != {"user", "assistant"}:
            raise ValueError("title messages require user and assistant content")
        return self


class ConversationTitleResponse(BaseModel):
    title: str = Field(min_length=1, max_length=60)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title cannot be blank")
        return stripped
