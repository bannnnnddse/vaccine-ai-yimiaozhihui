"""Traceable local evidence for image content; never a medical approval badge."""

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FigureSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: str = Field(pattern=r"^E[1-9]\d*$")
    chunk_id: str = Field(min_length=1, max_length=300)
    document_id: str = Field(min_length=1, max_length=300)
    file_name: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=1000)
    page: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, max_length=500)
    source_url: str | None = Field(default=None, max_length=2048)
    source_hash: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=8, max_length=2400)

    @field_validator("source_url")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        if value is not None:
            url = urlsplit(value)
            if (
                url.scheme not in {"http", "https"}
                or not url.netloc
                or url.username is not None
                or url.password is not None
            ):
                raise ValueError("evidence URL must be public HTTP(S)")
        return value


class FigureBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    target: Literal["claim", "step"]
    index: int = Field(ge=0, le=7)
    source_id: str = Field(pattern=r"^E[1-9]\d*$")
    quote: str = Field(min_length=8, max_length=600)


class FigureEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal["image_evidence_v1"] = "image_evidence_v1"
    index_version: str = Field(min_length=1, max_length=200)
    sources: list[FigureSource] = Field(min_length=1, max_length=4)
    bindings: list[FigureBinding] = Field(min_length=1, max_length=24)
    claims: list[Annotated[str, Field(min_length=4, max_length=300)]] = Field(
        min_length=1, max_length=8
    )
    steps: list[Annotated[str, Field(min_length=4, max_length=240)]] = Field(
        min_length=1, max_length=4
    )
    content_signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["sources_bound"] = "sources_bound"
    medical_review_required: Literal[True] = True
    # A separate model checks the proposed content; this is not expert approval.
    assessment_method: Literal["exact_quote_and_model_support"] = "exact_quote_and_model_support"
