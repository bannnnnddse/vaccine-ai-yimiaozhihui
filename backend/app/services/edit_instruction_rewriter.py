"""Build bounded instructions for automatic and human image revisions."""

from __future__ import annotations

import re

from app.schemas.image_pipeline import VisualIssue

_SCOPE_RULES = (
    "仅修改指定矩形区域；矩形外所有像素内容、主体、构图和文字保持不变。"
    "修改后保持原图画风、配色、光影、排版和文字风格一致，不新增无关元素。"
)

_ROI_SCOPE_RULES = (
    "你正在编辑一张从原图局部裁剪出的区域。只执行用户指定的修改。"
    "除用户要求修改的对象外，保持该局部区域中的背景、角色造型、文字、"
    "颜色、构图、光影和其他元素不变。不要重新设计整张局部图，不要新增无关元素。"
)


class EditInstructionRewriter:
    @staticmethod
    def is_removal_request(request: str) -> bool:
        return any(keyword in request for keyword in ("删除", "删掉", "去掉", "移除", "清除"))

    @staticmethod
    def is_text_edit_request(request: str) -> bool:
        """Identify bounded copy edits that do not need character reference sheets."""

        compact = request.strip()
        if any(
            keyword in compact
            for keyword in (
                "标题",
                "文字",
                "文本",
                "字样",
                "字体",
                "标签",
                "错别字",
                "改字",
                "替换为",
            )
        ):
            return True
        # A short quoted replacement such as “流程图” is an exact copy-edit target.
        return bool(re.search(r"[“「『\"]\s*[^\n”」』\"]{1,40}\s*[”」』\"]", compact))

    def exact_text_replacement(self, request: str) -> str | None:
        """Return an explicit short replacement only for requests classified as copy edits."""

        if not self.is_text_edit_request(request):
            return None
        compact = request.strip()
        quoted = re.search(r"[“「『\"]\s*([^\n”」』\"]{1,40}?)\s*[”」』\"]", compact)
        if quoted:
            return quoted.group(1).strip()
        replacement = re.search(r"(?:改为|改成|替换为)\s*[：:]?\s*([^\n，；。]{1,40})$", compact)
        return replacement.group(1).strip() if replacement else None

    def rewrite_human(self, request: str) -> str:
        request = request.strip()
        removal_rule = ""
        if self.is_removal_request(request):
            removal_rule = (
                "\n这是删除任务：必须完整移除矩形框内用户指明的对象或文字，"
                "使用框内周围背景自然填充，不得保留原对象、文字、描边或残影。"
            )
        return f"{_ROI_SCOPE_RULES}{removal_rule}\n用户要求：{request}"

    def rewrite_auto(self, issues: list[VisualIssue]) -> str:
        fixes: list[str] = []
        for issue in issues:
            if issue.issue_type == "text_error":
                # The critic has supplied an exact, bounded transcription.
                # Do not let the image model reinterpret terminology from a
                # broad narrative recommendation.
                fixes.append(
                    f"将框内错误文字“{issue.observed_text}”逐字替换为"
                    f"“{issue.replacement_text}”，不得保留、增删或改写其他文字。"
                )
            elif issue.issue_type == "text_regeneration":
                fixes.append(
                    "清除框内所有乱码、错字、缺字、残影和不可读文字；"
                    "严格按审核契约重新排版完整、清晰的规范简体中文标签与步骤。"
                )
            else:
                fixes.append(issue.suggested_fix.strip())
        return f"{_SCOPE_RULES}\n根据审核意见修正：{'；'.join(fixes)}"
