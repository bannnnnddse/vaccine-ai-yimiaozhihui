"""Fast native WAN generation for Chinese public-health illustrations."""

from __future__ import annotations

import asyncio
import io
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.config import Settings
from app.schemas.image_pipeline import NormalizedBBox
from app.schemas.science_figure import ChineseFigureBrief, primary_relation_of
from app.services.cell_ip_assets import (
    CellIpAssetError,
    CellIpAssetService,
    CellIpGenerationProfile,
)
from app.services.visual_complexity_contract import derive_visual_complexity_contract
from app.services.wan_api_client import WanApiClient

logger = logging.getLogger(__name__)

FAST_WAN_PROMPT_CONSTRAINTS = """请生成一张用于公共卫生科普传播的科学图解。

【画布与整体风格】
- 画幅固定为9:16竖版
- 风格为清晰、温和、专业、适合公众传播的医学科普插画风格
- 整体简洁、结构清楚、留白充足，避免拥挤
- 画面无品牌标志、无水印、无夸张或恐怖医疗场景

【文字要求】
- 所有可读文字必须为简体中文
- 标题仅1个，短而清晰，不超过12个字
- 标签总数不超过8个，每个标签尽量不超过8个字
- 只保留必要文字，避免密集小字和长段落
- 禁止出现英文、乱码、拼音、占位符文字
- 如果文字较多，请优先减少文字数量，而不要生成错误文字

【内容与科学关系】
- 图解主题：{optimized_chinese_prompt}
- 必须严格按照以下核心关系展示，不得增加未给出的因果关系、治疗承诺或精确数值：
{causal_chain}
- 关系展示必须清楚，可使用箭头、编号或分步结构
- 所有箭头方向必须与给定关系一致
- 不得自行补充额外机制、结论或疗效暗示

【构图要求】
- 采用自上而下的信息流阅读方式
- 顶部放中文标题
- 中部重点展示核心机制或传播过程
- 下部可放简短总结性提示，但不要堆积小字
- 每一个核心步骤都要有明确视觉主体，便于公众一眼看懂

【信息密度与完整性契约】
{complexity_contract}

【医学表达要求】
- 医学元素应符合基础常识，表达准确、克制、易懂
- 适合表现人体、器官、细胞、病毒、传播路径、防护行为等公共卫生元素
- 不要把病毒画得过于拟人化
- 不要表现“绝对保护”“立刻治愈”“100%有效”等含义

【必须出现的中文标签】
{chinese_labels}

【参考图使用】
- 随请求提供的参考图仅用于总体视觉语言、配色与大体构图参考
- 不得复制参考图中的文字、数据、Logo、水印或具体主体内容

请输出一张适合公共卫生宣传栏/科普海报使用的中文科学图解，重点突出“关系清楚、中文可读、画面干净、结构稳定”。"""

CELL_IP_PROMPT_CONSTRAINTS = """请生成一张 {aspect_ratio} 中文图解。

【仅场景与构图指令】
{scene_direction}

【科学边界】
- 只表现以下核心关系，不得增加未给出的角色、分子连接、机制、治疗承诺或精确数值：
{causal_chain}
- {text_instruction}，候选词为：{chinese_labels}
- 不要因为参考图中存在某个角色就把它加入画面；只有科学关系真正需要时才使用

【固定细胞 IP 与参考图】
{reference_usage}
- 本题命中的固定角色：{matched_roles}
- 固定角色外观契约（只能由下列 canonical reference 决定，场景指令无权重设计或重述）：
{identity_contract}
{sheet_selection}
- 未收录的必要细胞：{unmatched_cells}。它们没有独立资产，应沿用与角色总表一致的整体
  扁平手绘画风（圆润或生物学可辨识的轮廓、短小四肢、黑色圆眼、粉色腮红、深色手绘描边和平涂），
  但不得使用任何固定角色的专属颜色组合、轮廓或道具，也不得被标注为固定角色

【构图与风格契约】
- {composition_instruction}
- {style_instruction}
- 标题策略：{title_instruction}
- 禁止：{prohibitions}
- 科学关系的完整性、箭头方向和实体标签优先于装饰风格；不得为了套用IP而删减关系

【信息密度与完整性契约】
{complexity_contract}

禁止使用用户原始请求、Refiner 文本或标签中的自由外观描述重新设计固定角色。"""

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_REFERENCE_FILENAMES = {
    "science_poster": "science_poster/runtime-reference.png",
    "graphical_abstract": "graphical_abstract/runtime-reference.png",
    "mechanism_diagram": "mechanism_diagram/runtime-reference.jpg",
}


