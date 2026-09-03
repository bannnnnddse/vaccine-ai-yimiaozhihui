"""Organize public-health and biomedical prompts into a strict visual dossier."""

from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal
from math import isfinite
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit, urlunsplit

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
)
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.core.config import Settings
from app.schemas.knowledge_image import ScienceImageType
from app.schemas.science_figure import ChineseFigureBrief, primary_relation_of
from app.services.cell_ip_assets import CellIpAssetService

Verification = Literal["verified", "candidate"]
FallbackModuleKind = Literal[
    "fact_cards",
    "symptom_cards",
    "mechanism",
    "timeline",
    "medical_advice",
]

_IMAGE_TYPES = {
    "science_poster",
    "graphical_abstract",
    "mechanism_diagram",
}
_CELL_IP_EXPLICIT_REQUEST = re.compile(
    r"细胞\s*IP|IP\s*角色|固定(?:细胞)?角色|手绘(?:细胞|角色|IP)|正文配图",
    re.IGNORECASE,
)
_CELL_IP_SCIENTIFIC_REQUEST = re.compile(
    r"机制图|流程图|图形摘要|因果链|箭头|分区|科研|学术|论文|严谨"
)
_CELL_IP_EDITORIAL_REQUEST = re.compile(r"正文配图|文章配图|(?:手绘)?插画")
_CELLULAR_SUBJECT_REQUEST = re.compile(
    r"细胞|病毒|抗原|抗体|免疫球蛋白|\b(?:cell|virus|antigen|antibody|immunoglobulin)s?\b",
    re.IGNORECASE,
)
_DEFAULT_FACTS_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "verified_visual_facts.json"
)

# Length limits for a readable public-health scientific diagram.
#
# Module-level constraints keep visual labels compact:
#   fact_cards / symptom_cards / medical_advice → items on separate lines
#   mechanism → " → ".join(items), wrapped
#   timeline  → " · ".join(items), wrapped
# The total character budget per module prevents the wrapped text from
# overflowing the registered text-box height even at the minimum 24px font.
_MAX_TITLE_CHARS = 10
_MAX_SUMMARY_CHARS = 32
_MAX_VISUAL_SUBJECT_CHARS = 18
_MAX_FACT_CHARS = 20
_MAX_MODULE_TITLE_CHARS = 10
_MAX_MODULE_ITEM_CHARS = 12
_MAX_MODULE_ITEMS = 3
# Sum of all item char lengths (excluding renderer joiners).
# For mechanism (→) and timeline (·) this is the raw item text total.
_MAX_MODULE_TEXT_BUDGET = 36

ORGANIZER_SYSTEM_PROMPT = """你是公共卫生与生物医学科学图像的内容整理器。输出的文字会渲染到
1200×1600 像素的科学图解画布上，因此必须严格控制长度。

**严格长度限制：**
- title：≤10 字符（科普海报的简洁大标题）
- summary：≤32 字符（一行副标题）
- visual_subject：≤18 字符（画面主体的关键词描述）
- facts 每条：≤20 字符，最多 4 条
- fallback_modules 每个模块 { title: ≤10, items 每条: ≤12, items 数量: ≤3 }

**模块总文本预算（极其重要）：**
每个模块的所有 items 字符数之和（不含渲染器添加的分隔符）不得超过 36 字符。
超限会被硬截断，可能破坏医学含义。请主动压缩：

优先级：
1. 减少 items 数量（保留最关键的 1-2 条）
2. 压缩每条 item 表达（保持含义，削除修饰）
   例："树突状细胞摄取抗原后迁移至淋巴结并通过MHC分子呈递给辅助性T细胞"
   压缩为："树突细胞呈递抗原激活T细胞"
3. 句子边界截断（最后手段）

**其他规则：**
输入会明确给出用户已经选择的图像类型。必须原样采用该类型，不得根据自然语言猜测或改写类型。
主题范围包括公共卫生、流行病学、疫苗、免疫学和其他生物医学科学传播。无需询问主题是否属于疫苗问题；
但如果内容明显无关（例如菜谱、娱乐或编程），将 in_scope 设为 false。

只整理用于后续可视化的科学素材，不生成面向用户的问答回复。不得提供个体诊断、处方或接种决策。
不得虚构精确数字、比例、时间、样本量或来源。仅当输入明确支持某个数字时，才可把它列为
data_candidates；每项都必须保留 label、value、unit、scope、source。候选数字不得声称已核验。
无论是否有数字，in_scope 为 true 时都要提供至少三个非数据 fallback_modules。

只能输出一个合法 JSON 对象，不得输出 Markdown、代码围栏或 JSON 外文字。对象必须且只能包含：
in_scope, title, summary, facts, visual_subject, fallback_modules, data_candidates。
fallback_modules 每项必须且只能包含 kind, title, items；kind 只能是 fact_cards、symptom_cards、
mechanism、timeline、medical_advice。data_candidates 每项必须且只能包含 label、value、unit、
scope、source，不得包含 verification。若 in_scope 为 false，其余字段使用空字符串或空数组。"""

