import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Download,
  FilePenLine,
  Plus,
  RotateCcw,
  Send,
  Trash2,
  Upload,
} from "lucide-react";
import { classroomApi, lessonVersionExportUrl } from "../lib/api";
import type {
  LessonReviewMessage,
  LessonSlide,
  LessonVersion,
} from "../types/workflow";
import { LessonSlideCanvas } from "./LessonSlideCanvas";
import "./LessonReviewWorkspace.css";

interface Props {
  runId: string;
  version: LessonVersion;
  maxRounds: number;
  reviewPlan?: Record<string, string>;
  focusSlideId?: string | null;
  onVersionChange: (version: LessonVersion) => void;
  onApproved: (info?: { awaitingStart?: boolean }) => Promise<void> | void;
  /** 勾选「教学设计后暂停」时为 true: 确认 PPT 后停在审阅门, 不自动进课堂 */
  pauseAfterDesign?: boolean;
  onError: (message: string) => void;
}

interface DeletedSlide {
  slide: LessonSlide;
  index: number;
}

export function LessonReviewWorkspace({
  runId,
  version,
  maxRounds,
  reviewPlan = {},
  focusSlideId = null,
  onVersionChange,
  onApproved,
  pauseAfterDesign = false,
  onError,
}: Props) {
  const [current, setCurrent] = useState(0);
  const [messages, setMessages] = useState<LessonReviewMessage[]>([]);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState<"save" | "ai" | "approve" | "import" | null>(
    null,
  );
  const [editing, setEditing] = useState<LessonSlide | null>(null);
  const [deleted, setDeleted] = useState<DeletedSlide | null>(null);
  const [feedback, setFeedback] = useState("");
  const [sideWidth, setSideWidth] = useState(
    () =>
      Number(window.localStorage.getItem("platform.ppt-review-width")) || 330,
  );
  const sideWidthRef = useRef(sideWidth);
  const fileRef = useRef<HTMLInputElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const swipeStart = useRef<number | null>(null);
  const slide =
    version.slides[Math.min(current, Math.max(0, version.slides.length - 1))];
  const canEdit = version.status === "draft";

  useEffect(() => {
    setCurrent((index) =>
      Math.min(index, Math.max(0, version.slides.length - 1)),
    );
  }, [version.slides.length]);

  useEffect(() => {
    if (!focusSlideId) return;
    const index = version.slides.findIndex((item) => item.slide_id === focusSlideId);
    if (index >= 0) setCurrent(index);
  }, [focusSlideId, version.slides]);

  useEffect(() => {
    let active = true;
    classroomApi
      .listReviewMessages(runId, version.id)
      .then((result) => {
        if (active) setMessages(result.items);
      })
      .catch((reason) =>
        onError(
          reason instanceof Error ? reason.message : "PPT 审阅会话加载失败",
        ),
      );
    return () => {
      active = false;
    };
  }, [runId, version.id]);

  useEffect(() => {
    if (chatRef.current)
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages.length, busy]);

  useEffect(() => {
    if (busy !== "ai") return;
    let active = true;
    const refreshProgress = async () => {
      try {
        const result = await classroomApi.listReviewMessages(runId, version.id);
        if (active) setMessages(result.items);
      } catch {
        // The main revise request owns the error state. Progress polling is best effort.
      }
    };
    const timer = window.setInterval(() => void refreshProgress(), 650);
    void refreshProgress();
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [busy, runId, version.id]);

  const persist = async (slides: LessonSlide[]) => {
    if (!canEdit) {
      const reason = "当前版本已经进入课堂或定稿，不能直接修改。请从待审阅草稿进入逐页对话。";
      onError(reason);
      throw new Error(reason);
    }
    setBusy("save");
    try {
      const updated = await classroomApi.updateLessonDraft(runId, {
        ...version,
        slides,
      });
      onVersionChange(updated);
      return updated;
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "PPT 草稿保存失败");
      throw reason;
    } finally {
      setBusy(null);
    }
  };

  const saveEditor = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editing) return;
    const data = new FormData(event.currentTarget);
    const title = String(data.get("title") || "").trim();
    const bullets = String(data.get("bullets") || "")
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
    if (!title || !bullets.length) {
      onError("页面标题和至少一条内容要点不能为空。");
      return;
    }
    const originalBlocks = editing.speaker_notes?.length
      ? editing.speaker_notes
      : [
          {
            block_id: `${editing.slide_id}:block_001`,
            order: 1,
            block_type: "explanation",
            content: "",
            estimated_seconds: Math.max(
              15,
              Math.round((editing.estimated_minutes || 1) * 60),
            ),
            knowledge_point_ids: editing.knowledge_points || [],
          },
        ];
    const speakerNotes = originalBlocks.map((block, index) => ({
      ...block,
      order: index + 1,
      content: String(data.get(`note-${index}`) || "").trim(),
      estimated_seconds: Math.max(
        1,
        Number(data.get(`seconds-${index}`)) || block.estimated_seconds || 30,
      ),
    }));
    if (speakerNotes.some((block) => !block.content)) {
      onError("每个讲稿 Block 都需要保留讲授内容。");
      return;
    }
    const revised: LessonSlide = {
      ...editing,
      title,
      purpose: String(data.get("purpose") || "").trim(),
      ppt_content: {
        ...editing.ppt_content,
        title,
        subtitle: String(data.get("subtitle") || "").trim(),
        bullets,
        examples: String(data.get("examples") || "")
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean),
      },
      speaker_notes: speakerNotes,
    };
    const slides = version.slides.map((item) =>
      item.slide_id === revised.slide_id ? revised : item,
    );
    await persist(slides);
    setEditing(null);
    setFeedback(`${revised.slide_id} 已保存，稳定 ID 保持不变。`);
  };

  const addSlide = async () => {
    const ids = new Set(version.slides.map((item) => item.slide_id));
    let serial = 1;
    while (ids.has(`slide_custom_${String(serial).padStart(3, "0")}`))
      serial += 1;
    const slideId = `slide_custom_${String(serial).padStart(3, "0")}`;
    const reference = slide || version.slides[version.slides.length - 1];
    const added: LessonSlide = {
      slide_id: slideId,
      order: current + 2,
      title: "新增教学页面",
      purpose: "补充当前知识点的讲解或应用",
      learning_objectives:
        reference?.learning_objectives || version.learning_objectives || [],
      knowledge_points:
        reference?.knowledge_points || version.knowledge_points || [],
      estimated_minutes: 1,
      ppt_content: {
        title: "新增教学页面",
        subtitle: "待完善",
        bullets: ["填写本页核心观点"],
      },
      speaker_notes: [
        {
          block_id: `${slideId}:block_001`,
          order: 1,
          block_type: "explanation",
          content: "填写本页教师讲稿。",
          estimated_seconds: 60,
          knowledge_point_ids: reference?.knowledge_points || [],
        },
      ],
      interaction_anchors: [],
      expected_misconceptions: [],
    };
    const slides = [...version.slides];
    slides.splice(current + 1, 0, added);
    const updated = await persist(
      slides.map((item, index) => ({ ...item, order: index + 1 })),
    );
    setCurrent(updated.slides.findIndex((item) => item.slide_id === slideId));
    setEditing(
      updated.slides.find((item) => item.slide_id === slideId) || null,
    );
    setDeleted(null);
  };

  const deleteSlide = async () => {
    if (
      !slide ||
      version.slides.length <= 1 ||
      !window.confirm(
        `删除第 ${current + 1} 页“${slide.title}”？其他页面的稳定 ID 不会改变。`,
      )
    )
      return;
    const removed = { slide, index: current };
    const updated = await persist(
      version.slides
        .filter((item) => item.slide_id !== slide.slide_id)
        .map((item, index) => ({ ...item, order: index + 1 })),
    );
    setDeleted(removed);
    setCurrent(Math.min(current, updated.slides.length - 1));
    setFeedback(`${slide.slide_id} 已删除，可撤销。`);
  };

  const undoDelete = async () => {
    if (!deleted) return;
    const slides = [...version.slides];
    slides.splice(Math.min(deleted.index, slides.length), 0, deleted.slide);
    const updated = await persist(
      slides.map((item, index) => ({ ...item, order: index + 1 })),
    );
    setCurrent(
      updated.slides.findIndex(
        (item) => item.slide_id === deleted.slide.slide_id,
      ),
    );
    setDeleted(null);
    setFeedback("已恢复刚才删除的页面。");
  };

  const sendInstruction = async (event: FormEvent) => {
    event.preventDefault();
    const content = instruction.trim();
    if (!canEdit || !content || !slide || busy) return;
    setMessages((items) => [
      ...items,
      {
        message_id: `pending:${Date.now()}`,
        run_id: runId,
        version_id: version.id,
        slide_id: slide.slide_id,
        role: "user",
        content,
        created_at: new Date().toISOString(),
      },
    ]);
    setInstruction("");
    setBusy("ai");
    try {
      const response = await classroomApi.reviseSlide(
        runId,
        version.id,
        slide.slide_id,
        content,
      );
      onVersionChange(response.lesson_version);
      const restored = await classroomApi.listReviewMessages(runId, version.id);
      setMessages(restored.items);
      setFeedback(`${slide.slide_id} 已由 Teacher Agent 局部完善。`);
    } catch (reason) {
      onError(
        reason instanceof Error
          ? reason.message
          : "Teacher Agent 未能完成本页修改",
      );
      const restored = await classroomApi
        .listReviewMessages(runId, version.id)
        .catch(() => ({ items: [] as LessonReviewMessage[] }));
      setMessages(restored.items);
    } finally {
      setBusy(null);
    }
  };

  const importDeck = async (file?: File) => {
    if (!file) return;
    setBusy("import");
    setFeedback("正在校验导入文案…");
    try {
      const payload = JSON.parse(await file.text());
      const rawSlides = Array.isArray(payload.slides) ? payload.slides : [];
      if (!rawSlides.length) throw new Error("导入文件缺少非空 slides 数组");
      const imported: LessonSlide[] = rawSlides.map(
        (raw: Record<string, unknown>, index: number) =>
          normalizeImportedSlide(raw, index, version),
      );
      const updated = await classroomApi.updateLessonDraft(runId, {
        ...version,
        title: String(payload.title || version.title),
        estimated_minutes: Number(
          payload.estimated_minutes ||
            payload.duration_minutes ||
            version.estimated_minutes,
        ),
        slides: imported,
      });
      onVersionChange(updated);
      setCurrent(0);
      setDeleted(null);
      setFeedback(`导入成功：${updated.slides.length} 页，等待审阅确认。`);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "PPT 文案导入失败");
      setFeedback("导入失败，请使用本平台导出的 JSON 格式。");
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const approve = async (autoStart = true) => {
    if (busy) return;
    setBusy("approve");
    try {
      // autoStart=false: 只把版本置为 ready 并停在审阅门(「教学设计后暂停」勾选时的行为)
      const result = await classroomApi.approveLessonVersion(runId, version.id, maxRounds, { autoStart });
      await onApproved({ awaitingStart: Boolean(result?.awaiting_start) });
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "PPT 确认失败");
    } finally {
      setBusy(null);
    }
  };

  const resizeStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const startX = event.clientX;
    const initial = sideWidth;
    const move = (next: globalThis.PointerEvent) => {
      sideWidthRef.current = Math.min(
        460,
        Math.max(280, initial + startX - next.clientX),
      );
      setSideWidth(sideWidthRef.current);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.localStorage.setItem(
        "platform.ppt-review-width",
        String(sideWidthRef.current),
      );
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const setStoredSideWidth = (value: number) => {
    const next = Math.min(460, Math.max(280, value));
    sideWidthRef.current = next;
    setSideWidth(next);
    window.localStorage.setItem("platform.ppt-review-width", String(next));
  };

  const noteText = useMemo(
    () => (slide?.speaker_notes || []).map((item) => item.content).join("\n\n"),
    [slide],
  );
  const latestProcessMessage = [...messages]
    .reverse()
    .find((message) => message.role === "system");
  return (
    <section
      className="lesson-review-workspace"
      style={{ "--review-side-width": `${sideWidth}px` } as CSSProperties}
    >
      <header className="lesson-review-toolbar">
        <div>
          <strong>PPT V{version.version_number} 逐页审阅</strong>
          <span>
            {version.slides.length} 页 · {version.estimated_minutes || 0} 分钟
            {canEdit ? " · 草稿可修改" : " · 已锁定，仅供查看"}
          </span>
        </div>
        <div className="lesson-review-actions">
          <input
            ref={fileRef}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(event) => void importDeck(event.target.files?.[0])}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={!canEdit || Boolean(busy)}
          >
            <Upload size={14} />
            导入文案
          </button>
          <a href={lessonVersionExportUrl(runId, version.id, "json")}>
            <Download size={14} />
            导出文案
          </a>
          <a href={lessonVersionExportUrl(runId, version.id, "html")}>
            <Download size={14} />
            导出演示稿
          </a>
          {deleted && (
            <button type="button" onClick={() => void undoDelete()}>
              <RotateCcw size={14} />
              撤销删除
            </button>
          )}
        </div>
      </header>
      {feedback && (
        <div className="lesson-review-feedback" role="status">
          <Check size={13} />
          {feedback}
        </div>
      )}
      {Object.keys(reviewPlan).length > 0 && (
        <section className="lesson-review-plan-context" aria-label="本轮教师修改计划">
          <header><strong>Teacher Agent 已确认的逐页修改计划</strong><span>请在下方逐页编辑，确认后再开始下一轮</span></header>
          <div>{Object.entries(reviewPlan).map(([slideId, plan]) => <p key={slideId}><b>{slideId}</b>{plan}</p>)}</div>
        </section>
      )}
      <div className="lesson-review-layout">
        <aside className="lesson-thumbnails">
          <header>
            <strong>页面</strong>
            <span>{version.slides.length}</span>
          </header>
          <div>
            {version.slides.map((item, index) => (
              <button
                type="button"
                className={index === current ? "active" : ""}
                onClick={() => setCurrent(index)}
                key={item.slide_id}
              >
                <LessonSlideCanvas
                  slide={item}
                  index={index}
                  total={version.slides.length}
                  compact
                />
                <span>
                  <b>{index + 1}</b>
                  {item.slide_id}
                </span>
              </button>
            ))}
          </div>
        </aside>
        <main className="lesson-review-main">
          <div className="lesson-slide-toolbar">
            <strong>
              第 {current + 1} / {version.slides.length} 页
            </strong>
            <span>{slide?.slide_id}</span>
            <div>
              <button
                type="button"
                onClick={() => setCurrent((index) => Math.max(0, index - 1))}
                disabled={current === 0}
                aria-label="上一页"
              >
                <ArrowLeft size={15} />
              </button>
              <button
                type="button"
                onClick={() =>
                  setCurrent((index) =>
                    Math.min(version.slides.length - 1, index + 1),
                  )
                }
                disabled={current >= version.slides.length - 1}
                aria-label="下一页"
              >
                <ArrowRight size={15} />
              </button>
              <button
                type="button"
                onClick={() => setEditing(slide)}
                disabled={!canEdit || !slide || Boolean(busy)}
              >
                <FilePenLine size={14} />
                编辑
              </button>
              <button
                type="button"
                onClick={() => void addSlide()}
                disabled={!canEdit || Boolean(busy)}
              >
                <Plus size={14} />
                新增
              </button>
              <button
                className="danger"
                type="button"
                onClick={() => void deleteSlide()}
                disabled={!canEdit || version.slides.length <= 1 || Boolean(busy)}
              >
                <Trash2 size={14} />
                删除
              </button>
            </div>
          </div>
          <div
            className="lesson-slide-stage"
            onPointerDown={(event) => {
              swipeStart.current = event.clientX;
            }}
            onPointerUp={(event) => {
              if (swipeStart.current === null) return;
              const delta = event.clientX - swipeStart.current;
              if (Math.abs(delta) > 48)
                setCurrent((index) =>
                  Math.min(
                    version.slides.length - 1,
                    Math.max(0, index + (delta < 0 ? 1 : -1)),
                  ),
                );
              swipeStart.current = null;
            }}
          >
            <LessonSlideCanvas
              slide={slide}
              index={current}
              total={version.slides.length}
            />
          </div>
          <section className="lesson-note-preview">
            <header>
              <strong>本页教师讲课稿</strong>
              <span>
                约{" "}
                {(slide?.speaker_notes || []).reduce(
                  (total, item) => total + (item.estimated_seconds || 0),
                  0,
                )}{" "}
                秒
              </span>
            </header>
            <p>{noteText || "本页暂无教师讲稿。"}</p>
          </section>
        </main>
        <div
          className="lesson-review-resizer"
          role="separator"
          aria-label="调整 Teacher Agent 会话宽度"
          aria-orientation="vertical"
          aria-valuemin={280}
          aria-valuemax={460}
          aria-valuenow={sideWidth}
          tabIndex={0}
          onPointerDown={resizeStart}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") setStoredSideWidth(sideWidth + 16);
            if (event.key === "ArrowRight") setStoredSideWidth(sideWidth - 16);
          }}
          onDoubleClick={() => setStoredSideWidth(330)}
        />
        <aside className="lesson-review-chat">
          <header>
            <span className="teacher-avatar">师</span>
            <div>
              <strong>Teacher Agent</strong>
              <small>
                {canEdit
                  ? `正在讨论 ${slide?.slide_id || "--"}，只修改当前页`
                  : "该版本已锁定，当前对话为只读记录"}
              </small>
            </div>
          </header>
          <div className="lesson-review-messages" ref={chatRef}>
            {messages.length ? (
              messages.map((message) => (
                <article className={message.role} key={message.message_id}>
                  <span>
                    {message.role === "user"
                      ? "你"
                      : message.role === "teacher"
                        ? "Teacher Agent"
                        : "Teacher Agent · 运行阶段"}
                  </span>
                  <p>{message.role === "system" ? message.content.replace(/^Teacher Agent\s*·\s*/, "") : message.content}</p>
                </article>
              ))
            ) : (
              <p className="lesson-review-chat-empty">
                Teacher Agent 会在 PPT 生成后说明审阅方式。
              </p>
            )}
            {busy === "ai" && (
              <article className="system teacher-process-live">
                <span>Teacher Agent · 运行阶段</span>
                <p className="typing">
                  {latestProcessMessage?.content.replace(/^Teacher Agent\s*·\s*/, "") || "正在读取当前页并理解你的修改意见…"}
                </p>
              </article>
            )}
          </div>
          <form onSubmit={sendInstruction}>
            <label htmlFor="lesson-review-instruction">当前页修改意见</label>
            <textarea
              id="lesson-review-instruction"
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              rows={3}
              disabled={!canEdit || Boolean(busy)}
              placeholder="例如：精简要点，补充一个可观察的课堂案例"
            />
            <div className="lesson-review-quick">
              <button
                type="button"
                disabled={!canEdit || Boolean(busy)}
                onClick={() =>
                  setInstruction("精简本页内容，每条只保留一个核心信息")
                }
              >
                精简
              </button>
              <button
                type="button"
                disabled={!canEdit || Boolean(busy)}
                onClick={() =>
                  setInstruction("补充一个与当前知识点相关的课堂应用案例")
                }
              >
                补案例
              </button>
              <button
                type="button"
                disabled={!canEdit || Boolean(busy)}
                onClick={() =>
                  setInstruction("增加一个理解检查，并同步完善教师讲稿")
                }
              >
                加互动
              </button>
            </div>
            <button
              className="lesson-review-send"
              type="submit"
              disabled={!canEdit || !instruction.trim() || Boolean(busy)}
            >
              <Send size={14} />
              {busy === "ai" ? "处理中" : "发送并完善当前页"}
            </button>
          </form>
          <div className="lesson-approve">
            <button
              type="button"
              onClick={() => void approve(!pauseAfterDesign)}
              disabled={!canEdit || Boolean(busy)}
            >
              <Check size={15} />
              {busy === "approve" ? "正在启动课堂…" : "确认 PPT，进入课堂演练"}
            </button>
            <small>
              {canEdit
                ? "确认后当前版本冻结；课堂将严格执行这份逐页 PPT 与讲稿。"
                : "当前版本已冻结；请回到待审阅草稿修改后再开启新一轮。"}
            </small>
          </div>
        </aside>
      </div>
      {editing && (
        <div
          className="lesson-editor-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setEditing(null);
          }}
        >
          <form
            className="lesson-editor-dialog"
            onSubmit={saveEditor}
            role="dialog"
            aria-modal="true"
            aria-labelledby="lesson-editor-title"
          >
            <header>
              <div>
                <span>{editing.slide_id}</span>
                <h3 id="lesson-editor-title">编辑第 {current + 1} 页</h3>
              </div>
              <button
                type="button"
                onClick={() => setEditing(null)}
                aria-label="关闭编辑器"
              >
                ×
              </button>
            </header>
            <label>
              页面标题
              <input
                name="title"
                defaultValue={editing.ppt_content?.title || editing.title}
                autoFocus
              />
            </label>
            <label>
              副标题
              <input
                name="subtitle"
                defaultValue={editing.ppt_content?.subtitle || ""}
              />
            </label>
            <label>
              教学目的
              <input name="purpose" defaultValue={editing.purpose || ""} />
            </label>
            <label>
              内容要点（每行一条）
              <textarea
                name="bullets"
                rows={5}
                defaultValue={(editing.ppt_content?.bullets || []).join("\n")}
              />
            </label>
            <label>
              案例（每行一个）
              <textarea
                name="examples"
                rows={3}
                defaultValue={(editing.ppt_content?.examples || []).join("\n")}
              />
            </label>
            <section className="lesson-editor-note-list">
              <header>
                <strong>逐 Block 教师讲课稿</strong>
                <span>稳定 block_id 将原样保留，互动锚点不会失效</span>
              </header>
              {(editing.speaker_notes?.length
                ? editing.speaker_notes
                : [
                    {
                      block_id: `${editing.slide_id}:block_001`,
                      block_type: "explanation",
                      content: "",
                      estimated_seconds: 60,
                    },
                  ]
              ).map((block, index) => (
                <fieldset key={block.block_id}>
                  <legend>
                    <b>
                      {index + 1}. {block.block_type || "explanation"}
                    </b>
                    <code>{block.block_id}</code>
                  </legend>
                  <label>
                    讲授内容
                    <textarea
                      name={`note-${index}`}
                      rows={5}
                      defaultValue={block.content}
                    />
                  </label>
                  <label>
                    预计秒数
                    <input
                      name={`seconds-${index}`}
                      type="number"
                      min={1}
                      max={3600}
                      defaultValue={block.estimated_seconds || 30}
                    />
                  </label>
                </fieldset>
              ))}
            </section>
            <footer>
              <button type="button" onClick={() => setEditing(null)}>
                取消
              </button>
              <button
                className="primary"
                type="submit"
                disabled={busy === "save"}
              >
                {busy === "save" ? "保存中…" : "保存当前页"}
              </button>
            </footer>
          </form>
        </div>
      )}
    </section>
  );
}

