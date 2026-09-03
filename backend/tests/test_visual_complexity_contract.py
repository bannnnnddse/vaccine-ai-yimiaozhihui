from app.schemas.science_figure import ChineseFigureBrief
from app.services.visual_complexity_contract import derive_visual_complexity_contract


def _brief(*, profile: str = "scientific_diagram", steps: int = 1) -> ChineseFigureBrief:
    return ChineseFigureBrief(
        image_type="mechanism_diagram",
        generation_route="fast",
        visual_profile=profile,  # type: ignore[arg-type]
        optimized_chinese_prompt=(
            "制作一张中文科学图解，使用清晰的因果顺序、视觉节点、箭头、分区和标签，"
            "完整解释免疫过程的起点、变化过程与结果。"
        ),
        chinese_labels=["抗原", "免疫反应"],
        scientific_claims=["抗原可被免疫系统识别。"],
        core_causal_steps=[
            {"primary_relation": f"第 {index} 个核心步骤清楚展示免疫过程。"}
            for index in range(1, steps + 1)
        ],
        route_reason="测试复杂度契约。",
    )


def test_standard_diagram_has_a_nontrivial_visual_density_floor() -> None:
    contract = derive_visual_complexity_contract(_brief())

    assert contract.tier == "标准图解"
    assert contract.minimum_information_zones == 3
    assert contract.minimum_visual_nodes == 3
    assert contract.minimum_directional_connectors == 2
    assert "不得为满足复杂度而新增未经支持的实体" in contract.generation_text()


def test_multi_step_or_cell_ip_diagram_uses_detailed_contract() -> None:
    multi_step = derive_visual_complexity_contract(_brief(steps=3))
    cell_ip = derive_visual_complexity_contract(_brief(profile="cell_ip_scientific"))

    assert multi_step.tier == "详细机制图"
    assert multi_step.minimum_information_zones == 4
    assert multi_step.requires_numbered_steps is True
    assert cell_ip.tier == "详细机制图"
    assert cell_ip.minimum_information_zones == 3
    assert "layout_hierarchy 标记为 issue" in cell_ip.audit_text()


def test_editorial_profile_remains_intentionally_spare() -> None:
    contract = derive_visual_complexity_contract(_brief(profile="cell_ip_editorial"))

    assert contract.tier == "简洁叙事"
    assert contract.minimum_information_zones == 1
    assert contract.requires_title is False
