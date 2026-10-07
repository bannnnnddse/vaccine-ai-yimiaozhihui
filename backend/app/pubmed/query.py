import re

_LATIN_BINOMIAL_PATTERN = re.compile(
    r"\b[A-Z][A-Za-z-]{1,}(?:\s+[a-z][A-Za-z-]{1,})+\b"
)
_PRODUCT_IDENTIFIER_PATTERN = re.compile(
    r"\b(?=[A-Za-z0-9-]*[A-Z0-9])[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b"
)


def extract_named_identifiers(query: str) -> list[str]:
    """Extract narrow biomedical/product identifiers suitable for PubMed fallback."""

    return sorted(
        {
            *(_LATIN_BINOMIAL_PATTERN.findall(query)),
            *(_PRODUCT_IDENTIFIER_PATTERN.findall(query)),
        }
    )


def build_identifier_query(query: str) -> str | None:
    identifiers = extract_named_identifiers(query)
    return " ".join(identifiers) if identifiers else None