function normalizeImportedSlide(
  raw: Record<string, unknown>,
  index: number,
  version: LessonVersion,
): LessonSlide {
  const ppt =
    raw.ppt_content && typeof raw.ppt_content === "object"
      ? (raw.ppt_content as Record<string, unknown>)
      : raw;
  const slideId = String(
    raw.slide_id || raw.id || `slide_${String(index + 1).padStart(3, "0")}`,
  );
  const title = String(ppt.title || raw.title || "").trim();
  const bullets = Array.isArray(ppt.bullets)
    ? ppt.bullets
        .map(String)
        .map((item) => item.trim())
        .filter(Boolean)
    : [];
  if (!title || !bullets.length)
    throw new Error(`第 ${index + 1} 页缺少标题或内容要点`);
  const notes =
    Array.isArray(raw.speaker_notes) && raw.speaker_notes.length
      ? raw.speaker_notes
      : [
          {
            content: String(raw.note || "请补充本页教师讲稿。"),
            estimated_seconds: Math.max(15, Number(raw.minutes || 1) * 60),
          },
        ];
  const normalizedNotes = notes.map((item: unknown, noteIndex: number) => {
    const note = item as Record<string, unknown>;
    return {
      block_id: String(
        note.block_id ||
          `${slideId}:block_${String(noteIndex + 1).padStart(3, "0")}`,
      ),
      order: noteIndex + 1,
      block_type: normalizeBlockType(note.block_type),
      content: String(note.content || raw.note || "请补充本页教师讲稿。"),
      estimated_seconds: Math.max(1, Number(note.estimated_seconds || 30)),
      knowledge_point_ids: Array.isArray(note.knowledge_point_ids)
        ? note.knowledge_point_ids.map(String)
        : [],
    };
  });
  const blockIds = new Set(normalizedNotes.map((item) => item.block_id));
  return {
    slide_id: slideId,
    order: index + 1,
    title,
    purpose: String(raw.purpose || ""),
    learning_objectives: Array.isArray(raw.learning_objectives)
      ? raw.learning_objectives.map(String)
      : version.learning_objectives || [],
    knowledge_points: Array.isArray(raw.knowledge_points)
      ? raw.knowledge_points.map(String)
      : version.knowledge_points || [],
    estimated_minutes: Math.max(
      0.25,
      Number(raw.estimated_minutes || raw.minutes || 1),
    ),
    ppt_content: {
      title,
      subtitle: String(ppt.subtitle || ""),
      bullets,
      examples: Array.isArray(ppt.examples)
        ? ppt.examples.map(String)
        : raw.example
          ? [String(raw.example)]
          : [],
      code_blocks: Array.isArray(ppt.code_blocks)
        ? (ppt.code_blocks as Array<Record<string, unknown>>)
        : [],
      visual_instruction: String(ppt.visual_instruction || ""),
    },
    speaker_notes: normalizedNotes,
    interaction_anchors: Array.isArray(raw.interaction_anchors)
      ? raw.interaction_anchors.map((item: unknown, anchorIndex: number) =>
          normalizeImportedAnchor(
            item as Record<string, unknown>,
            anchorIndex,
            slideId,
            blockIds,
          ),
        )
      : [],
    expected_misconceptions: Array.isArray(raw.expected_misconceptions)
      ? raw.expected_misconceptions.map(
          (item: unknown, misconceptionIndex: number) =>
            normalizeImportedMisconception(
              item as Record<string, unknown>,
              misconceptionIndex,
              slideId,
            ),
        )
      : [],
  };
}

