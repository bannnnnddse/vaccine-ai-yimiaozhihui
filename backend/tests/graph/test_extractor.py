from app.graph.extractor import RuleGraphExtractor


def _triples(text: str) -> set[tuple[str, str, str]]:
    return {
        (item.source.canonical_name, item.relation_type, item.target.canonical_name)
        for item in RuleGraphExtractor().extract_relations(text)
    }


def test_extracts_compact_hpv_prevention_targets() -> None:
    triples = _triples("九价 HPV 疫苗可预防 HPV16、18 感染。")

    assert ("九价HPV疫苗", "PREVENTS", "HPV16") in triples
    assert ("九价HPV疫苗", "PREVENTS", "HPV18") in triples


def test_preserves_decreased_risk_semantics() -> None:
    triples = _triples("HPV 疫苗可降低 HPV16 感染风险。")

    assert triples == {("HPV疫苗", "DECREASES_RISK", "HPV16")}


def test_does_not_invent_relation_from_cooccurrence() -> None:
    assert _triples("HPV 疫苗与宫颈癌是常见科普主题。") == set()
    assert all(item[1] != "related_to" for item in _triples("B 细胞和抗体。"))


def test_rejects_population_self_loop_from_prevention_noun_phrase() -> None:
    text = "监护人携带儿童的疫苗预防接种登记卡建立儿童预防接种证。"

    assert _triples(text) == set()


def test_rejects_population_to_vaccine_schedule_false_positive() -> None:
    text = "儿童可按照免疫程序接种乙肝疫苗等非减毒活疫苗。"

    assert _triples(text) == set()


def test_exact_aliases_resolve_to_one_canonical_entity() -> None:
    mentions = RuleGraphExtractor().extract_entities("HPV疫苗与人乳头瘤病毒疫苗")

    assert {item.definition.canonical_name for item in mentions} == {"HPV疫苗"}
