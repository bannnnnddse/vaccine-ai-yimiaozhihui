"""Contracts for dynamically routed Chinese science-image generation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ScienceImageType = Literal[
    "science_poster",
    "graphical_abstract",
    "mechanism_diagram",
]

# The public image-job contract retains the route field for existing clients,
# but Wan is now the only supported generator.
GenerationRoute = Literal["fast"]
VisualProfile = Literal[
    "scientific_diagram",
    "cell_ip_editorial",
    "cell_ip_scientific",
]


class CoreCausalStep(BaseModel):
    """One irreducible relationship in a scientific mechanism."""

    model_config = ConfigDict(extra="forbid")

    primary_relation: str = Field(min_length=4, max_length=240)


def primary_relation_of(step: object) -> str:
    """Return ``primary_relation`` from a CoreCausalStep or a raw mapping.

    ``BaseModel.model_copy(update=...)`` bypasses validation, so callers may
    briefly hold raw ``{"primary_relation": ...}`` dicts in place of validated
    ``CoreCausalStep`` instances. Reading relation text through this helper keeps
    the locked-IP pipeline robust to both shapes.
    """
    if isinstance(step, CoreCausalStep):
        return step.primary_relation
    if isinstance(step, dict):
        relation = step.get("primary_relation")
        if isinstance(relation, str):
            return relation
    return ""


class ChineseFigureBrief(BaseModel):
    """Chinese prompt for the supported Wan science-image pipeline."""

    model_config = ConfigDict(extra="forbid")

    image_type: ScienceImageType
    generation_route: GenerationRoute
    visual_profile: VisualProfile = "scientific_diagram"
    # Assigned by the application before prompt refinement; never authored by the model.
    governed_role_ids: list[str] | None = None
    # The refiner may describe scene-only attributes here. Canonical appearance is compiled
    # separately from the governed asset manifest.
    scene_direction: str = Field(default="", max_length=1600)
    optimized_chinese_prompt: str = Field(min_length=40, max_length=3000)
    chinese_labels: list[str] = Field(min_length=1, max_length=8)
    scientific_claims: list[str] = Field(min_length=1, max_length=8)
    core_causal_steps: list[CoreCausalStep] = Field(min_length=1, max_length=4)
    route_reason: str = Field(min_length=4, max_length=240)


# Retained as a temporary import-compatible name until the organizer and image
# generators move to ChineseFigureBrief in their dedicated follow-up tasks.
EnglishFigureBrief = ChineseFigureBrief