CHINESE_FAST_ROUTE_SYSTEM_PROMPT = """你是公共卫生与生物医学科学图解的策划器。
将用户的中文主题整理成一个可直接交给图像生成器的严格 JSON 对象。只输出 JSON，不要
输出 Markdown、代码围栏或任何额外说明。对象必须且只能包含以下键：image_type、
 generation_route、visual_profile、scene_direction、optimized_chinese_prompt、chinese_labels、scientific_claims、
core_causal_steps、route_reason。

image_type 必须是 science_poster、graphical_abstract 或 mechanism_diagram 之一，并选择
最适合主题的类型。generation_route 必须为 "fast"。
route_reason 要用简短中文说明该选择。
visual_profile 必须固定为 "scientific_diagram"。

optimized_chinese_prompt 必须是完整、可执行的中文生成提示词：明确要求 9:16 竖版画幅，
所有可读文字均使用简体中文，包含简短且醒目的中文大标题，并以与 core_causal_steps 完全
一致的因果顺序安排画面。描述必要的对象、关系、视觉层级和可读中文标签；不要为了画面
完整而补充 core_causal_steps 未支持的分子连接或机制。

chinese_labels 为 1 至 8 个简短、可读的简体中文标签；scientific_claims 为 1 至 8 条
简洁的中文科学表述。core_causal_steps 为按因果顺序排列的 1 至 4 个对象，每个对象必须
且只能包含 primary_relation，使用完整中文描述一个不可再分的科学关系。不得虚构或强化
未获输入支持的因果主张，不得给出疗效保证，不得编造或使用无来源的精确数值、百分比、
日期或其他定量事实。不要输出诊断、处方或个体化接种建议。"""

