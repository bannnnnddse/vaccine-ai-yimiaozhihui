export interface KnowledgeTopic {
  id: string;
  question: string;
  answer: string;
  image: string;
  imageTitle: string;
  imageDescription: string;
  steps: [string, string, string, string];
}

export const emptyKnowledgeTopic: KnowledgeTopic = {
  id: "empty",
  question: "",
  answer: "",
  image: "",
  imageTitle: "等待您的问题",
  imageDescription: "选择推荐问题可查看对应图解，也可以输入自己的问题。",
  steps: ["", "", "", ""],
};

export const knowledgeTopics: KnowledgeTopic[] = [
  {
    id: "mechanism",
    question: "疫苗是如何进入体内发挥作用的？",
    answer: "疫苗通过注射、口服等方式进入人体后，会向免疫系统展示安全的抗原信息。免疫系统识别这些“外来者”后，会产生相应的抗体和记忆细胞。当真正的病原体再次进入人体时，免疫系统就能更快识别并清除它，从而起到预防疾病的作用。",
    image: "/assets/questions/question-1.png",
    imageTitle: "疫苗在体内的作用过程",
    imageDescription: "从抗原信息进入人体，到免疫系统建立长期记忆。",
    steps: ["疫苗进入人体", "免疫系统识别", "产生免疫反应", "形成免疫记忆并预防疾病"],
  },
  {
    id: "protection-time",
    question: "接种疫苗后多久能产生保护？",
    answer: "多数疫苗接种后需要约 1～2 周建立初步免疫反应，有些疫苗还需要完成多剂次接种才能达到理想保护水平。具体时间会因疫苗种类、接种程序和个人免疫状况而不同，请以接种医生告知为准。",
    image: "/assets/questions/question-2.png",
    imageTitle: "保护力如何逐步建立",
    imageDescription: "免疫反应需要时间，多剂次程序还能帮助巩固免疫记忆。",
    steps: ["完成疫苗接种", "启动免疫应答", "抗体逐步增加", "按程序巩固保护"],
  },
  {
    id: "common-reactions",
    question: "接种疫苗有哪些常见反应？",
    answer: "常见反应包括接种部位疼痛、红肿，以及短暂的低热、乏力或食欲下降，通常较轻并会自行缓解。若出现持续高热、严重过敏表现或其他令人担心的症状，应及时就医并联系接种单位。",
    image: "/assets/questions/question-3.png",
    imageTitle: "接种后的常见反应与观察",
    imageDescription: "区分常见轻微反应与需要及时就医的异常信号。",
    steps: ["留观至少 30 分钟", "观察局部与体温", "适当休息和补水", "异常情况及时就医"],
  },
  {
    id: "coadministration",
    question: "疫苗可以同时接种多种吗？",
    answer: "多种疫苗在符合免疫程序和接种规范时可以同时接种，通常会选择不同接种部位，并分别记录。是否适合同一天接种需结合疫苗说明、儿童健康状况和当地接种安排，由接种医生现场评估。",
    image: "/assets/questions/question-4.png",
    imageTitle: "多种疫苗的规范接种",
    imageDescription: "遵循免疫程序、分开接种部位，并做好完整记录。",
    steps: ["核对免疫程序", "评估当前健康状况", "选择不同接种部位", "完成记录并留观"],
  },
];
