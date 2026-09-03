import { useEffect, useRef } from "react";
import type { AppPage } from "./CardNav";
import "./HomeLanding.css";

interface HomeLandingProps { onNavigate: (page: AppPage) => void; }

const Dot = () => <span className="landing-dot" aria-hidden="true">·</span>;

export function HomeLanding({ onNavigate }: HomeLandingProps) {
  const landingRef = useRef<HTMLElement>(null);
  const capabilities = [
    ["01", "ASK", "可追溯的科学问答", "从一个真实问题开始，获得清晰的知识线索与边界提示。"],
    ["02", "DRAW", "9:16 科学图解", "将中文主题转化为适合传播的科学图解，保留生成过程。"],
    ["03", "PLAY", "病毒入侵日记", "在沉浸式关卡中感受免疫应答如何一步步发生。"],
    ["04", "SHARE", "科普视频素材", "把理解过的知识重新组织成可分享的短视频表达。"],
    ["05", "EXPLORE", "查看知识图谱", "沿着实体、关系与来源证据，探索当前知识库的最新结构。"],
  ];
  useEffect(() => {
    const landing = landingRef.current;
    if (!landing) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const revealItems = Array.from(landing.querySelectorAll<HTMLElement>("[data-reveal]"));
    const revealVisibleItems = () => {
      const bounds = landing.getBoundingClientRect();
      revealItems.forEach((item) => {
        const rect = item.getBoundingClientRect();
        if (rect.bottom > bounds.top && rect.top < bounds.bottom) item.classList.add("is-revealed");
      });
    };
    landing.classList.add("is-motion-ready");
    if (reduced || !("IntersectionObserver" in window)) {
      revealItems.forEach((item) => item.classList.add("is-revealed"));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-revealed");
        observer.unobserve(entry.target);
      });
    }, { root: landing, threshold: 0.12, rootMargin: "0px 0px -7% 0px" });
    revealItems.forEach((item) => observer.observe(item));
    let frame = 0;
    const onScroll = () => {
      revealVisibleItems();
      window.dispatchEvent(new CustomEvent<number>("home-landing-scroll", { detail: landing.scrollTop }));
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        landing.style.setProperty("--hero-offset", `${Math.min(landing.scrollTop * 0.055, 66)}px`);
        frame = 0;
      });
    };
    landing.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => { observer.disconnect(); landing.removeEventListener("scroll", onScroll); if (frame) window.cancelAnimationFrame(frame); };
  }, []);
  return <section ref={landingRef} className="landing" aria-label="疫苗智绘产品总览" data-od-id="landing-page" tabIndex={0}>
    <div className="landing-rail landing-rail--left" aria-hidden="true">VACCINE INTELLIGENCE / 2026</div><div className="landing-rail landing-rail--right" aria-hidden="true">01—05</div>
    <section className="landing-hero" data-od-id="hero-section">
      <div className="landing-kicker" data-reveal>VOLUME 01 / IMMUNITY, MADE LEGIBLE</div>
      <div className="landing-hero-grid"><div className="landing-hero-copy"><p className="landing-index" data-reveal>01 / A public health studio</p><h1 data-od-id="hero-heading" data-reveal>Make immunity<br /><em>visible</em><Dot /></h1><p className="landing-lead" data-reveal>An editorial learning space where vaccine questions become clear scientific stories, visual systems and moments worth sharing.</p><button className="landing-text-link" type="button" onClick={() => onNavigate("answer")} data-od-id="hero-cta" data-reveal>进入 AI 问答 <span>↗</span></button></div>
      <div className="landing-plate landing-plate--hero" data-od-id="hero-image-placeholder" data-reveal role="img" aria-label="首屏主视觉占位图"><span className="plate-note">IMAGE PLATE / 01<br />免疫系统主视觉</span><span className="plate-orbit plate-orbit--one" /><span className="plate-orbit plate-orbit--two" /><span className="plate-core" /></div></div>
      <div className="landing-meta-row" data-reveal><span>疫苗智绘</span><span>PUBLIC HEALTH × CREATIVE LEARNING</span><span>SCROLL TO EXPLORE ↓</span></div>
    </section>
    <section className="landing-section landing-section--capabilities" data-od-id="capabilities-section"><div className="landing-section-head" data-reveal><p>02 / THE STUDIO</p><h2>From a question<br />to a <em>living</em> explanation<Dot /></h2></div><div className="landing-statement" data-reveal><p>复杂的免疫学，不该只停留在术语里。疫苗智绘把科学问题拆解为可以理解、体验、创作与复核的知识路径。</p><span>— 为公众、青少年、教师与公共卫生传播者而作</span></div><div className="landing-capability-grid">{capabilities.map(([num, tag, title, body]) => <article className="landing-capability" key={num} data-reveal data-od-id={`capability-${num}`}><span>{num} / {tag}</span><h3>{title}</h3><p>{body}</p>{num === "05" && <button type="button" onClick={() => onNavigate("graph")}>打开知识图谱 ↗</button>}</article>)}</div></section>
    <section className="landing-section landing-section--method" data-od-id="method-section"><div className="landing-method-intro" data-reveal><p>03 / THE METHOD</p><h2>Science needs<br /><em>a point of view</em><Dot /></h2><p>我们将每一次输入视作一次可验证的创作起点，而不是快速答案的终点。</p></div><div className="landing-method-grid"><div className="landing-plate landing-plate--method" data-reveal role="img" aria-label="科学图解拼贴占位图" data-od-id="method-image-placeholder"><span className="plate-note">IMAGE PLATE / 02<br />科学图解拼贴</span><i /><b /></div><ol className="landing-steps">{[["01", "提出主题", "以中文描述你真正想弄明白的疫苗或免疫问题。"], ["02", "建立证据路径", "将术语、机制与叙事结构逐层整理，明确知识边界。"], ["03", "转译为可视化", "生成图解、互动与短视频表达，留下版本与反馈痕迹。"]].map(([num, title, body]) => <li key={num} data-reveal><span>{num}</span><div><strong>{title}</strong><p>{body}</p></div></li>)}</ol></div></section>
    <section className="landing-closing" data-od-id="closing-section"><div className="landing-closing-copy" data-reveal><p>04 / BEGIN HERE</p><h2>Give science<br />a <em>human scale</em><Dot /></h2><p>从一个问题出发，进入属于你的免疫探索现场。</p><button className="landing-primary-button" type="button" onClick={() => onNavigate("answer")} data-od-id="closing-cta">开始一次探索 <span>↗</span></button></div><div className="landing-closing-plate" data-reveal role="img" aria-label="结尾场景占位图" data-od-id="closing-image-placeholder"><span>IMAGE PLATE / 03</span><div className="closing-sun" /></div><footer className="landing-footer" data-reveal><span>疫苗智绘 / VACCINE INTELLIGENCE</span><span>仅供科普参考，不替代专业医疗建议</span><span>© 2026</span></footer></section>
  </section>;
}