CELL_IP_ROUTE_SYSTEM_PROMPT = """你是公共卫生与生物医学科学图解的策划器。系统已安装可选的
固定细胞 IP 视觉资产，但不能因此降低科学关系的完整性。
将用户的中文主题整理成一个可直接交给图像生成器的严格 JSON 对象。只输出 JSON，不要
输出 Markdown、代码围栏或任何额外说明。对象必须且只能包含以下键：image_type、
 generation_route、visual_profile、scene_direction、optimized_chinese_prompt、chinese_labels、scientific_claims、
core_causal_steps、route_reason。

image_type 必须是 science_poster、graphical_abstract 或 mechanism_diagram 之一；
generation_route 必须为 fast。

visual_profile 必须从以下三项选择：
- scientific_diagram：仅用于不涉及细胞、病毒、抗原或抗体的普通机制图、海报、图形摘要。
  要求 9:16 竖版、必要标题、清楚标签，并按 core_causal_steps 完整安排箭头、编号或分区。
- cell_ip_editorial：仅当用户明确要求固定细胞 IP、手绘角色或正文配图，且内容不超过两个核心
  关系时使用。要求 16:9 横版单场景、极少量手写批注、较多留白，不要标题。
- cell_ip_scientific：细胞、病毒、抗原或抗体相关主题的默认模式；也用于明确要求固定 IP 的
  机制图/流程/三个以上关系/严谨表达。要求 16:9 横版，允许必要标题、编号、箭头、流程和分区，
  逐条覆盖 core_causal_steps。

optimized_chinese_prompt 必须与所选 visual_profile 相容。无论选择哪种 profile，都只选择科学
关系真正需要的细胞或分子角色，不得因存在角色资产而添加未获输入支持的细胞、分子连接、
机制、结论或疗效暗示，也不得为了留白或故事感删减 core_causal_steps。

chinese_labels 为 1 至 8 个简短标签；scientific_claims 为 1 至 8 条简洁科学表述；
core_causal_steps 为按因果顺序排列的 1 至 4 个对象，每个对象只能包含 primary_relation。
不得虚构精确数字、百分比、日期、诊断、处方或个体化接种建议。"""

_LOCKED_IP_REFINER_RULES = """

【锁定角色契约】
以下实体已由应用程序绑定到 canonical IP。它们的外观不属于你的输出权限：
{locked_entities}
对每个锁定实体，只能在 scene_direction、因果关系和标签中描述其语义角色、动作、位置、朝向、
大小、交互与科学过程。不得描述、重述或改写其颜色、轮廓、形状、面部、刺突/表面结构、服饰、
专属道具、比例或其他身份特征；不得把用户提供的冲突外观要求写回输出。
scene_direction 只能写场景和构图关系，不能写任何锁定实体的外观。
"""


class ScienceImageOrganizerError(Exception):
    """Safe base error for organizer failures."""


class ScienceImageScopeError(ScienceImageOrganizerError):
    """The requested content is outside the supported scientific scope."""


class ScienceImageNotConfiguredError(ScienceImageOrganizerError):
    """The model client or API key is unavailable."""


class FallbackModule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: FallbackModuleKind
    title: str
    items: list[str]

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("fallback module title cannot be blank")
        return value

    @field_validator("items")
    @classmethod
    def validate_items(cls, value: list[str]) -> list[str]:
        items = [item.strip() for item in value]
        if not items or any(not item for item in items):
            raise ValueError("fallback module items cannot be empty")
        return items


