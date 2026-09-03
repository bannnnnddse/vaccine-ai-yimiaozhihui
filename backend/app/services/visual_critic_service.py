"""Vision-model reviewer with strict structured output and safe degradation."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from openai import APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.image_pipeline import (
    BlindTextAudit,
    NormalizedBBox,
    VisualCriticResult,
    critic_unavailable_result,
    normalize_critic,
)

logger = logging.getLogger(__name__)

CRITIC_SYSTEM_PROMPT = """你是医学科普图解的视觉质量审核器。只评估画面可读性、布局、
明显视觉伪影、基础解剖表现、风格一致性、固定细胞 IP 身份一致性和潜在科学表达风险。
请严格以 JSON 输出，不要输出
JSON 之外的文字。所有可展示给用户的字符串字段（summary、description、suggested_fix、
audit_checks.evidence）必须使用简体中文；术语、文件名或用户原文可原样保留，但不得用英文句子
替代中文说明。当前没有接入证据检索，因此
scientific_expression 只能表示潜在风险，必须要求人工复核，不得宣称已经证实科学事实错误。
只有局部、明确、低风险且能够用矩形区域约束的问题才可标记 auto_fixable。bbox 使用归一化
[x1,y1,x2,y2] 坐标。无法确定区域时 bbox 为 null。对于 text_error：若你能清楚读出错误
文字并且唯一确定其标准替换文字，应逐字填写 observed_text 和 replacement_text，并可标记
auto_fixable；如果正确术语存在多个可能、涉及免疫学关系判断、或看不清文字，必须要求人工复核。
不要把“建议使用 A 或 B”标为可自动修复。若提供细胞 IP 参考图，第一张图始终是
待审核成图，其余图片仅是参考；固定角色与参考图的颜色、轮廓或专属道具不符时使用
ip_identity_mismatch。只有单一角色、bbox 明确、且不涉及科学关系改写时才可自动修订。