function normalizeBlockType(value: unknown) {
  const type = String(value || "explanation").toLowerCase();
  const aliases: Record<string, string> = {
    opening: "explanation",
    demonstration: "example",
    question_prep: "question",
  };
  const normalized = aliases[type] || type;
  return [
    "explanation",
    "question",
    "example",
    "feedback",
    "summary",
    "transition",
    "other",
  ].includes(normalized)
    ? normalized
    : "other";
}

function normalizeImportedAnchor(
  raw: Record<string, unknown>,
  index: number,
  slideId: string,
  blockIds: Set<string>,
) {
  const sourceType = String(
    raw.type || raw.interaction_type || "question",
  ).toLowerCase();
  const types: Record<string, string> = {
    check_understanding: "check",
    concept_question: "question",
    application_question: "practice",
    prediction: "question",
  };
  const type = [
    "question",
    "check",
    "discussion",
    "practice",
    "reflection",
    "other",
  ].includes(types[sourceType] || sourceType)
    ? types[sourceType] || sourceType
    : "other";
  const rawLevel = String(raw.target_student_level || "all").toLowerCase();
  const levels: Record<string, string> = {
    advanced: "high",
    intermediate: "medium",
    basic: "low",
    beginner: "low",
  };
  const targetLevel = ["high", "medium", "low", "all"].includes(
    levels[rawLevel] || rawLevel,
  )
    ? levels[rawLevel] || rawLevel
    : "all";
  const requestedBlock = String(raw.after_block_id || "");
  return {
    ...raw,
    interaction_id: String(
      raw.interaction_id ||
        `${slideId}:interaction_${String(index + 1).padStart(3, "0")}`,
    ),
    type,
    objective: String(raw.objective || "检查本页理解"),
    planned_question: String(
      raw.planned_question || "请说明你对本页核心内容的理解。",
    ),
    target_student_level: targetLevel,
    after_block_id: blockIds.has(requestedBlock) ? requestedBlock : null,
  };
}

function normalizeImportedMisconception(
  raw: Record<string, unknown>,
  index: number,
  slideId: string,
) {
  const correction = String(
    raw.recommended_correction ||
      raw.correction_strategy ||
      "结合本页示例进行澄清。",
  );
  return {
    ...raw,
    misconception_id: String(
      raw.misconception_id ||
        `${slideId}:misconception_${String(index + 1).padStart(3, "0")}`,
    ),
    description: String(raw.description || "待确认的常见误区"),
    correction_strategy: correction,
    recommended_correction: correction,
  };
}
