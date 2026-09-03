from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from app.schemas.science_figure import ChineseFigureBrief, CoreCausalStep
from app.services.cell_ip_assets import CellIpAssetError, CellIpAssetService

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "cell-ip-illustrations"


def _brief() -> ChineseFigureBrief:
    return ChineseFigureBrief(
        image_type="mechanism_diagram",
        generation_route="fast",
        visual_profile="cell_ip_editorial",
        optimized_chinese_prompt=(
            "制作16:9横版免疫科普配图，展示树突状细胞呈递抗原后，"
            "辅助性T细胞向B细胞传递支援信号并形成清楚的可见结果。"
        ),
        chinese_labels=["树突状细胞", "辅助性T细胞", "B细胞"],
        scientific_claims=["树突状细胞参与抗原呈递。"],
        core_causal_steps=[{"primary_relation": "树突状细胞向辅助性T细胞呈递抗原。"}],
        route_reason="使用细胞角色解释免疫协作。",
    )


def test_manifest_matches_all_ten_roles_and_ignores_vague_t_cell() -> None:
    service = CellIpAssetService(SKILL_DIR)
    all_roles = service.match_roles(
        "辅助性T细胞、B细胞、记忆B细胞、细胞毒性T细胞、巨噬细胞、"
        "树突状细胞、红细胞、病毒颗粒、抗原和抗体"
    )

    assert len(all_roles) == 10
    assert service.match_roles("T细胞参与免疫反应") == []


def test_longest_alias_prevents_memory_b_from_also_matching_b_cell() -> None:
    roles = CellIpAssetService(SKILL_DIR).match_roles("记忆B细胞再次遇到抗原")

    assert [role.id for role in roles] == ["memory_b", "antigen"]


def test_profile_uses_full_character_sheet_when_roles_exceed_budget() -> None:
    profile = CellIpAssetService(SKILL_DIR).profile_for(_brief(), "B细胞接受帮助")

    assert profile.role_ids == ("b_cell", "dendritic", "antigen", "helper_t")
    assert len(profile.generation_references) == 1
    decoded = [Image.open(io.BytesIO(value)) for value in profile.generation_references]
    assert all(image.mode == "RGB" for image in decoded)
    assert decoded[0].size == (945, 900)
    assert profile.reference_names == ("role-sheet:b_cell+dendritic+antigen+helper_t",)


def test_editorial_profile_without_named_role_uses_sheet_as_style_reference() -> None:
    brief = _brief().model_copy(
        update={
            "optimized_chinese_prompt": (
                "制作16:9横版配图，展示先天免疫屏障如何识别风险并完成防护。"
            ),
            "chinese_labels": ["先天免疫"],
            "scientific_claims": ["先天免疫屏障参与基础防护。"],
            "core_causal_steps": [
                CoreCausalStep(primary_relation="先天免疫屏障识别风险信号。")
            ],
        }
    )

    profile = CellIpAssetService(SKILL_DIR).profile_for(brief)

    assert profile.role_ids == ()
    assert profile.reference_names == ("role-sheet:style",)
    assert len(profile.generation_references) == 1


def test_scientific_profile_uses_only_matched_role_sheet() -> None:
    brief = _brief().model_copy(update={"visual_profile": "cell_ip_scientific"})

    profile = CellIpAssetService(SKILL_DIR).profile_for(brief, "B细胞接受帮助")

    assert profile.reference_names == ("role-sheet:b_cell+dendritic+antigen+helper_t",)
    assert len(profile.generation_references) == 1
    assert profile.allow_title is True
    assert profile.composition == "causal_diagram"


def test_profile_records_unmatched_cells_without_extra_reference() -> None:
    brief = _brief().model_copy(
        update={
            "visual_profile": "cell_ip_scientific",
            "optimized_chinese_prompt": "展示宫颈上皮细胞识别风险并保持相容的手绘细胞风格。",
            "chinese_labels": ["宫颈上皮细胞"],
            "scientific_claims": ["宫颈上皮细胞可被病毒感染。"],
            "core_causal_steps": [
                CoreCausalStep(primary_relation="宫颈上皮细胞暴露于病毒风险。")
            ],
        }
    )

    profile = CellIpAssetService(SKILL_DIR).profile_for(brief)

    assert profile.role_ids == ("virus",)
    assert "宫颈上皮细胞" in profile.unmatched_cell_terms
    assert profile.reference_names == ("canonical:virus",)


def test_non_cell_ip_brief_cannot_load_cell_ip_profile() -> None:
    with pytest.raises(CellIpAssetError, match="non-cell-IP"):
        CellIpAssetService(SKILL_DIR).profile_for(
            _brief().model_copy(update={"visual_profile": "scientific_diagram"})
        )


def test_manifest_asset_path_cannot_escape_skill_directory(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "runtime-profile.json").write_text(
        (SKILL_DIR / "runtime-profile.json").read_text("utf-8"),
        encoding="utf-8",
    )
    payload = json.loads((SKILL_DIR / "assets" / "manifest.json").read_text("utf-8"))
    payload["roles"][0]["asset"] = "../outside.png"
    (assets / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CellIpAssetError, match="escaped"):
        CellIpAssetService(tmp_path)