你必须完成 audit_checks 的六项检查，并给出能追溯到画面的简短证据：visual_integrity、
text_legibility、layout_hierarchy、brief_alignment、causal_step_coverage、
scientific_expression_risk。除 scientific_expression_risk 外，前五项不能写
not_assessable；看不清、无法确认或图片无法覆盖要求时应视为 issue，并创建对应 VisualIssue。
brief_alignment 和 causal_step_coverage 必须逐项对照随请求提供的“审核契约”，不得仅复述用户
原话。若任一 checklist 项为 issue，必须在 issues 中给出对应问题；只有前五项均为 pass、
scientific_expression_risk 没有潜在风险且 issues 为空时，才可以 overall_status=pass。若独立
文字盲读结果出现乱码、缺字或不可辨认的文字，必须将 text_legibility 标记为 issue 并创建
VisualIssue。所有文字错误均应优先标记为 auto_fixable 且 human_input_required=false：能唯一确定
替换内容时使用 text_error；不能唯一逐字替换时使用 text_regeneration，并框选受影响区域（无法
定位时使用全图 bbox）。若审核契约要求出现的标签无法在盲读结果中合理核对，或盲读文本与可见
标签冲突，必须将 brief_alignment 标记为 issue 并创建 VisualIssue；不得用用户需求或审核契约
改写、补全盲读文字。"""

BLIND_TEXT_SYSTEM_PROMPT = """你是图片文字盲读器。你只能根据提供的图片逐字转录肉眼可见的
文字；不会得到主题、预期文字、用户需求或任何背景资料。不要猜测、补全、纠正或翻译文字。
发现乱码、缺字、看不清或无法唯一辨认的文字时，status 必须为 unreadable，并在 summary 中
说明位置和原因。没有可见文字才可使用 clear 且 text_blocks 为空。只输出符合 Schema 的 JSON。"""


class VisualCriticService:
    def __init__(self, settings: Settings, client: AsyncOpenAI | None) -> None:
        self._settings = settings
        self._client = client

    async def review(
        self,
        image_path: Path,
        *,
        user_prompt: str,
        review_label: str,
        revision_instruction: str | None = None,
        target_bbox: NormalizedBBox | None = None,
        collateral_change_note: str | None = None,
        audit_contract: str | None = None,
        cell_ip_context: str | None = None,
        cell_ip_references: Sequence[bytes] = (),
        cell_ip_reference_names: Sequence[str] = (),
    ) -> VisualCriticResult:
        if self._client is None or not self._settings.dashscope_api_key:
            return critic_unavailable_result("authentication_failed")
        try:
            data_url = await _image_data_url(image_path)
            blind_text_audit = await self._best_effort_blind_text_audit(data_url)
            revision_context = ""
            if revision_instruction is not None:
                revision_context = (
                    f"\n本轮局部编辑要求：{revision_instruction}"
                    f"\n目标区域 bbox：{target_bbox.root if target_bbox else '未提供'}"
                    "\n局部编辑已由代码层 ROI mask 限定写入范围。"
                    "请重点判断：用户要求是否真正完成；目标是否符合指令；"
                    "mask 边缘是否有明显拼接痕迹；科学关系、文字、箭头或固定角色 IP 是否受损；"
                    "是否出现新的视觉错误。不能只因画面有变化就判定通过。"
                )
            if collateral_change_note is not None:
                revision_context += f"\n范围保护提示：{collateral_change_note}"
            skill_context = f"\n{cell_ip_context}" if cell_ip_context else ""
            contract_context = (
                f"\n审核契约（仅检查是否在画面中可见、可读且顺序明确，不验证事实真伪）：\n{audit_contract}"
                if audit_contract
                else "\n审核契约：未提供；仍须完成基础视觉检查。"
            )
            blind_text_context = (
                "\n独立文字盲读结果（由未接收主题和期望标签的上游阶段生成；"
                "必须以此为文字判断依据）：\n" + blind_text_audit.model_dump_json()
            )
            content: list[dict[str, object]] = [
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
            for reference in cell_ip_references:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": _bytes_data_url(reference)},
                    }
                )
            reference_context = (
                "\n细胞 IP 参考图顺序（图2起）：" + "、".join(cell_ip_reference_names)
                if cell_ip_references
                else ""
            )
            content.append(
                {
                    "type": "text",
                    "text": (
                        f"审核阶段：{review_label}\n用户原始需求：{user_prompt}"
                        f"{revision_context}{skill_context}{contract_context}{blind_text_context}{reference_context}\n"
                        "请返回符合指定 Schema 的 JSON。"
                    ),
                }
            )
            messages = [
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": content,
                },
            ]
            try:
                response = await self._client.chat.completions.create(
                    model=self._settings.image_critic_model,
                    messages=messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "visual_critic_result",
                            "strict": True,
                            "schema": VisualCriticResult.model_json_schema(),
                        },
                    },
                    extra_body={"enable_thinking": False},
                )
            except APIStatusError as exc:
                if not _structured_output_is_unsupported(exc):
                    raise
                response = await self._client.chat.completions.create(
                    model=self._settings.image_critic_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    extra_body={"enable_thinking": False},
                )
            content = response.choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                return _unavailable("invalid_structured_output")
            parsed = VisualCriticResult.model_validate(json.loads(content))
            return normalize_critic(
                parsed.model_copy(update={"blind_text_audit": blind_text_audit})
            )
        except APITimeoutError as exc:
            return _unavailable("timeout", exc)
        except APIStatusError as exc:
            return _unavailable(_classify_api_error(exc), exc)
        except OSError as exc:
            return _unavailable("local_image_error", exc)
        except (ValueError, TypeError, IndexError, json.JSONDecodeError, ValidationError) as exc:
            return _unavailable("invalid_structured_output", exc)
        except Exception as exc:
            return _unavailable("service_error", exc)

    async def _best_effort_blind_text_audit(self, data_url: str) -> BlindTextAudit:
        """Keep the main visual review available when its auxiliary text pass fails."""

        try:
            return await self._blind_text_audit(data_url)
        except Exception as exc:
            logger.warning("Blind text audit unavailable error_type=%s", type(exc).__name__)
            return BlindTextAudit(
                status="unavailable",
                summary="独立文字盲读暂时不可用，已继续进行完整视觉审核。",
                text_blocks=[],
            )

    async def _blind_text_audit(self, data_url: str) -> BlindTextAudit:
        """Run a prompt-isolated text pass before the contextual critic."""

        assert self._client is not None
        messages = [
            {"role": "system", "content": BLIND_TEXT_SYSTEM_PROMPT},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": data_url}}]},
        ]
        try:
            response = await self._client.chat.completions.create(
                model=self._settings.image_critic_model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "blind_text_audit",
                        "strict": True,
                        "schema": BlindTextAudit.model_json_schema(),
                    },
                },
                extra_body={"enable_thinking": False},
            )
        except APIStatusError as exc:
            if not _structured_output_is_unsupported(exc):
                raise
            response = await self._client.chat.completions.create(
                model=self._settings.image_critic_model,
                messages=messages,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty blind text audit")
        return BlindTextAudit.model_validate(json.loads(content))


async def _image_data_url(path: Path) -> str:
    image_bytes = await asyncio.to_thread(path.read_bytes)
    return _bytes_data_url(image_bytes)


def _bytes_data_url(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _structured_output_is_unsupported(exc: APIStatusError) -> bool:
    if exc.status_code not in {400, 404, 422}:
        return False
    message = str(exc).casefold()
    return "json_schema" in message or "response_format" in message


def _classify_api_error(exc: APIStatusError) -> str:
    message = str(exc).casefold()
    if exc.status_code in {401, 403}:
        return "authentication_failed"
    if exc.status_code == 429:
        return (
            "quota_exhausted"
            if any(marker in message for marker in ("quota", "balance", "insufficient"))
            else "rate_limited"
        )
    if any(
        marker in message
        for marker in (
            "image_url",
            "multimodal",
            "modality",
            "model_not_supported",
            "model not supported",
        )
    ):
        return "model_or_input_not_supported"
    if _structured_output_is_unsupported(exc):
        return "structured_output_not_supported"
    return "service_error"


def _unavailable(reason: str, exc: Exception | None = None) -> VisualCriticResult:
    logger.warning(
        "visual critic unavailable reason=%s exception=%s status=%s",
        reason,
        type(exc).__name__ if exc else None,
        getattr(exc, "status_code", None),
    )
    return critic_unavailable_result(reason)
