"""Deterministic visual-density requirements for science-image generation.

The contract intentionally constrains presentation, not medical content.  It
can reuse a causal step's start/process/result states, but never authorizes a
new biological relation, statistic, or claim.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.schemas.science_figure import ChineseFigureBrief

ComplexityTier = Literal["简洁叙事", "标准图解", "详细机制图"]


@dataclass(frozen=True)
class VisualComplexityContract:
    tier: ComplexityTier
    minimum_information_zones: int
    minimum_visual_nodes: int
    minimum_directional_connectors: int
    minimum_labeled_steps: int
    requires_numbered_steps: bool
    requires_title: bool

    def summary(self) -> str:
        return (
            f"{self.tier}：至少 {self.minimum_information_zones} 个信息分区、"
            f"{self.minimum_visual_nodes} 个可辨视觉节点、"
            f"{self.minimum_directional_connectors} 条方向连接。"
        )

    def generation_text(self) -> str:
        numbering = "使用编号步骤" if self.requires_numbered_steps else "可不使用编号步骤"
        title = "保留一个简短中文标题" if self.requires_title else "不强制标题"
        return (
            f"复杂度等级：{self.tier}。至少设置 {self.minimum_information_zones} 个信息分区、"
            f"{self.minimum_visual_nodes} 个可辨视觉节点、"
            f"{self.minimum_directional_connectors} 条有方向的箭头或连接，并清楚呈现不少于"
            f" {self.minimum_labeled_steps} 个核心步骤；{numbering}；{title}。\n"
            "这些数量只可通过同一核心因果链的起点、过程、结果、状态变化、分区和箭头来实现；"
            "不得为满足复杂度而新增未经支持的实体、医学机制、数据或结论。"
        )

    def audit_text(self) -> str:
        return (
            f"复杂度契约：{self.summary()}"
            f"应{'使用' if self.requires_numbered_steps else '可不使用'}编号步骤，"
            f"应{'保留' if self.requires_title else '不强制'}中文标题。"
            "请根据画面可见内容核验；若信息密度明显不足或步骤被压成单一场景，"
            "将 layout_hierarchy 标记为 issue，并在 issues 中给出需要人工核验的 layout 问题。"
        )

    def metadata(self) -> dict[str, object]:
        return asdict(self)


def derive_visual_complexity_contract(brief: ChineseFigureBrief) -> VisualComplexityContract:
    """Derive a stable density target from the already-governed brief."""

    step_count = len(brief.core_causal_steps)
    if brief.visual_profile == "cell_ip_editorial":
        # Editorial illustration is intentionally a single, airy scene.  Do
        # not turn it into a dense mechanism diagram merely because the global
        # pipeline has a richness target.
        return VisualComplexityContract(
            tier="简洁叙事",
            minimum_information_zones=1,
            minimum_visual_nodes=max(2, step_count + 1),
            minimum_directional_connectors=1 if step_count else 0,
            minimum_labeled_steps=step_count,
            requires_numbered_steps=False,
            requires_title=False,
        )

    detailed = step_count >= 3 or brief.visual_profile == "cell_ip_scientific"
    if detailed:
        return VisualComplexityContract(
            tier="详细机制图",
            minimum_information_zones=4 if step_count >= 3 else 3,
            minimum_visual_nodes=max(4, step_count + 1),
            minimum_directional_connectors=max(3, step_count),
            minimum_labeled_steps=step_count,
            requires_numbered_steps=step_count >= 2,
            requires_title=True,
        )
    return VisualComplexityContract(
        tier="标准图解",
        minimum_information_zones=3,
        minimum_visual_nodes=max(3, step_count + 1),
        minimum_directional_connectors=max(2, step_count),
        minimum_labeled_steps=step_count,
        requires_numbered_steps=step_count >= 2,
        requires_title=True,
    )
