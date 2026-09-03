import { useEffect, useRef, useState, type PointerEvent } from "react";
import type {
  EditScopeGuardResult,
  ImageJobStage,
  NormalizedBBox,
  RevisionOrigin,
  VisualCriticResult,
} from "../services/generationService";

interface ImageReviewCardProps {
  imageUrl: string;
  candidateImageUrl?: string;
  previousImageUrl?: string;
  previousImageId?: string;
  imageId: string;
  stage: ImageJobStage;
  criticResult?: VisualCriticResult;
  guardResult?: EditScopeGuardResult;
  autoRevisionCount: number;
  revisionOrigin?: RevisionOrigin;
  accepted?: boolean;
  historical?: boolean;
  acceptError?: string;
  onAccept: () => void;
  onRestorePrevious?: () => void;
  onEdit: (bbox: NormalizedBBox, request: string) => void;
  onImageError?: () => void;
  onInteraction?: () => void;
}

const severityCopy = { low: "轻微", medium: "中等", high: "严重" } as const;
const originCopy = { initial: "首次生成", auto: "AI 自动修订", human: "用户局部编辑" } as const;
const issueTypeCopy = {
  text_error: "文字标注错误",
  text_regeneration: "文字需要重新生成",
  layout: "版式与层级问题",
  artifact: "画面伪影或瑕疵",
  anatomy: "基础形态问题",
  style_inconsistency: "画面风格不一致",
  ip_identity_mismatch: "固定形象不一致",
  scientific_expression: "潜在科学表达风险",
  other: "其他视觉问题",
} as const;

export function ImageReviewCard(props: ImageReviewCardProps) {
  const shouldExpandReview = () => Boolean(
    (props.guardResult && !props.guardResult.passed && !props.candidateImageUrl)
    || (props.criticResult && props.criticResult.overallStatus !== "pass"),
  );
  const [showReview, setShowReview] = useState(shouldExpandReview);
  const [editing, setEditing] = useState(false);
  const [bbox, setBBox] = useState<NormalizedBBox | null>(null);
  const [request, setRequest] = useState("");
  const busy = !["completed", "awaiting_human_feedback"].includes(props.stage);
  useEffect(() => {
    setEditing(false);
    setBBox(null);
    setRequest("");
    setShowReview(shouldExpandReview());
  }, [props.imageId]);
  if (props.accepted) {
    return <section className="image-review-card image-review-card--accepted">
      <div className="image-review-card__media">
        <img src={props.imageUrl} alt="AI 生成的科学图解" onError={props.onImageError} />
      </div>
    </section>;
  }
  return <section className="image-review-card">
    <div className="image-review-card__media">
      {editing ? <BBoxEditor imageUrl={props.imageUrl} bbox={bbox} onChange={(nextBBox) => { props.onInteraction?.(); setBBox(nextBBox); }} onImageError={props.onImageError} />
        : <img src={props.imageUrl} alt="AI 生成的科学图解" onError={props.onImageError} />}
    </div>
    <div className="image-review-card__body">
      <div className="image-review-card__meta">
        <strong>{props.historical ? "历史版本" : busy ? stageLabel(props.stage) : props.stage === "completed" ? "图解可接受" : "等待你的确认或修改"}</strong>
        <span>{props.revisionOrigin ? originCopy[props.revisionOrigin] : "生成闭环"}{props.autoRevisionCount > 0 ? ` · AI 已自动修订 ${props.autoRevisionCount} 次` : ""}</span>
      </div>
      {!props.accepted && props.guardResult && !props.guardResult.passed && (
        props.candidateImageUrl
          ? <div className="guard-warning" role="alert">
              <strong>{props.guardResult.insufficientChangeInsideBBox
                ? "框内修改未生效，候选未被接受"
                : "范围保护未通过，候选未被接受"}</strong>
              <p>{props.guardResult.notes}</p>
              <div className="guard-comparison"><figure><img src={props.imageUrl} alt="保留的可信版本" /><figcaption>可信版本</figcaption></figure><figure><img src={props.candidateImageUrl} alt="被拒绝的编辑候选" /><figcaption>被拒绝候选</figcaption></figure></div>
            </div>
          : <div className="guard-warning" role="alert">
              <strong>{props.guardResult.insufficientChangeInsideBBox
                ? "当前显示候选修订图，但框内目标修改尚未确认"
                : "已采用修订结果，但框外有其他区域被修改"}</strong>
              <p>修订图已替换显示；橙色框为本地差异检测到的框外变化区域。请在下方“AI 审核”中核验后，再确认采用或恢复上一版。</p>
              <CollateralPreview imageUrl={props.imageUrl} regions={props.guardResult.outsideChangeRegions ?? []} />
            </div>
      )}
      {!props.accepted && props.candidateImageUrl && props.guardResult?.passed
        && props.criticResult && props.criticResult.overallStatus !== "pass" && (
        <div className="guard-warning" role="alert">
          <strong>局部修改未通过最终视觉审核，可信版本未被覆盖</strong>
          <p>{localizedSummary(props.criticResult)}</p>
          <div className="guard-comparison"><figure><img src={props.imageUrl} alt="保留的可信版本" /><figcaption>可信版本</figcaption></figure><figure><img src={props.candidateImageUrl} alt="未通过视觉审核的编辑候选" /><figcaption>未通过审核的候选</figcaption></figure></div>
        </div>
      )}
      {!props.accepted && showReview && props.criticResult && <CriticPanel result={props.criticResult} />}
      {!props.accepted && editing && <div className="bbox-edit-form">
        <p>在图片上拖拽一个矩形框，再说明需要修改的内容。</p>
        <textarea value={request} onChange={(event) => { props.onInteraction?.(); setRequest(event.target.value); }} maxLength={1000} placeholder="例如：把框内标题改成更简洁的中文" />
        <div><button type="button" onClick={() => setBBox(null)}>清除框选</button><button type="button" disabled={!bbox || !request.trim() || busy} onClick={() => { if (bbox && request.trim()) props.onEdit(bbox, request.trim()); }}>提交局部修改</button></div>
      </div>}
      {!props.accepted && props.acceptError && <p className="image-review-card__accept-error" role="alert">{props.acceptError}</p>}
      {!props.accepted && <div className="image-review-card__actions">
        {!props.historical && <button type="button" disabled={busy} onClick={props.onAccept}>{props.guardResult?.insufficientChangeInsideBBox ? "确认采用当前修订图" : "接受结果"}</button>}
        {!props.historical && props.previousImageUrl && props.previousImageId && <button type="button" disabled={busy} onClick={props.onRestorePrevious}>恢复上一版</button>}
        <button type="button" disabled={!props.criticResult} onClick={() => setShowReview((value) => !value)}>{showReview ? "收起 AI 审核" : "查看 AI 审核"}</button>
        {!props.historical && <button type="button" disabled={busy} onClick={() => { props.onInteraction?.(); setEditing((value) => !value); }}>{editing ? "退出修改" : "修改这张图"}</button>}
      </div>}
    </div>
  </section>;
}

