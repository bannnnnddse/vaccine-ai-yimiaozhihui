from __future__ import annotations

import re

from app.graph.models import EntityDefinition, EntityMention, ExtractedRelation, RelationType
from app.graph.vocabulary import ENTITY_DEFINITIONS

EXTRACTION_RULES_VERSION = "vaccine_rules_v2"
_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？；;，\n])")
_RELATION_PATTERNS: tuple[tuple[RelationType, re.Pattern[str], float], ...] = (
    ("PREVENTS", re.compile(r"(?:可|能够|能|用于)?预防|防止"), 0.98),
    ("CAUSES", re.compile(r"导致|引起|造成"), 0.96),
    ("CAN_PROGRESS_TO", re.compile(r"可(?:能)?进展为|可发展为|演变为"), 0.96),
    ("INDICATED_FOR", re.compile(r"适用于|推荐用于|建议用于"), 0.94),
    ("HAS_SCHEDULE", re.compile(r"接种程序(?:为|是)|按照.+程序接种"), 0.94),
    ("HAS_CONTRAINDICATION", re.compile(r"禁忌|不应接种|不能接种"), 0.96),
    ("ACTIVATES", re.compile(r"激活|活化"), 0.96),
    ("PRODUCES", re.compile(r"产生|分泌"), 0.96),
    ("NEUTRALIZES", re.compile(r"中和|清除"), 0.94),
    ("INCREASES_RISK", re.compile(r"增加.+风险|风险增加"), 0.96),
    ("DECREASES_RISK", re.compile(r"降低.+风险|减少.+风险|风险降低"), 0.96),
)


class RuleGraphExtractor:
    """High-precision domain rules. It intentionally has no co-occurrence fallback."""

    def __init__(self, definitions: tuple[EntityDefinition, ...] = ENTITY_DEFINITIONS) -> None:
        self._definitions = definitions
        self._aliases = sorted(
            (
                (alias, definition)
                for definition in definitions
                for alias in definition.aliases
            ),
            key=lambda item: (-len(_normalize(item[0])), item[0]),
        )

    def extract_entities(self, text: str) -> list[EntityMention]:
        normalized = _normalize(text)
        mentions: list[EntityMention] = []
        occupied: list[tuple[int, int]] = []
        for alias, definition in self._aliases:
            normalized_alias = _normalize(alias)
            for match in re.finditer(re.escape(normalized_alias), normalized, re.IGNORECASE):
                span = match.span()
                if any(span[0] < end and span[1] > start for start, end in occupied):
                    continue
                mentions.append(EntityMention(definition, match.group(), span[0], span[1]))
                occupied.append(span)
        return sorted(
            mentions,
            key=lambda item: (item.start, item.end, item.definition.canonical_name),
        )

    def extract_relations(self, text: str) -> list[ExtractedRelation]:
        relations: list[ExtractedRelation] = []
        for sentence in _sentences(text):
            mentions = self.extract_entities(sentence)
            if len(mentions) < 2:
                relations.extend(self._extract_compact_hpv_targets(sentence, mentions))
                continue
            for source_index, source in enumerate(mentions):
                for target in mentions[source_index + 1 :]:
                    between = _normalize(sentence)[source.end : target.start]
                    suffix = _normalize(sentence)[target.end :]
                    match = _match_relation(between, suffix)
                    if match is None:
                        continue
                    relation_type, confidence = match
                    source_definition = source.definition
                    target_definition = target.definition
                    if (
                        relation_type == "HAS_CONTRAINDICATION"
                        and source_definition.entity_type == "Population"
                        and target_definition.entity_type == "Vaccine"
                    ):
                        source_definition, target_definition = (
                            target_definition,
                            source_definition,
                        )
                    if not _valid_relation_types(
                        relation_type,
                        source_definition.entity_type,
                        target_definition.entity_type,
                    ):
                        continue
                    relations.append(
                        ExtractedRelation(
                            source=source_definition,
                            target=target_definition,
                            relation_type=relation_type,
                            confidence=confidence,
                            quote=sentence.strip(),
                        )
                    )
            relations.extend(self._extract_compact_hpv_targets(sentence, mentions))
        unique: dict[tuple[str, str, str, str], ExtractedRelation] = {}
        for relation in relations:
            key = (
                relation.source.canonical_name,
                relation.relation_type,
                relation.target.canonical_name,
                relation.quote,
            )
            unique.setdefault(key, relation)
        return list(unique.values())

    @staticmethod
    def _extract_compact_hpv_targets(
        sentence: str,
        mentions: list[EntityMention],
    ) -> list[ExtractedRelation]:
        vaccine = next(
            (item.definition for item in mentions if item.definition.entity_type == "Vaccine"),
            None,
        )
        compact = re.search(
            r"(?:可|能够|能)?(?P<verb>预防|降低)(?:感染)?(?:\s*)HPV\s*16[、,，/和及\s]+(?:HPV\s*)?18(?:型)?(?:感染)?(?:的)?(?P<risk>风险)?",
            sentence,
            re.IGNORECASE,
        )
        if vaccine is None or compact is None:
            return []
        decreases_risk = compact.group("verb") == "降低" or compact.group("risk")
        relation_type: RelationType = "DECREASES_RISK" if decreases_risk else "PREVENTS"
        definitions = {item.canonical_name: item for item in ENTITY_DEFINITIONS}
        return [
            ExtractedRelation(vaccine, definitions[target], relation_type, 0.98, sentence.strip())
            for target in ("HPV16", "HPV18")
        ]


def _match_relation(text: str, suffix: str = "") -> tuple[RelationType, float] | None:
    if "降低" in text and "风险" in suffix:
        return "DECREASES_RISK", 0.96
    if "增加" in text and "风险" in suffix:
        return "INCREASES_RISK", 0.96
    for relation_type, pattern, confidence in _RELATION_PATTERNS:
        if pattern.search(text):
            return relation_type, confidence
    return None


def _valid_relation_types(
    relation_type: RelationType,
    source_type: str,
    target_type: str,
) -> bool:
    allowed: dict[RelationType, set[tuple[str, str]]] = {
        "PREVENTS": {("Vaccine", "Disease"), ("Vaccine", "Pathogen")},
        "CAUSES": {
            ("Pathogen", "Disease"),
            ("Vaccine", "AdverseEvent"),
            ("ImmuneEntity", "AdverseEvent"),
        },
        "CAN_PROGRESS_TO": {("Pathogen", "Disease"), ("Disease", "Disease")},
        "INDICATED_FOR": {("Vaccine", "Population")},
        "HAS_SCHEDULE": {("Vaccine", "Schedule")},
        "HAS_CONTRAINDICATION": {("Vaccine", "Population")},
        "ACTIVATES": {
            ("Vaccine", "ImmuneEntity"),
            ("Pathogen", "ImmuneEntity"),
            ("ImmuneEntity", "ImmuneEntity"),
        },
        "PRODUCES": {("ImmuneEntity", "ImmuneEntity")},
        "NEUTRALIZES": {
            ("ImmuneEntity", "Pathogen"),
            ("ImmuneEntity", "Disease"),
        },
        "INCREASES_RISK": {
            ("Pathogen", "Disease"),
            ("ImmuneEntity", "Disease"),
            ("ImmuneEntity", "Pathogen"),
            ("Population", "Disease"),
        },
        "DECREASES_RISK": {
            ("Vaccine", "Disease"),
            ("Vaccine", "Pathogen"),
            ("ImmuneEntity", "Disease"),
            ("Population", "Disease"),
        },
    }
    return (source_type, target_type) in allowed[relation_type]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in _SENTENCE_BOUNDARY.split(text) if item.strip()]
