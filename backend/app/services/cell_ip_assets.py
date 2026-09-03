"""Validated runtime access to the cell-character IP skill assets."""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.schemas.science_figure import ChineseFigureBrief, primary_relation_of

_MANIFEST_PATH = Path("assets/manifest.json")
_RUNTIME_PROFILE_PATH = Path("runtime-profile.json")
_GENERIC_CELL_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9+ -]{0,12}细胞")
_REQUIRED_SKILL_FILES = (
    Path("SKILL.md"),
    _RUNTIME_PROFILE_PATH,
    Path("references/character-bible.md"),
    Path("references/style-dna.md"),
    Path("references/composition-patterns.md"),
    Path("references/prompt-template.md"),
    Path("references/scientific-prompt-template.md"),
    Path("references/qa-checklist.md"),
)


class CellIpAssetError(RuntimeError):
    """The configured skill or one of its governed assets is invalid."""


class _RoleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(min_length=1)
    asset: str = Field(min_length=1)
    appearance: str = Field(min_length=1, max_length=240)

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, aliases: list[str]) -> list[str]:
        cleaned = [alias.strip() for alias in aliases]
        duplicate_count = len(set(map(str.casefold, cleaned))) != len(cleaned)
        if any(not alias for alias in cleaned) or duplicate_count:
            raise ValueError("role aliases must be non-empty and unique")
        return cleaned


class _CellIpManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    aspect_ratio: str
    style_reference: str
    character_sheet: str
    roles: list[_RoleManifest] = Field(min_length=10, max_length=10)

    @field_validator("aspect_ratio")
    @classmethod
    def require_supported_ratio(cls, value: str) -> str:
        if value != "16:9":
            raise ValueError("cell IP runtime currently requires a 16:9 manifest")
        return value

    @field_validator("roles")
    @classmethod
    def require_unique_roles(cls, roles: list[_RoleManifest]) -> list[_RoleManifest]:
        ids = [role.id for role in roles]
        if len(ids) != len(set(ids)):
            raise ValueError("role IDs must be unique")
        alias_owners: dict[str, str] = {}
        for role in roles:
            for alias in role.aliases:
                key = alias.casefold()
                owner = alias_owners.setdefault(key, role.id)
                if owner != role.id:
                    raise ValueError("role aliases must be unique across roles")
        return roles


class _RuntimeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    aspect_ratio: Literal["16:9"]
    composition: Literal["single_scene", "causal_diagram"]
    max_causal_steps: int = Field(ge=1, le=4)
    max_reference_images: int = Field(ge=0, le=3)
    include_style_reference: bool
    include_role_board: bool
    allow_title: bool
    style_instruction: str = Field(min_length=20, max_length=500)
    composition_instruction: str = Field(min_length=20, max_length=500)
    prohibitions: list[str] = Field(min_length=1, max_length=12)


class _RuntimeContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    skill_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    profiles: dict[Literal["cell_ip_editorial", "cell_ip_scientific"], _RuntimeProfile]

    @field_validator("profiles")
    @classmethod
    def require_both_profiles(
        cls, profiles: dict[str, _RuntimeProfile]
    ) -> dict[str, _RuntimeProfile]:
        if set(profiles) != {"cell_ip_editorial", "cell_ip_scientific"}:
            raise ValueError("runtime contract must define both cell IP profiles")
        return profiles


@dataclass(frozen=True)
class CellIpGenerationProfile:
    """Immutable references and prompt context selected for one image job."""

    visual_profile: Literal["cell_ip_editorial", "cell_ip_scientific"]
    role_ids: tuple[str, ...]
    role_names: tuple[str, ...]
    role_specs: tuple[str, ...]
    unmatched_cell_terms: tuple[str, ...]
    aspect_ratio: str
    composition: Literal["single_scene", "causal_diagram"]
    max_causal_steps: int
    allow_title: bool
    style_instruction: str
    composition_instruction: str
    prohibitions: tuple[str, ...]
    reference_names: tuple[str, ...]
    references: tuple[bytes, ...]

    @property
    def generation_references(self) -> list[bytes]:
        return list(self.references)

    @property
    def edit_references(self) -> list[bytes]:
        return list(self.references)

    @property
    def review_references(self) -> list[bytes]:
        """Return the same governed references used for generation and edits."""
        return list(self.references)

    @property
    def critic_context(self) -> str:
        roles = "；".join(self.role_specs) if self.role_specs else "未命中固定角色"
        unmatched = (
            "；未收录细胞：" + "、".join(self.unmatched_cell_terms)
            if self.unmatched_cell_terms
            else ""
        )
        if self.visual_profile == "cell_ip_scientific":
            profile_check = (
                "这是细胞IP科学图解：必须逐条覆盖核心因果链，箭头方向、实体标签和步骤顺序"
                "优先于留白与故事感；允许标题、编号、箭头、分区和流程结构，不得因为画面复杂"
                "而要求压缩成单场景。"
            )
        else:
            profile_check = (
                "这是细胞IP正文插画：检查触发、行动、可见结果的单场景因果，以及克制手绘风格；"
                "不得出现标题、PPT、UI、密集信息图、角色摆拍或无关剧情。"
            )
        return (
            "当前任务启用了细胞 IP skill。必须检查16:9横版和固定角色的颜色、轮廓、专属道具；"
            f"{profile_check} 固定角色：{roles}{unmatched}"
        )