export function normalizedDragBBox(
  start: [number, number], current: [number, number],
): NormalizedBBox | null {
  const [sx, sy] = start;
  if (Math.abs(current[0] - sx) <= 0.005 || Math.abs(current[1] - sy) <= 0.005) return null;
  return [Math.min(sx, current[0]), Math.min(sy, current[1]), Math.max(sx, current[0]), Math.max(sy, current[1])];
}

function CriticPanel({ result }: { result: VisualCriticResult }) {
  return <section className="critic-panel"><h4>AI 视觉审核</h4><p>{localizedSummary(result)}</p>
    {result.issues.length > 0 && <ul>{result.issues.map((issue, index) => <li key={`${issue.issueType}-${index}`}>
      <div><strong>{severityCopy[issue.severity]} · {issueTypeCopy[issue.issueType]}</strong><span>{issue.autoFixable ? "可自动修复" : issue.humanInputRequired ? "需要人工判断" : "建议检查"}</span></div>
      <p>{localizedIssueDescription(issue)}</p><small>建议：{localizedSuggestedFix(issue)}</small>
    </li>)}</ul>}
  </section>;
}

export function normalizedPointInImage(
  clientPoint: [number, number],
  imageRect: Pick<DOMRect, "left" | "top" | "width" | "height">,
): [number, number] {
  if (imageRect.width <= 0 || imageRect.height <= 0) return [0, 0];
  return [
    Math.max(0, Math.min(1, (clientPoint[0] - imageRect.left) / imageRect.width)),
    Math.max(0, Math.min(1, (clientPoint[1] - imageRect.top) / imageRect.height)),
  ];
}

export function normalizedBBoxToNaturalPixels(
  bbox: NormalizedBBox, naturalWidth: number, naturalHeight: number,
): [number, number, number, number] {
  return [
    Math.floor(bbox[0] * naturalWidth),
    Math.floor(bbox[1] * naturalHeight),
    Math.ceil(bbox[2] * naturalWidth),
    Math.ceil(bbox[3] * naturalHeight),
  ];
}

function CollateralPreview({ imageUrl, regions }: { imageUrl: string; regions: NormalizedBBox[] }) {
  if (regions.length === 0) return null;
  return <figure className="image-review-card__collateral-preview">
    <div className="image-review-card__collateral-preview-image">
      <img src={imageUrl} alt="框外变化位置预览" />
      {regions.map((region, index) => (
        <span
          className="image-review-card__collateral-region"
          key={`${region.join("-")}-${index}`}
          aria-label="检测到框外变化的区域"
          style={{ left: `${region[0] * 100}%`, top: `${region[1] * 100}%`, width: `${(region[2] - region[0]) * 100}%`, height: `${(region[3] - region[1]) * 100}%` }}
        />
      ))}
    </div>
    <figcaption>框外变化位置预览（主图不叠加标记）</figcaption>
  </figure>;
}

