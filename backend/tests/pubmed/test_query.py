from app.pubmed.query import build_identifier_query, extract_named_identifiers


def test_mixed_case_hyphenated_product_identifier_is_detected() -> None:
    assert extract_named_identifiers("Com-COV2 异源接种") == ["Com-COV2"]


def test_plain_lowercase_hyphenated_phrase_is_not_treated_as_a_product() -> None:
    assert build_identifier_query("请检索 meta-analysis") is None