class WanImageGeneratorError(RuntimeError):
    """The native WAN provider did not produce an acceptable image."""


@dataclass(frozen=True)
class WanImageResult:
    """A validated PNG owned by the backend."""

    final_path: Path
    cell_ip_profile: CellIpGenerationProfile | None = None
    final_prompt: str | None = None
    reference_names_sent: tuple[str, ...] = ()


def build_fast_wan_prompt(
    brief: ChineseFigureBrief,
    user_prompt: str | None = None,
) -> str:
    """Render the single editable fast-route prompt template from a brief."""
    causal_chain = "；".join(
        f"{index}. {primary_relation_of(step).strip()}"
        for index, step in enumerate(brief.core_causal_steps, start=1)
    )
    prompt = FAST_WAN_PROMPT_CONSTRAINTS.format(
        causal_chain=causal_chain,
        optimized_chinese_prompt=brief.optimized_chinese_prompt.strip(),
        chinese_labels="、".join(label.strip() for label in brief.chinese_labels),
        complexity_contract=derive_visual_complexity_contract(brief).generation_text(),
    )
    original = user_prompt.strip() if user_prompt else ""
    if original:
        follow_up = "请在遵循上述科学关系的前提下，兼顾用户原始需求中的表达重点。"
        prompt = f"{prompt}\n\n【用户原始需求】\n{original}\n\n{follow_up}"
    return prompt


def build_cell_ip_prompt(
    brief: ChineseFigureBrief,
    profile: CellIpGenerationProfile,
    user_prompt: str | None = None,
) -> str:
    """Build the skill-governed prompt used only when the global switch is on."""
    causal_chain = "；".join(
        f"{index}. {primary_relation_of(step).strip()}"
        for index, step in enumerate(brief.core_causal_steps, start=1)
    )
    identity_names = dict(zip(profile.role_ids, profile.role_names, strict=True))
    if profile.reference_names:
        reference_usage = "\n".join(
            f"- 图{index}{_reference_usage(name, identity_names)}"
            for index, name in enumerate(profile.reference_names, start=1)
        )
    else:
        reference_usage = "- 本轮未提供参考图，仅按文字角色档案生成，不得添加未命中的固定角色"
    identity_contract = (
        "\n".join(f"- {spec}" for spec in profile.role_specs)
        if profile.role_specs
        else "- 本题没有命中固定角色；不要擅自复刻角色总表中的任何角色。"
    )
    unmatched_cells = "、".join(profile.unmatched_cell_terms) or "未识别到命名的未收录细胞"
    scene_direction = _compile_scene_direction(brief, profile)
    return CELL_IP_PROMPT_CONSTRAINTS.format(
        aspect_ratio=profile.aspect_ratio,
        scene_direction=scene_direction,
        causal_chain=causal_chain,
        chinese_labels="、".join(label.strip() for label in brief.chinese_labels),
        matched_roles=("、".join(profile.role_names) if profile.role_names else "无明确命中"),
        text_instruction=(
            "可使用必要的简短中文标题、步骤和实体标签"
            if profile.allow_title
            else "可读中文只保留极少量短手写批注"
        ),
        reference_usage=reference_usage,
        identity_contract=identity_contract,
        sheet_selection=_sheet_selection_block(profile),
        unmatched_cells=unmatched_cells,
        composition_instruction=profile.composition_instruction,
        style_instruction=profile.style_instruction,
        title_instruction=("允许一个必要的简短中文标题" if profile.allow_title else "不要标题"),
        prohibitions="、".join(profile.prohibitions),
        complexity_contract=derive_visual_complexity_contract(brief).generation_text(),
    )