function localizedSummary(result: VisualCriticResult): string {
  return shouldUseChineseFallback(result.summary)
    ? "AI 审核发现以下需要处理的问题，请逐项核验。"
    : result.summary;
}

function localizedIssueDescription(issue: VisualCriticResult["issues"][number]): string {
  if (!shouldUseChineseFallback(issue.description)) return issue.description;
  if (issue.issueType === "text_error" && issue.observedText && issue.replacementText) {
    return `检测到文字标注错误：应将“${issue.observedText}”修正为“${issue.replacementText}”。`;
  }
  return ({
    text_error: "检测到文字标注错误，需要改为规范、清晰的中文表述。",
    text_regeneration: "画面中的文字存在乱码、错字、缺字或不可读内容。",
    layout: "画面信息层级或元素布局不够清晰。",
    artifact: "画面存在影响阅读的伪影、残留或异常细节。",
    anatomy: "画面中的基础形态表现需要进一步核验。",
    style_inconsistency: "画面中存在与整体视觉风格不一致的元素。",
    ip_identity_mismatch: "固定角色形象与提供的参考图不一致。",
    scientific_expression: "画面可能存在科学表达风险，需人工核验。",
    other: "发现需要进一步核验的视觉问题。",
  } as const)[issue.issueType];
}

function localizedSuggestedFix(issue: VisualCriticResult["issues"][number]): string {
  if (!shouldUseChineseFallback(issue.suggestedFix)) return issue.suggestedFix;
  if (issue.issueType === "text_error" && issue.observedText && issue.replacementText) {
    return `将“${issue.observedText}”逐字替换为“${issue.replacementText}”。`;
  }
  return ({
    text_error: "核对并修正该区域的中文标注。",
    text_regeneration: "重新生成该区域文字，使用完整、清晰的规范简体中文。",
    layout: "调整相关元素的位置、层级或留白，使阅读顺序清晰。",
    artifact: "清除异常细节，并保持周围画面自然连续。",
    anatomy: "依据可靠的科普参考重新核验和调整该区域。",
    style_inconsistency: "统一相关元素的配色、轮廓和视觉风格。",
    ip_identity_mismatch: "参照固定角色参考图核验后，再决定是否需要修改。",
    scientific_expression: "请人工核验科学表述后再接受或修改。",
    other: "请人工核验该问题后再接受或修改。",
  } as const)[issue.issueType];
}

function shouldUseChineseFallback(value: string): boolean {
  const latinCount = (value.match(/[A-Za-z]/g) ?? []).length;
  const chineseCount = (value.match(/[\u3400-\u9fff]/g) ?? []).length;
  return latinCount > chineseCount;
}

function BBoxEditor({ imageUrl, bbox, onChange, onImageError }: { imageUrl: string; bbox: NormalizedBBox | null; onChange: (bbox: NormalizedBBox | null) => void; onImageError?: () => void }) {
  const container = useRef<HTMLDivElement>(null);
  const image = useRef<HTMLImageElement>(null);
  const start = useRef<[number, number] | null>(null);
  const point = (event: PointerEvent<HTMLDivElement>): [number, number] => {
    const rect = image.current?.getBoundingClientRect() ?? container.current!.getBoundingClientRect();
    return normalizedPointInImage([event.clientX, event.clientY], rect);
  };
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!start.current) return;
    const selection = normalizedDragBBox(start.current, point(event));
    if (selection) onChange(selection);
  };
  return <div className="bbox-editor" ref={container} onPointerDown={(event) => { start.current = point(event); onChange(null); event.currentTarget.setPointerCapture?.(event.pointerId); }} onPointerMove={move} onPointerUp={(event) => { move(event); start.current = null; }} onPointerCancel={() => { start.current = null; }}>
    <img ref={image} src={imageUrl} alt="框选需要修改的区域" draggable={false} onError={onImageError} />
    {bbox && <span className="bbox-editor__selection" style={{ left: `${bbox[0] * 100}%`, top: `${bbox[1] * 100}%`, width: `${(bbox[2] - bbox[0]) * 100}%`, height: `${(bbox[3] - bbox[1]) * 100}%` }} />}
  </div>;
}

function stageLabel(stage: ImageJobStage): string {
  return ({ queued: "任务排队中", rewriting_prompt: "提示词优化中", generating: "图片生成中", critic_review_1: "AI 首次审核中", auto_revising: "AI 自动修订中", guard_check: "编辑范围保护检查中", critic_review_2: "自动修订结果审核中", awaiting_human_feedback: "等待你的修改建议", editing_with_bbox: "区域编辑中", critic_review_final: "修改结果审核中", completed: "图解生成完成", failed: "图解生成失败", cancelled: "图解生成已取消" })[stage];
}
