import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cancelImageJob,
  createImageJob,
  editImageJob,
  generateChatAnswer,
  generateConversationTitle,
  getImageJob,
  ChatRequestError,
  ImageJobRequestError,
} from "./generationService";

describe("generateChatAnswer", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("预设问题等待两秒后返回本地答案且不请求 AI", async () => {
    vi.useFakeTimers();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const answerPromise = generateChatAnswer({
      question: "预设问题",
      presetAnswer: "预设答案",
      sessionId: "ignored-session-id",
    });
    await vi.advanceTimersByTimeAsync(1_999);
    expect(fetchSpy).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    await expect(answerPromise).resolves.toEqual({
      answer: "预设答案",
      isVaccineRelated: true,
      sessionId: null,
      sources: [],
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("自定义问题携带会话 ID 并读取后端返回的新会话 ID 与来源", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "这是疫苗科普回答。",
        model: "qwen3.7-plus",
        is_vaccine_related: true,
        session_id: "fresh-session-id",
        sources: [
          { file_name: "指南.pdf", page: 12, content: "相关片段" },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await expect(generateChatAnswer({
      question: "疫苗有什么作用？",
      sessionId: "previous-session-id",
      history: [
        { role: "user", content: "  你好  " },
        { role: "assistant", content: "你好。" },
      ],
    })).resolves.toEqual({
      answer: "这是疫苗科普回答。",
      isVaccineRelated: true,
      sessionId: "fresh-session-id",
      sources: [
        { fileName: "指南.pdf", page: 12, content: "相关片段" },
      ],
    });
    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: "疫苗有什么作用？",
        session_id: "previous-session-id",
        history: [
          { role: "user", content: "你好" },
          { role: "assistant", content: "你好。" },
        ],
      }),
    });
  });

  it("拒绝来源数组缺省的后端响应", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "这是疫苗科普回答。",
        is_vaccine_related: true,
        session_id: "fresh-session-id",
      }),
    }));

    await expect(generateChatAnswer({ question: "疫苗有什么作用？" })).rejects.toThrow(
      "invalid source",
    );
  });

  it("接受并规范化同一文档合并后的多个页码", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "回答［1］",
        is_vaccine_related: true,
        session_id: "fresh-session-id",
        sources: [{
          file_name: "接种规范.pdf",
          page: 3,
          pages: [7, 3, 7],
          content: "第 3 页片段。\n\n第 7 页片段。",
        }],
      }),
    }));

    await expect(generateChatAnswer({ question: "发热能接种吗？" })).resolves.toMatchObject({
      answer: "回答［1］",
      sources: [{ pages: [3, 7] }],
    });
  });

  it("接受没有伪造页码的官方网页来源", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "水痘疫苗接种请以当地接种机构安排为准。",
        is_vaccine_related: true,
        session_id: "fresh-session-id",
        sources: [{
          file_name: "水痘疫苗国家疾控权威接种规范.md",
          content: "水痘疫苗多为非免疫规划疫苗。",
          source_type: "web",
          source_title: "疫苗免疫预防（水痘）",
          source_url: "https://www.chinacdc.cn/example",
          section: "接种建议",
        }],
      }),
    }));

    await expect(generateChatAnswer({ question: "水痘疫苗怎么接种？" })).resolves.toMatchObject({
      sources: [{
        fileName: "水痘疫苗国家疾控权威接种规范.md",
        page: null,
        sourceType: "web",
        sourceTitle: "疫苗免疫预防（水痘）",
        sourceUrl: "https://www.chinacdc.cn/example",
        section: "接种建议",
      }],
    });
  });

  it("接受结构化 PubMed 来源并保留文献元数据", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "外部研究证据回答。",
        is_vaccine_related: true,
        session_id: "fresh-session-id",
        sources: [{
          file_name: "HPV vaccine safety study",
          content: "摘要片段。",
          source_type: "pubmed",
          source_title: "HPV vaccine safety study",
          source_url: "https://pubmed.ncbi.nlm.nih.gov/12345678/",
          title: "HPV vaccine safety study",
          pmid: "12345678",
          journal: "Vaccine",
          year: 2025,
          doi: "10.1/example",
          url: "https://pubmed.ncbi.nlm.nih.gov/12345678/",
          snippet: "摘要片段。",
        }],
      }),
    }));

    await expect(generateChatAnswer({ question: "最新 HPV 疫苗研究" })).resolves.toMatchObject({
      sources: [{
        fileName: "HPV vaccine safety study",
        page: null,
        sourceType: "pubmed",
        sourceTitle: "HPV vaccine safety study",
        sourceUrl: "https://pubmed.ncbi.nlm.nih.gov/12345678/",
        pmid: "12345678",
        journal: "Vaccine",
        year: 2025,
        doi: "10.1/example",
      }],
    });
  });

  it.each([
    [{ file_name: "  ", page: 1, content: "片段" }],
    [{ file_name: "指南.pdf", page: 0, content: "片段" }],
    [{ file_name: "指南.pdf", page: 1, content: "   " }],
  ])("拒绝非法来源条目：%j", async (sources) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "这是疫苗科普回答。",
        is_vaccine_related: true,
        session_id: "fresh-session-id",
        sources,
      }),
    }));

    await expect(generateChatAnswer({ question: "疫苗有什么作用？" })).rejects.toThrow(
      "invalid source",
    );
  });

  it.each([undefined, "   "])("自定义问题在会话 ID 为 %j 时不发送 session_id", async (sessionId) => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "这是疫苗科普回答。",
        is_vaccine_related: true,
        session_id: "fresh-session-id",
        sources: [],
      }),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await generateChatAnswer({ question: "疫苗有什么作用？", sessionId });

    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: "疫苗有什么作用？" }),
    });
  });

  it.each([undefined, "", "   "])("拒绝缺失或空白的后端会话 ID：%j", async (sessionId) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "这是疫苗科普回答。",
        is_vaccine_related: true,
        session_id: sessionId,
      }),
    }));

    await expect(generateChatAnswer({ question: "疫苗有什么作用？" })).rejects.toThrow(
      "invalid session ID",
    );
  });

  it("保留冲突响应的 HTTP 状态码", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
    }));

    await expect(generateChatAnswer({ question: "疫苗有什么作用？" })).rejects.toMatchObject({
      name: "ChatRequestError",
      status: 409,
    } satisfies Partial<ChatRequestError>);
  });

  it("透传后端错误 detail（如网络超时）", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 504,
      json: async () => ({ detail: "网络超时，请稍后重试。" }),
    }));

    await expect(generateChatAnswer({ question: "疫苗有什么作用？" })).rejects.toMatchObject({
      name: "ChatRequestError",
      status: 504,
      detail: "网络超时，请稍后重试。",
    } satisfies Partial<ChatRequestError>);
  });

  it("旧会话失效时自动移除 session_id 并重试当前问题", async () => {
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 409 })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          answer: "这是重新建立会话后的回答。",
          is_vaccine_related: true,
          session_id: "replacement-session-id",
          sources: [],
        }),
      });
    vi.stubGlobal("fetch", fetchSpy);

    await expect(generateChatAnswer({
      question: "水痘疫苗怎么接种？",
      sessionId: "expired-session-id",
      history: [{ role: "user", content: "我想了解水痘疫苗。" }],
    })).resolves.toMatchObject({
      answer: "这是重新建立会话后的回答。",
      sessionId: "replacement-session-id",
    });
    expect(fetchSpy).toHaveBeenNthCalledWith(2, "/api/v1/chat", expect.objectContaining({
      body: JSON.stringify({
        question: "水痘疫苗怎么接种？",
        history: [{ role: "user", content: "我想了解水痘疫苗。" }],
      }),
    }));
  });

  it("用用户的原始中文主题创建正式图解任务", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ job_id: "job-1", stage: "queued" }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    const controller = new AbortController();

    await expect(createImageJob("介绍疫苗如何建立免疫记忆", controller.signal)).resolves.toEqual({
      jobId: "job-1",
      stage: "queued",
      autoRevisionCount: 0,
      traceId: "",
      traceEvents: [],
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/v1/image-jobs",
      expect.objectContaining({
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({ prompt: "介绍疫苗如何建立免疫记忆" }),
      }),
    );
  });

  it("查询已完成任务并接受相对图片 URL", async () => {
    vi.stubGlobal("window", { location: { origin: "http://localhost:5173" } });
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "job-1",
        stage: "completed",
        image_url: "/api/v1/generated-images/job-1.png",
        image_id: "job-1-v0",
        error: null,
        retryable: false,
      }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    const controller = new AbortController();

    await expect(getImageJob("job-1", controller.signal)).resolves.toEqual({
      jobId: "job-1",
      stage: "completed",
      imageUrl: "/api/v1/generated-images/job-1.png",
      imageId: "job-1-v0",
      error: null,
      retryable: false,
      autoRevisionCount: 0,
      traceId: "",
      traceEvents: [],
    });
    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/image-jobs/job-1", { signal: controller.signal });
  });

  it("查询已完成任务并接受绝对图片 URL", async () => {
    vi.stubGlobal("window", { location: { origin: "http://localhost:5173" } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "job-2",
        stage: "completed",
        image_url: "https://api.example.test/api/v1/generated-images/job-2.png",
        image_id: "job-2-v0",
        error: null,
        retryable: false,
      }),
    }));

    await expect(getImageJob("job-2", new AbortController().signal)).resolves.toMatchObject({
      jobId: "job-2",
      imageUrl: "https://api.example.test/api/v1/generated-images/job-2.png",
    });
  });

  it("按后端顺序解析真实图片过程事件", async () => {
    vi.stubGlobal("window", { location: { origin: "http://localhost:5173" } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "job-trace",
        stage: "generating",
        trace_id: "trace-1",
        trace_events: [
          { id: "trace-1-1", stage: "understanding", title: "图解需求已确认", status: "completed", created_at: "2026-08-13T10:00:00Z" },
          { id: "trace-1-2", stage: "generation", title: "正在生成第一版图像", detail: "已提交至 Wan 图像生成模型。", status: "running", created_at: "2026-08-13T10:00:01Z" },
        ],
      }),
    }));

    const result = await getImageJob("job-trace", new AbortController().signal);

    expect(result.traceId).toBe("trace-1");
    expect(result.traceEvents.map((event) => event.stage)).toEqual(["understanding", "generation"]);
    expect(result.traceEvents[1]).toMatchObject({ status: "running", detail: "已提交至 Wan 图像生成模型。" });
  });

  it("解析 Guard 失败候选并提交 authoritative bbox 编辑", async () => {
    vi.stubGlobal("window", { location: { origin: "http://localhost:5173" } });
    const fetchSpy = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        job_id: "job-guard", stage: "awaiting_human_feedback",
        image_url: "/api/v1/generated-images/job-guard-v0.png", image_id: "job-guard-v0",
        candidate_image_url: "/api/v1/generated-images/job-guard-v1-rejected.png",
        auto_revision_count: 1, revision_origin: "initial",
        guard_result: {
          passed: false,
          outside_change_score: 0.2,
          threshold: 0.05,
          changed_outside_bbox: true,
          inside_change_score: 0.08,
          minimum_inside_change: 0.01,
          insufficient_change_inside_bbox: false,
          notes: "框外变化过大",
        },
      }) });
    vi.stubGlobal("fetch", fetchSpy);
    const result = await getImageJob("job-guard", new AbortController().signal);
    expect(result.guardResult?.passed).toBe(false);
    expect(result.candidateImageUrl).toContain("rejected.png");

    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => ({ job_id: "job-guard", stage: "queued" }) });
    await editImageJob("job-guard", "job-guard-v0", [0.1, 0.2, 0.7, 0.8], "修改标题", new AbortController().signal);
    expect(fetchSpy).toHaveBeenLastCalledWith("/api/v1/image-jobs/job-guard/edits", expect.objectContaining({
      body: JSON.stringify({ target_image_id: "job-guard-v0", bbox: [0.1, 0.2, 0.7, 0.8], user_edit_request: "修改标题" }),
    }));
  });

  it("拒绝已完成任务的非本地生成图片地址", async () => {
    vi.stubGlobal("window", { location: { origin: "http://localhost:5173" } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job_id: "job-3",
        stage: "completed",
        image_url: "https://untrusted.example/image.png",
      }),
    }));

    await expect(getImageJob("job-3", new AbortController().signal)).rejects.toThrow(
      "invalid generated image URL",
    );
  });

  it("取消任务使用 DELETE", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchSpy);

    await expect(cancelImageJob("job-1")).resolves.toBeUndefined();
    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/image-jobs/job-1", { method: "DELETE" });
  });

  it.each([404, 409, 500])("保留失败请求的 HTTP %i 状态码", async (status) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status,
      json: async () => ({ detail: "request failed" }),
    }));

    await expect(createImageJob("疫苗机制", new AbortController().signal)).rejects.toMatchObject({
      name: "ImageJobRequestError",
      status,
    } satisfies Partial<ImageJobRequestError>);
  });

  it("成功响应不是 JSON 时报错", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => { throw new SyntaxError("Unexpected token"); },
    }));

    await expect(createImageJob("疫苗机制", new AbortController().signal)).rejects.toThrow(
      "invalid JSON response",
    );
  });
});

describe("generateConversationTitle", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses the internal title endpoint and validates its response", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ title: "17岁男性九价HPV接种" }),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await expect(generateConversationTitle([
      { role: "user", content: "我17岁男生，还能打九价HPV疫苗吗？" },
      { role: "assistant", content: "是否适合接种需要结合当地程序与接种门诊评估。" },
    ])).resolves.toBe("17岁男性九价HPV接种");
    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/conversations/title", expect.objectContaining({
      method: "POST",
    }));
  });

  it("rejects malformed title responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ title: "" }),
    }));
    await expect(generateConversationTitle([
      { role: "user", content: "问题" },
      { role: "assistant", content: "回答" },
    ])).rejects.toThrow("invalid title");
  });
});