def _reference_usage(name: str, identity_names: dict[str, str]) -> str:
    """Describe what the model must and must not do with one reference image."""
    if name == "role-sheet:style":
        return (
            "仅用于整体扁平手绘画风与配色的统一参考；不要复制其中任何具体角色作为画面元素，"
            "不得改变 fixed canonical IP，不得复制其中的文字、事件或构图"
        )
    if name.startswith("role-sheet:"):
        role_ids = name.removeprefix("role-sheet:").split("+")
        display = "、".join(
            identity_names.get(role_id, role_id) for role_id in role_ids
        )
        return (
            f"是完整细胞 IP 角色总表；只从中提取并使用命中的固定角色（{display}），"
            "保持其颜色、轮廓、面部和专属道具与表中完全一致；不得使用表中其余角色，"
            "也不得复制其中的文字、事件或构图"
        )
    role_id = name.removeprefix("canonical:")
    return (
        f"是 {identity_names.get(role_id, role_id)} 的独立 canonical 身份参考；"
        "必须保持其颜色、轮廓、面部和专属道具完全一致，不得重新设计；"
        "不得复制其中的文字、事件或构图"
    )


def _sheet_selection_block(profile: CellIpGenerationProfile) -> str:
    """When the reference is the full character sheet, tell Wan which cells to use."""
    sheet_name = next(
        (
            name
            for name in profile.reference_names
            if name.startswith("role-sheet:") and name != "role-sheet:style"
        ),
        None,
    )
    if sheet_name is None:
        return ""
    sheet_index = profile.reference_names.index(sheet_name) + 1
    contract = (
        "\n".join(f"- {spec}" for spec in profile.role_specs)
        if profile.role_specs
        else "- 本题没有命中固定角色。"
    )
    matched = "、".join(profile.role_names) if profile.role_names else "无"
    return (
        "【角色总表选取】（仅当参考图为完整角色总表时启用）\n"
        f"- 图{sheet_index} 是完整细胞 IP 角色总表。画面所需固定角色必须逐个从该表中"
        "找到并原样使用，颜色、轮廓、面部、专属道具与装饰一律以表中为准：\n"
        f"{contract}\n"
        f"- 只在总表中提取命中的角色：{matched}；忽略并不得使用表中其余角色，"
        "也不得新增表中不存在的固定角色。"
    )


def _compile_scene_direction(
    brief: ChineseFigureBrief, profile: CellIpGenerationProfile
) -> str:
    """Keep model-authored scene guidance outside governed visual authority."""
    fallback = "\n".join(
        f"- {index}. {primary_relation_of(step).strip()}"
        for index, step in enumerate(brief.core_causal_steps, start=1)
    )
    candidate = brief.scene_direction.strip()
    if not candidate:
        return fallback
    if _contains_governed_appearance(candidate, profile):
        # Preserve scientific actions from the structured causal chain while dropping
        # the entire contaminated free-text scene direction.
        return fallback
    return candidate


_GOVERNED_APPEARANCE_PATTERN = re.compile(
    # A bare “色” also occurs in ordinary visual direction (“角色”, “视觉”).
    # It must not make an otherwise valid governed scene direction disappear.
    r"颜色|黄色|红色|绿色|蓝色|紫色|球形|圆形|多边形|轮廓|形状|刺突|圆刺|"
    r"表情|眼睛|脸|道具|服饰|帽子|背包|披风|武器|比例|皇冠"
)
_GOVERNED_MENTION_PATTERN = re.compile(
    r"HPV|病毒|抗原|抗体|[TB]\s*细胞", re.IGNORECASE
)


def _contains_governed_appearance(
    text: str, profile: CellIpGenerationProfile
) -> bool:
    """Detect free scene text that tries to redesign a locked identity.

    Appearance vocabulary appearing together with a governed role (by canonical
    name or a common alias such as HPV) means the refiner overstepped its visual
    authority; the caller then drops the whole contaminated direction.
    """
    if _GOVERNED_APPEARANCE_PATTERN.search(text):
        if any(role in text for role in profile.role_names):
            return True
        return bool(profile.role_ids and _GOVERNED_MENTION_PATTERN.search(text))
    return False


def load_reference_image(
    settings: Settings,
    image_type: str | None,
) -> list[bytes]:
    """Load the single approved reference image for ``image_type``.

    Fails closed when the matching runtime asset is missing so the fast
    route never silently generates without the intended style anchor.
    """
    filename = _REFERENCE_FILENAMES.get(image_type or "")
    if filename is None:
        return []
    path = settings.reference_image_dir / filename
    try:
        return [path.read_bytes()]
    except OSError as exc:
        raise RuntimeError(
            f"reference image missing for {image_type}: {filename}"
        ) from exc


