from pydantic import BaseModel, Field, field_validator, model_validator


class PubMedArticle(BaseModel):
    """Provider-neutral PubMed evidence used by the agent and API layers."""

    pmid: str = Field(pattern=r"^\d{1,10}$")
    title: str = Field(min_length=1, max_length=1000)
    abstract: str = Field(default="", max_length=20_000)
    authors: list[str] = Field(default_factory=list, max_length=100)
    journal: str = Field(default="", max_length=500)
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    doi: str | None = Field(default=None, max_length=500)
    publication_types: list[str] = Field(default_factory=list, max_length=50)
    url: str | None = Field(default=None, max_length=2048)

    @field_validator("pmid", "title", "abstract", "journal", mode="before")
    @classmethod
    def strip_required_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("doi", "url", mode="before")
    @classmethod
    def strip_optional_strings(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip() or None

    @field_validator("authors", "publication_types", mode="before")
    @classmethod
    def clean_string_lists(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    @model_validator(mode="after")
    def add_canonical_url(self) -> "PubMedArticle":
        if self.url is None:
            self.url = f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"
        return self