class _RawDataCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    label: str
    value: float | None = None
    unit: str
    scope: str
    source: str

    @field_validator("label", "unit", "scope", "source")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("label")
    @classmethod
    def require_label(cls, value: str) -> str:
        if not value:
            raise ValueError("data label cannot be blank")
        return value

    @field_validator("value")
    @classmethod
    def require_finite_value(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("data value must be finite")
        return value


class DataCandidate(_RawDataCandidate):
    verification: Verification = "candidate"

    @property
    def is_renderable(self) -> bool:
        return (
            self.verification == "verified"
            and self.value is not None
            and isfinite(self.value)
            and bool(self.scope)
        )


class _VerifiedVisualFact(_RawDataCandidate):
    value: float

    @field_validator("label", "unit", "scope", "source")
    @classmethod
    def require_identity_fields(cls, value: str) -> str:
        if not value:
            raise ValueError("verified fact identity fields cannot be blank")
        return value


class _OrganizerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    in_scope: bool
    title: str
    summary: str
    facts: list[str]
    visual_subject: str
    fallback_modules: list[FallbackModule]
    data_candidates: list[_RawDataCandidate]


class ScienceDossier(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    image_type: ScienceImageType
    title: str
    summary: str
    facts: list[str]
    visual_subject: str
    fallback_modules: list[FallbackModule]
    data_candidates: list[DataCandidate]


class ScienceImageOrganizer:
    def __init__(
        self,
        settings: Settings,
        client: AsyncOpenAI | None,
        *,
        verified_facts_path: Path | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._cell_ip_assets = (
            CellIpAssetService(settings.cell_ip_skill_dir)
            if settings.cell_ip_enabled
            else None
        )
        self._verified_facts = _load_verified_facts(
            verified_facts_path or _DEFAULT_FACTS_PATH
        )

    async def organize(
        self,
        image_type: ScienceImageType,
        prompt: str,
    ) -> ScienceDossier:
        if image_type not in _IMAGE_TYPES:
            raise ValueError("unknown science image type")

        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            raise ValueError("prompt cannot be blank")
        if len(normalized_prompt) > 2000:
            raise ValueError("prompt cannot exceed 2000 characters")

        if self._client is None or not self._settings.dashscope_api_key:
            raise ScienceImageNotConfiguredError

        messages = [
            {"role": "system", "content": ORGANIZER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"已选择图像类型：{image_type}\n用户主题：{normalized_prompt}",
            },
        ]
        try:
            response = await self._client.chat.completions.create(
                model=self._settings.qwen_lightweight_model,
                messages=messages,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
        except (
            AuthenticationError,
            APITimeoutError,
            APIConnectionError,
            APIStatusError,
            APIError,
        ) as exc:
            raise ScienceImageOrganizerError from exc

        try:
            raw_content = response.choices[0].message.content
            if not isinstance(raw_content, str) or not raw_content:
                raise ValueError("empty organizer response")
            decoded = json.loads(raw_content, parse_constant=_reject_json_constant)
            organized = _OrganizerResponse.model_validate(decoded)
        except (
            json.JSONDecodeError,
            ValidationError,
            TypeError,
            ValueError,
            AttributeError,
            IndexError,
        ) as exc:
            raise ScienceImageOrganizerError from exc

        if not organized.in_scope:
            raise ScienceImageScopeError
        _validate_scientific_content(organized)
        organized = _compress_dossier(organized)

        try:
            candidates = [
                DataCandidate(
                    **candidate.model_dump(),
                    verification=(
                        "verified" if self._is_verified(candidate) else "candidate"
                    ),
                )
                for candidate in organized.data_candidates
            ]
        except ValueError as exc:
            raise ScienceImageOrganizerError("invalid organizer data candidate") from exc
        return ScienceDossier(
            image_type=cast(ScienceImageType, image_type),
            title=organized.title.strip(),
            summary=organized.summary.strip(),
            facts=[fact.strip() for fact in organized.facts],
            visual_subject=organized.visual_subject.strip(),
            fallback_modules=organized.fallback_modules,
            data_candidates=candidates,
        )

    async def refine(self, prompt: str) -> ChineseFigureBrief:
        """Route one request and produce a Chinese dynamic-image brief.

        ``organize`` is retained only until Task 5 moves the job manager to
        this prompt-only path.
        """
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            raise ValueError("prompt cannot be blank")
        if len(normalized_prompt) > 2000:
            raise ValueError("prompt cannot exceed 2000 characters")
        if self._client is None or not self._settings.dashscope_api_key:
            raise ScienceImageNotConfiguredError
        locked_role_ids = (
            [role.id for role in self._cell_ip_assets.match_roles(normalized_prompt)]
            if self._cell_ip_assets is not None
            else []
        )
        system_prompt = (
            CELL_IP_ROUTE_SYSTEM_PROMPT
            if self._settings.cell_ip_enabled
            else CHINESE_FAST_ROUTE_SYSTEM_PROMPT
        )
        if locked_role_ids and self._cell_ip_assets is not None:
            system_prompt += _locked_ip_refiner_rules(
                self._cell_ip_assets.roles_for_ids(locked_role_ids)
            )

        try:
            response = await self._client.chat.completions.create(
                model=self._settings.qwen_lightweight_model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {"role": "user", "content": normalized_prompt},
                ],
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
        except (
            AuthenticationError,
            APITimeoutError,
            APIConnectionError,
            APIStatusError,
            APIError,
        ) as exc:
            raise ScienceImageOrganizerError from exc

        try:
            raw_content = response.choices[0].message.content
            if not isinstance(raw_content, str) or not raw_content:
                raise ValueError("empty refiner response")
            decoded = _normalise_chinese_brief_payload(
                json.loads(raw_content, parse_constant=_reject_json_constant)
            )
            brief = ChineseFigureBrief.model_validate(decoded)
        except (
            json.JSONDecodeError,
            ValidationError,
            TypeError,
            ValueError,
            AttributeError,
            IndexError,
        ) as exc:
            raise ScienceImageOrganizerError from exc

        explicit_ip = bool(_CELL_IP_EXPLICIT_REQUEST.search(normalized_prompt))
        cellular_subject = _has_cellular_subject(normalized_prompt, brief)
        editorial_request = bool(_CELL_IP_EDITORIAL_REQUEST.search(normalized_prompt))
        scientific_request = bool(_CELL_IP_SCIENTIFIC_REQUEST.search(normalized_prompt))
        if not self._settings.cell_ip_enabled or not (explicit_ip or cellular_subject):
            brief = brief.model_copy(update={"visual_profile": "scientific_diagram"})
        elif (
            explicit_ip
            and editorial_request
            and len(brief.core_causal_steps) <= 2
            and not scientific_request
        ):
            brief = brief.model_copy(update={"visual_profile": "cell_ip_editorial"})
        else:
            brief = brief.model_copy(update={"visual_profile": "cell_ip_scientific"})
        if self._settings.cell_ip_enabled:
            # The refiner often introduces roles the raw user prompt never named
            # (e.g. "水痘疫苗机制图" → 树突状/辅助性T/记忆B). Re-match the brief's
            # structured fields (labels, claims, causal steps) and union the two
            # sets. This is safe: the refiner is barred from writing appearance,
            # and match_roles can only resolve manifest aliases, never invent a
            # governed identity. Only the final governable set is locked.
            brief_roles = (
                [
                    role.id
                    for role in self._cell_ip_assets.match_roles(_brief_match_text(brief))
                ]
                if self._cell_ip_assets is not None
                else []
            )
            locked_role_ids = _merge_role_ids(locked_role_ids, brief_roles)
            brief = brief.model_copy(update={"governed_role_ids": locked_role_ids})
        return brief

    def _is_verified(self, candidate: _RawDataCandidate) -> bool:
        key = _fact_key(candidate)
        return any(_fact_key(fact) == key for fact in self._verified_facts)


def _has_cellular_subject(prompt: str, brief: ChineseFigureBrief) -> bool:
    """Keep IP routing deterministic after the model returns its structured brief."""
    text = "\n".join(
        [
            prompt,
            brief.optimized_chinese_prompt,
            *brief.chinese_labels,
            *brief.scientific_claims,
            *(primary_relation_of(step) for step in brief.core_causal_steps),
        ]
    )
    return bool(_CELLULAR_SUBJECT_REQUEST.search(text))


def _brief_match_text(brief: ChineseFigureBrief) -> str:
    """Structured refiner output used to resolve governed roles post-refinement."""
    return "\n".join(
        [
            *brief.chinese_labels,
            *brief.scientific_claims,
            *(primary_relation_of(step) for step in brief.core_causal_steps),
        ]
    )


def _merge_role_ids(*groups: list[str]) -> list[str]:
    """Union role ID groups preserving first-mention order and dropping duplicates."""
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for role_id in group:
            if role_id not in seen:
                seen.add(role_id)
                merged.append(role_id)
    return merged


def _locked_ip_refiner_rules(roles: list[object]) -> str:
    entries = []
    for role in roles:
        name = getattr(role, "name", "")
        role_id = getattr(role, "id", "")
        entries.append(
            f'- {{"entity":"{name}","asset_id":"{role_id}",'
            '"visual_authority":"LOCKED",'
            '"allowed_fields":["action","position","orientation","scale","interaction"]}'
        )
    return _LOCKED_IP_REFINER_RULES.format(locked_entities="\n".join(entries))


def _normalise_chinese_brief_payload(payload: object) -> object:
    """Repair common model JSON shape drift before strict brief validation."""
    if not isinstance(payload, dict):
        return payload

    raw_steps = payload.get("core_causal_steps")
    normalised_steps: list[dict[str, str]] = []
    if isinstance(raw_steps, list):
        for item in raw_steps:
            if isinstance(item, dict):
                relation = item.get("primary_relation")
            elif isinstance(item, str):
                relation = item.removeprefix("primary_relation:")
            else:
                continue
            if isinstance(relation, str) and relation.strip():
                normalised_steps.append({"primary_relation": relation.strip()})

    if not normalised_steps:
        claims = payload.get("scientific_claims")
        if isinstance(claims, list):
            normalised_steps = [
                {"primary_relation": claim.strip()}
                for claim in claims
                if isinstance(claim, str) and claim.strip()
            ]
    if normalised_steps:
        payload["core_causal_steps"] = normalised_steps[:4]
    # Older model instructions may still emit the retired route. Normalizing
    # it preserves the response contract while keeping Wan exclusive.
    payload["generation_route"] = "fast"
    scene_direction = payload.get("scene_direction")
    if not isinstance(scene_direction, str):
        payload["scene_direction"] = ""
    return payload


def _compress_dossier(response: _OrganizerResponse) -> _OrganizerResponse:
    """Post-process the organizer output to fit a readable diagram.

    The system prompt asks the model to respect length limits, but Qwen
    may overshoot.  This function is a safety net that applies:

    1. Per-field character limits (hard truncation)
    2. Module-level text budget (smart compression with 3-tier strategy)
    """

    def _trim(text: str, limit: int) -> str:
        stripped = text.strip()
        if len(stripped) <= limit:
            return stripped
        candidate = stripped[:limit]
        for i in range(len(candidate) - 1, max(len(candidate) - 10, -1), -1):
            if candidate[i] in "。！？.!?；;）」』)":
                return candidate[: i + 1]
        return candidate

    response.title = _trim(response.title, _MAX_TITLE_CHARS)
    response.summary = _trim(response.summary, _MAX_SUMMARY_CHARS)
    response.visual_subject = _trim(
        response.visual_subject, _MAX_VISUAL_SUBJECT_CHARS
    )
    response.facts = [_trim(f, _MAX_FACT_CHARS) for f in response.facts[:4]]

    response.fallback_modules = [
        _compress_module(module) for module in response.fallback_modules
    ]
    return response


def _compress_module(module: FallbackModule) -> FallbackModule:
    """Compress a single fallback module to fit the diagram text budget.

    Strategy (in priority order):
      1. Reduce item count (keep most important, max 3)
      2. Compress individual items (hard truncate at limit)
      3. Check total budget — if still over, reduce items further
    """
    title = module.title.strip()
    if len(title) > _MAX_MODULE_TITLE_CHARS:
        candidate = title[:_MAX_MODULE_TITLE_CHARS]
        for i in range(len(candidate) - 1, max(len(candidate) - 6, -1), -1):
            if candidate[i] in "。！？.!?；;）」』)":
                candidate = candidate[: i + 1]
                break
        title = candidate

    items = [item.strip() for item in module.items if item.strip()]

    # Step 1: truncate to max item count
    items = items[:_MAX_MODULE_ITEMS]

    # Step 2: compress individual items to max length
    items = [_trim_item(item, _MAX_MODULE_ITEM_CHARS) for item in items]

    # Step 3: enforce total text budget
    items = _enforce_text_budget(items, _MAX_MODULE_TEXT_BUDGET)

    return FallbackModule(kind=module.kind, title=title, items=items)


def _trim_item(text: str, limit: int) -> str:
    """Compress a single item with sentence-boundary awareness."""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    candidate = stripped[:limit]
    for i in range(len(candidate) - 1, max(len(candidate) - 8, -1), -1):
        if candidate[i] in "。！？.!?；;）」』)，,、":
            return candidate[: i + 1] if candidate[i] in "。！？.!?）」』)" else candidate[:i]
    return candidate


def _enforce_text_budget(items: list[str], budget: int) -> list[str]:
    """Ensure the sum of item char lengths fits within the budget.

    Priority: keep items meaningful by dropping non-essential ones before
    hard-truncating individual items further.
    """
    if not items:
        return items

    total = sum(len(item) for item in items)
    if total <= budget:
        return items

    # Step 3a: drop items from the end until budget fits (but keep at least 1)
    while len(items) > 1 and sum(len(item) for item in items) > budget:
        items = items[:-1]

    # Step 3b: if still over budget, truncate last item
    total = sum(len(item) for item in items)
    if total > budget and items:
        available = budget - sum(len(item) for item in items[:-1])
        if available > 0 and len(items) >= 1:
            items[-1] = _trim_item(items[-1], available)
        items = [item for item in items if item]

    return items


def _validate_scientific_content(response: _OrganizerResponse) -> None:
    if not response.title.strip():
        raise ScienceImageOrganizerError("organizer title cannot be blank")
    if not response.summary.strip():
        raise ScienceImageOrganizerError("organizer summary cannot be blank")
    if not response.visual_subject.strip():
        raise ScienceImageOrganizerError("visual subject cannot be blank")
    if not response.facts or any(not fact.strip() for fact in response.facts):
        raise ScienceImageOrganizerError("organizer facts cannot be empty")
    if len(response.fallback_modules) < 3:
        raise ScienceImageOrganizerError(
            "organizer requires at least three non-data fallbacks"
        )


def _load_verified_facts(path: Path) -> tuple[_VerifiedVisualFact, ...]:
    try:
        decoded = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant
        )
        if not isinstance(decoded, list):
            raise TypeError("verified fact pack must be a JSON array")
        return tuple(_VerifiedVisualFact.model_validate(item) for item in decoded)
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise ScienceImageOrganizerError("invalid verified visual fact pack") from exc


def _fact_key(
    fact: _RawDataCandidate,
) -> tuple[str, Decimal | None, str, str, str]:
    return (
        _normalize_identity_text(fact.label),
        _normalize_number(fact.value),
        _normalize_unit(fact.unit),
        _normalize_identity_text(fact.scope),
        _normalize_source(fact.source),
    )


def _normalize_whitespace(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split())


def _normalize_identity_text(value: str) -> str:
    return _normalize_whitespace(value).casefold()


def _normalize_number(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).normalize()


def _normalize_unit(value: str) -> str:
    return _normalize_whitespace(value)


def _normalize_source(value: str) -> str:
    normalized = _normalize_whitespace(value)
    parts = urlsplit(normalized)
    if not parts.scheme or not parts.netloc:
        return normalized

    userinfo, separator, host_port = parts.netloc.rpartition("@")
    prefix = f"{userinfo}@" if separator else ""
    if host_port.startswith("["):
        closing_bracket = host_port.find("]")
        if closing_bracket >= 0:
            host = host_port[: closing_bracket + 1]
            port = host_port[closing_bracket + 1 :]
        else:
            host, port = host_port, ""
    else:
        host, port_separator, port_value = host_port.partition(":")
        port = f":{port_value}" if port_separator else ""

    return urlunsplit(
        (
            parts.scheme.casefold(),
            f"{prefix}{host.casefold()}{port}",
            parts.path,
            parts.query,
            parts.fragment,
        )
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")