class WanImageGenerator:
    """Run Bailian WAN generation off the event loop and retain only PNG output."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cell_ip_assets = (
            CellIpAssetService(settings.cell_ip_skill_dir)
            if settings.cell_ip_enabled
            else None
        )
        self._provider = WanApiClient(
            api_key=settings.dashscope_api_key or "",
            api_base=_image_api_base(settings),
            timeout_seconds=settings.wan_image_timeout_seconds,
        )

    async def generate(
        self,
        brief: ChineseFigureBrief,
        output_path: Path,
        cancel_event: asyncio.Event,
        user_prompt: str | None = None,
    ) -> WanImageResult:
        """Generate a PNG using the brief's matching reference image."""
        _raise_if_cancelled(cancel_event)
        wants_cell_ip = brief.visual_profile in {
            "cell_ip_editorial",
            "cell_ip_scientific",
        }
        if wants_cell_ip and self._cell_ip_assets is None:
            raise CellIpAssetError("cell IP visual profile requested while the skill is disabled")
        cell_ip_profile = (
            await asyncio.to_thread(self._cell_ip_assets.profile_for, brief, user_prompt)
            if wants_cell_ip and self._cell_ip_assets
            else None
        )
        if cell_ip_profile is None:
            reference_images = await asyncio.to_thread(
                load_reference_image, self._settings, brief.image_type
            )
            prompt = build_fast_wan_prompt(brief, user_prompt)
            aspect_ratio = "9:16"
        else:
            reference_images = cell_ip_profile.generation_references
            prompt = build_cell_ip_prompt(brief, cell_ip_profile, user_prompt)
            aspect_ratio = cell_ip_profile.aspect_ratio
            _assert_canonical_references(cell_ip_profile, reference_images)
        image_bytes = await asyncio.to_thread(
            self._provider.generate,
            prompt=prompt,
            reference_images=reference_images,
            model=self._settings.dashscope_image_model,
            aspect_ratio=aspect_ratio,
            image_size=self._settings.wan_image_size,
        )
        _raise_if_cancelled(cancel_event)
        if not _is_decodable_png(image_bytes):
            raise WanImageGeneratorError("WAN did not return PNG image bytes")

        output_path = Path(output_path)
        output_path.write_bytes(image_bytes)
        return WanImageResult(
            final_path=output_path,
            cell_ip_profile=cell_ip_profile,
            final_prompt=prompt,
            reference_names_sent=(cell_ip_profile.reference_names if cell_ip_profile else ()),
        )

    async def edit(
        self,
        *,
        source_path: Path,
        output_path: Path,
        instruction: str,
        bbox: NormalizedBBox,
        cancel_event: asyncio.Event,
        cell_ip_profile: CellIpGenerationProfile | None = None,
    ) -> WanImageResult:
        """Edit one authoritative region using Wan 2.7 ``bbox_list``."""
        _raise_if_cancelled(cancel_event)
        image_bytes = await asyncio.to_thread(source_path.read_bytes)
        image_bytes, source_size, provider_size = await asyncio.to_thread(
            _prepare_wan_edit_input,
            image_bytes,
            self._settings.wan_edit_min_input_side_px,
        )
        width, height = provider_size
        pixel_bbox = normalized_bbox_to_pixels(bbox, width, height)
        logger.info(
            "wan_edit_input source_size=%s provider_size=%s upscaled=%s pixel_bbox=%s model=%s",
            source_size,
            provider_size,
            provider_size != source_size,
            pixel_bbox,
            self._settings.image_edit_model,
        )
        result_bytes = await asyncio.to_thread(
            self._edit_sync,
            image_bytes,
            instruction,
            pixel_bbox,
            cell_ip_profile,
        )
        _raise_if_cancelled(cancel_event)
        if not _is_decodable_png(result_bytes):
            raise WanImageGeneratorError("WAN edit did not return PNG image bytes")
        output_path = Path(output_path)
        await asyncio.to_thread(output_path.write_bytes, result_bytes)
        return WanImageResult(final_path=output_path)

    def _edit_sync(
        self,
        image_bytes: bytes,
        instruction: str,
        pixel_bbox: list[int],
        cell_ip_profile: CellIpGenerationProfile | None,
    ) -> bytes:
        reference_images = cell_ip_profile.edit_references if cell_ip_profile else []
        # Wan follows the *last* input image's aspect ratio.  References must
        # therefore precede the authoritative ROI, which is always last.
        content = [
            self._provider._encode_reference_image(reference)  # noqa: SLF001
            for reference in reference_images
        ]
        content.append(self._provider._encode_reference_image(image_bytes))  # noqa: SLF001
        target_image_number = len(reference_images) + 1
        if cell_ip_profile is not None:
            identity_contract = (
                "；".join(cell_ip_profile.role_specs)
                if cell_ip_profile.role_specs
                else "没有命中固定角色，不得复刻任一固定角色"
            )
            instruction = (
                f"图{target_image_number}是唯一待编辑的 ROI 画布；它之前的图片只是固定角色参考，"
                "不得复制参考图的排列、背景、标签或其他角色。"
                "保持待编辑 ROI 的原始宽高比、内容布局、角色颜色、轮廓、表情和道具。"
                f"固定角色外观契约：{identity_contract}。\n"
                f"{instruction}"
            )
        else:
            instruction = (
                f"图{target_image_number}是唯一待编辑的 ROI 画布。"
                "保持它的原始宽高比和内容布局。\n"
                f"{instruction}"
            )
        content.append({"text": instruction})
        payload = {
            "model": self._settings.image_edit_model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {
                "bbox_list": [*([] for _ in reference_images), [pixel_bbox]],
                "size": self._settings.wan_image_size,
                "n": 1,
                "watermark": False,
            },
        }
        endpoint = (
            f"{_image_api_base(self._settings)}"
            "/services/aigc/multimodal-generation/generation"
        )
        response = self._provider._request_json(payload, endpoint=endpoint)  # noqa: SLF001
        image_url = self._provider._find_image_url(response)  # noqa: SLF001
        return self._provider._download_image(image_url)  # noqa: SLF001


