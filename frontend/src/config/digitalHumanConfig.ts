export interface DigitalHumanTemplate {
  id: string;
  title: string;
  prompt: string;
}

export const DIGITAL_HUMAN_CONFIG = {
  timing: {
    welcomeDurationMs: 4_500,
    idleHintDelayMs: 3_000,
    errorDurationMs: 4_000,
    editHintDurationMs: 4_500,
    successDurationMs: 800,
  },
  bubbles: {
    qaWelcome: "不知道怎么问？点击我看看模板吧~",
    qaIdle: "不知道怎么问？点一下我，可以看看常见的疫苗问题。",
    qaError: "这次没有顺利回答，可以重试或换一种问法。",
    imageWelcome: "想把疫苗知识变成图？描述你想了解的内容就可以。",
    imageIdle: "没有灵感的话，可以点一下我，从几种常用的医学图解开始。",
    imageError: "这次图片没有生成成功，可以调整描述后再试一次。",
    imageEditHint: "还想调整的话，可以框选图片中的区域，再告诉我需要怎么改。",
  },
  panelTitles: {
    qa: "你可以这样问",
    image: "试试这些图解",
  },
  qaTemplates: [
    {
      id: "qa-vaccination-preparation",
      title: "接种前须知",
      prompt: "接种[疫苗名称]前需要注意什么？哪些情况应该暂缓接种？",
    },
    {
      id: "qa-adverse-reactions",
      title: "不良反应",
      prompt: "接种[疫苗名称]后常见的不良反应有哪些？哪些属于正常反应，出现哪些情况需要及时就医？",
    },
    {
      id: "qa-vaccination-schedule",
      title: "接种程序",
      prompt: "[年龄/人群]接种[疫苗名称]通常需要几针？推荐接种间隔多久？如果其中一针延迟了应该怎么办？",
    },
    {
      id: "qa-vaccine-choice",
      title: "疫苗选择",
      prompt: "[年龄/人群]应该如何选择[疫苗A]和[疫苗B]？请从适用人群、接种程序和保护范围等方面解释。",
    },
    {
      id: "qa-special-populations",
      title: "特殊人群",
      prompt: "[儿童/孕妇/老年人/慢性病患者]是否可以接种[疫苗名称]？接种前后有哪些需要特别注意的地方？",
    },
    {
      id: "qa-coadministration",
      title: "联合接种",
      prompt: "[疫苗A]和[疫苗B]可以同时接种吗？如果不能同时接种，一般需要间隔多久？",
    },
  ] satisfies DigitalHumanTemplate[],
  imageTemplates: [
    {
      id: "image-immune-mechanism",
      title: "免疫机制图",
      prompt: "生成一张医学科普风格的疫苗免疫机制图，主题为“[需要解释的疫苗或免疫机制]”。清晰表现疫苗进入人体后，从抗原进入、抗原呈递、免疫细胞识别，到B细胞产生抗体并形成免疫记忆的主要过程。画面结构清晰、医学逻辑准确、适合普通公众理解，避免过度复杂的专业细节，整体保持现代医学科普插画风格。",
    },
    {
      id: "image-vaccination-process",
      title: "接种流程图",
      prompt: "生成一张面向普通公众的疫苗接种流程科普图，主题为“[疫苗名称或接种主题]”。按照清晰的步骤展示接种前准备、现场接种、接种后留观以及后续注意事项。使用简洁明确的视觉层级和步骤关系，使用户能够快速理解整个接种流程。整体采用现代、干净、友好的医学科普视觉风格。",
    },
    {
      id: "image-health-education-scene",
      title: "场景科普图",
      prompt: "生成一张疫苗健康教育场景科普插图，主题为“[需要科普的疫苗知识]”。以真实但亲和的医疗或接种场景表现核心知识，例如儿童与家长、接种人员、疫苗接种或接种后护理等。画面应突出一个明确的科普重点，人物关系自然，医学场景合理，视觉风格清晰友好，适合面向公众进行疫苗健康教育。",
    },
  ] satisfies DigitalHumanTemplate[],
} as const;