class CellIpAssetService:
    """Load, validate, match, and compose references from one skill directory."""

    def __init__(self, skill_dir: Path) -> None:
        self._root = Path(skill_dir).resolve()
        self._manifest = self._load_manifest()
        self._runtime_contract = self._load_runtime_contract()
        self._roles_by_id = {role.id: role for role in self._manifest.roles}
        self._role_assets = {
            role.id: self._resolve_asset(role.asset) for role in self._manifest.roles
        }
        self._style_path = self._resolve_asset(self._manifest.style_reference)
        self._character_sheet_path = self._resolve_asset(self._manifest.character_sheet)
        self._validate_required_files()
        self._style_reference = self._read_rgb_bytes(self._style_path)
        self._character_sheet = self._read_rgb_bytes(self._character_sheet_path)

    def profile_for(
        self, brief: ChineseFigureBrief, user_prompt: str | None = None
    ) -> CellIpGenerationProfile:
        if brief.visual_profile not in {"cell_ip_editorial", "cell_ip_scientific"}:
            raise CellIpAssetError("cell IP profile requested for a non-cell-IP brief")
        visual_profile = brief.visual_profile
        contract = self._runtime_contract.profiles[visual_profile]
        if len(brief.core_causal_steps) > contract.max_causal_steps:
            raise CellIpAssetError(
                f"{visual_profile} cannot cover {len(brief.core_causal_steps)} causal steps"
            )
        # A non-None governed list is an application-owned pre-refiner contract.
        # Never rematch model-authored brief text in that case: it would allow the
        # refiner to add or redefine governed identities after the lock is set.
        roles = (
            self.roles_for_ids(brief.governed_role_ids)
            if brief.governed_role_ids is not None
            else self.match_roles(self._brief_text(brief, user_prompt))
        )
        role_ids = tuple(role.id for role in roles)
        role_names = tuple(role.name for role in roles)
        role_specs = tuple(f"{role.name}：{role.appearance}" for role in roles)
        unmatched_cell_terms = self.unmatched_cell_terms(
            self._semantic_text(brief, user_prompt)
            if brief.governed_role_ids is not None
            else self._brief_text(brief, user_prompt)
        )
        if roles and len(roles) <= contract.max_reference_images:
            # Few governed roles: send each flat-characters asset as an
            # independent canonical identity reference.
            references = [
                self._read_rgb_bytes(self._role_assets[role.id]) for role in roles
            ]
            reference_names = [f"canonical:{role.id}" for role in roles]
        elif roles:
            # More governed roles than the reference budget (2): use the complete
            # flat-character-sheet as ONE identity-selection reference and let the
            # compiled prompt tell Wan exactly which cells to extract.
            references = [self._character_sheet]
            reference_names = [f"role-sheet:{'+'.join(role_ids)}"]
        else:
            # No governed role matched: reuse the full sheet purely as a shared
            # style-language reference so unmatched cells keep the flat hand-drawn
            # look without copying any specific fixed role.
            references = [self._character_sheet]
            reference_names = ["role-sheet:style"]
        if len(references) > contract.max_reference_images:
            raise CellIpAssetError(
                "too many independent canonical references for the runtime profile"
            )
        return CellIpGenerationProfile(
            visual_profile=visual_profile,
            role_ids=role_ids,
            role_names=role_names,
            role_specs=role_specs,
            unmatched_cell_terms=unmatched_cell_terms,
            aspect_ratio=contract.aspect_ratio,
            composition=contract.composition,
            max_causal_steps=contract.max_causal_steps,
            allow_title=contract.allow_title,
            style_instruction=contract.style_instruction,
            composition_instruction=contract.composition_instruction,
            prohibitions=tuple(contract.prohibitions),
            reference_names=tuple(reference_names),
            references=tuple(references),
        )

    def match_roles(self, text: str) -> list[_RoleManifest]:
        folded = text.casefold()
        candidates: list[tuple[int, int, _RoleManifest]] = []
        for role in self._manifest.roles:
            for alias in role.aliases:
                needle = alias.casefold()
                pattern = re.escape(needle)
                if needle.isascii() and needle[0].isalnum() and needle[-1].isalnum():
                    pattern = rf"(?<![a-z0-9]){pattern}(?![a-z0-9])"
                candidates.extend(
                    (match.start(), match.end(), role)
                    for match in re.finditer(pattern, folded)
                )

        selected: list[tuple[int, int, _RoleManifest]] = []
        occupied: list[tuple[int, int]] = []
        for start, end, role in sorted(
            candidates, key=lambda item: (-(item[1] - item[0]), item[0], item[2].id)
        ):
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            selected.append((start, end, role))
            occupied.append((start, end))

        first_mentions: dict[str, tuple[int, _RoleManifest]] = {}
        for start, _, role in selected:
            previous = first_mentions.get(role.id)
            if previous is None or start < previous[0]:
                first_mentions[role.id] = (start, role)
        return [item[1] for item in sorted(first_mentions.values(), key=lambda item: item[0])]

    def roles_for_ids(self, role_ids: list[str]) -> list[_RoleManifest]:
        unknown = [role_id for role_id in role_ids if role_id not in self._roles_by_id]
        if unknown:
            raise CellIpAssetError("locked cell IP contract referenced an unknown role")
        if len(role_ids) != len(set(role_ids)):
            raise CellIpAssetError("locked cell IP contract contains duplicate roles")
        return [self._roles_by_id[role_id] for role_id in role_ids]

    def unmatched_cell_terms(self, text: str) -> tuple[str, ...]:
        """Find named cell terms that are not one of the governed fixed roles."""
        terms: list[str] = []
        for match in _GENERIC_CELL_PATTERN.finditer(text):
            term = " ".join(match.group().split())
            if not term or self.match_roles(term):
                continue
            if term not in terms:
                terms.append(term)
        return tuple(terms)

    def _load_manifest(self) -> _CellIpManifest:
        manifest_path = self._resolve_asset(_MANIFEST_PATH)
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            return _CellIpManifest.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise CellIpAssetError("invalid cell IP asset manifest") from exc

    def _load_runtime_contract(self) -> _RuntimeContract:
        contract_path = self._resolve_asset(_RUNTIME_PROFILE_PATH)
        try:
            payload = json.loads(contract_path.read_text(encoding="utf-8"))
            return _RuntimeContract.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise CellIpAssetError("invalid cell IP runtime profile") from exc

    def _validate_required_files(self) -> None:
        for relative in _REQUIRED_SKILL_FILES:
            path = self._resolve_asset(relative)
            if not path.is_file():
                raise CellIpAssetError(
                    f"required cell IP skill file is missing: {relative.as_posix()}"
                )
        for path in (
            self._style_path,
            self._character_sheet_path,
            *self._role_assets.values(),
        ):
            if not path.is_file():
                raise CellIpAssetError(f"required cell IP asset is missing: {path.name}")

    def _resolve_asset(self, relative: str | Path) -> Path:
        candidate = (self._root / Path(relative)).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise CellIpAssetError(
                "cell IP asset path escaped the configured skill directory"
            ) from exc
        return candidate

    @staticmethod
    def _brief_text(brief: ChineseFigureBrief, user_prompt: str | None) -> str:
        parts = [
            user_prompt or "",
            brief.optimized_chinese_prompt,
            *brief.chinese_labels,
            *brief.scientific_claims,
            *(primary_relation_of(step) for step in brief.core_causal_steps),
        ]
        return "\n".join(parts)

    @staticmethod
    def _semantic_text(brief: ChineseFigureBrief, user_prompt: str | None) -> str:
        return "\n".join(
            [
                user_prompt or "",
                *brief.chinese_labels,
                *brief.scientific_claims,
                *(primary_relation_of(step) for step in brief.core_causal_steps),
            ]
        )

    @classmethod
    def _read_rgb_bytes(cls, path: Path) -> bytes:
        image = cls._read_rgb(path)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    @staticmethod
    def _read_rgb(path: Path) -> Image.Image:
        try:
            with Image.open(path) as source:
                source.load()
                if source.mode == "RGBA":
                    background = Image.new("RGBA", source.size, "white")
                    background.alpha_composite(source)
                    return background.convert("RGB")
                return source.convert("RGB")
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            raise CellIpAssetError(f"invalid cell IP image asset: {path.name}") from exc