def _image_api_base(settings: Settings) -> str:
    """Reuse the configured Bailian image endpoint while removing its service path."""
    base, marker, _ = settings.z_image_endpoint.partition("/services/")
    return base if marker else settings.dashscope_base_url


def _is_decodable_png(image_bytes: object) -> bool:
    if not isinstance(image_bytes, bytes) or not image_bytes.startswith(_PNG_SIGNATURE):
        return False
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.format != "PNG":
                return False
            image.load()
    except (UnidentifiedImageError, OSError, ValueError):
        return False
    return True


def _assert_canonical_references(
    profile: CellIpGenerationProfile, reference_images: list[bytes]
) -> None:
    expected = {f"canonical:{role_id}" for role_id in profile.role_ids}
    actual = set(profile.reference_names)
    sheet = f"role-sheet:{'+'.join(profile.role_ids)}"
    has_identity_references = expected.issubset(actual) or sheet in actual
    if not has_identity_references or len(reference_images) != len(profile.reference_names):
        raise CellIpAssetError(
            "locked cell IP contract is missing a canonical reference in the Wan payload"
        )


def _raise_if_cancelled(cancel_event: asyncio.Event) -> None:
    if cancel_event.is_set():
        raise asyncio.CancelledError("image generation was cancelled")


def normalized_bbox_to_pixels(
    bbox: NormalizedBBox, width: int, height: int
) -> list[int]:
    x1, y1, x2, y2 = bbox.root
    return [
        max(0, min(width - 1, int(round(x1 * width)))),
        max(0, min(height - 1, int(round(y1 * height)))),
        max(1, min(width, int(round(x2 * width)))),
        max(1, min(height, int(round(y2 * height)))),
    ]


def _prepare_wan_edit_input(
    image_bytes: bytes, min_input_side_px: int
) -> tuple[bytes, tuple[int, int], tuple[int, int]]:
    """Strip alpha and upscale small ROI inputs to Wan 2.7's documented minimum."""

    try:
        with Image.open(io.BytesIO(image_bytes)) as source_image:
            source = source_image.convert("RGB")
            source_size = source.size
            scale = max(
                1.0,
                min_input_side_px / source.width,
                min_input_side_px / source.height,
            )
            provider_size = (
                math.ceil(source.width * scale),
                math.ceil(source.height * scale),
            )
            if provider_size != source_size:
                source = source.resize(provider_size, Image.Resampling.LANCZOS)
            output = io.BytesIO()
            source.save(output, format="PNG")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise WanImageGeneratorError("WAN edit source is not a decodable image") from exc
    return output.getvalue(), source_size, provider_size
