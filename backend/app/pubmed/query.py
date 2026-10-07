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


def is_current_illness_vaccination_question(question: str) -> bool:
    """Identify vaccination eligibility during a stated current illness."""

    original = question.splitlines()[0].replace(" ", "") if question else ""
    return (
        any(term in original for term in ("目前", "现在", "正在", "患", "得了", "感染"))
        and any(term in original for term in ("甲流", "乙流", "流感", "生病", "患病", "感染"))
        and any(term in original for term in ("疫苗", "接种", "预防针"))
        and any(
            term in original
            for term in (
                "可以吗",
                "能否",
                "能打",
                "可以打",
                "能接种",
                "可以接种",
                "可否接种",
                "适合接种",
            )
        )
        and not any(term in original for term in ("接种后", "打完疫苗", "打了疫苗后"))
    )
