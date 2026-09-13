import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  Eye,
  History,
  ShieldCheck,
} from "lucide-react";
import type {
  ClassroomEvent,
  ClassroomState,
  LessonSlide,
  LessonVersion,
  StudentCognitiveState,
  StudentPersona,
  SupervisorObservation,
} from "../types/workflow";
import { ClassroomGroupChat } from "./ClassroomGroupChat";
import { ClassroomScene3D } from "./ClassroomScene3D";
import { LessonSlideCanvas } from "./LessonSlideCanvas";
import "./ClassroomRehearsalStage.css";

interface Props {
  version: LessonVersion;
  state: ClassroomState | null;
  events: ClassroomEvent[];
  observations: SupervisorObservation[];
  studentPersonas: StudentPersona[];
  studentCognitiveStates: StudentCognitiveState[];
  intervening: boolean;
  roundStatus?: string;
  onIntervene: (content: string) => Promise<void>;
  onControl: (action: "pause" | "resume" | "stop") => Promise<void>;
}

const AGENT_NAMES: Record<string, string> = {
  teacher: "教师 Agent",
  "student:high": "拓展型学生 A",
  "student:medium": "进阶型学生 B",
  "student:low": "基础型学生 C",
  supervisor: "督导 Agent",
};

const AGENT_KEYS = [
  "teacher",
  "student:high",
  "student:medium",
  "student:low",
  "supervisor",
] as const;

function normalizeAgent(id?: string | null) {
  const value = (id || "").toLowerCase();
  if (value.includes("teacher")) return "teacher";
  if (value.includes("supervisor")) return "supervisor";
  if (value.includes("high")) return "student:high";
  if (value.includes("medium")) return "student:medium";
  if (value.includes("low") || value.includes("basic")) return "student:low";
  return "teacher";
}

export function ClassroomRehearsalStage({
  version,
  state,
  events,
  observations,
  studentPersonas,
  studentCognitiveStates,
  intervening,
  roundStatus,
  onIntervene,
  onControl,
}: Props) {
  const activeIndex = Math.min(
    state?.current_slide_index ?? 0,
    Math.max(0, version.slides.length - 1),
  );
  const [previewIndex, setPreviewIndex] = useState(activeIndex);
  const [selectedAgent, setSelectedAgent] = useState("teacher");
  const [detailWidth, setDetailWidth] = useState(
    () =>
      Number(window.localStorage.getItem("platform.classroom-detail-width")) ||
      390,
  );
  const detailWidthRef = useRef(detailWidth);
  useEffect(() => setPreviewIndex(activeIndex), [activeIndex]);
  const slide = version.slides[previewIndex] as LessonSlide | undefined;
  const activeSlide = version.slides[activeIndex] as LessonSlide | undefined;
  const latestEvent = events[events.length - 1];
  const selectedEvent = useMemo(
    () =>
      [...events]
        .reverse()
        .find((event) => normalizeAgent(event.actor_id) === selectedAgent),
    [events, selectedAgent],
  );
  const selectedAgentEvents = useMemo(
    () =>
      events
        .filter((event) => normalizeAgent(event.actor_id) === selectedAgent)
        .sort((a, b) => a.sequence - b.sequence),
    [events, selectedAgent],
  );
  const selectedPersona = useMemo(
    () =>
      studentPersonas.find(
        (persona) => normalizeAgent(persona.student_id) === selectedAgent,
      ),
    [selectedAgent, studentPersonas],
  );
  const selectedCognitiveStates = useMemo(
    () =>
      studentCognitiveStates.filter(
        (item) => normalizeAgent(item.student_id) === selectedAgent,
      ),
    [selectedAgent, studentCognitiveStates],
  );
  const cognitiveSummary = useMemo(() => {
    if (!selectedCognitiveStates.length) return null;
    const count = selectedCognitiveStates.length;
    return {
      mastery:
        selectedCognitiveStates.reduce(
          (sum, item) => sum + item.current_mastery,
          0,
        ) / count,
      confidence:
        selectedCognitiveStates.reduce(
          (sum, item) => sum + item.current_confidence,
          0,
        ) / count,
      engagement:
        selectedCognitiveStates.reduce(
          (sum, item) => sum + item.engagement_runtime,
          0,
        ) / count,
      misconceptions: Array.from(
        new Set(selectedCognitiveStates.flatMap((item) => item.misconceptions)),
      ),
    };
  }, [selectedCognitiveStates]);
  const selectedWasSilent =
    selectedEvent?.event_type === "classroom.student.silence";
  const selectedObservations = observations.filter(
    (item) => item.slide_id === (activeSlide?.slide_id || slide?.slide_id),
  );
  const notes = (slide?.speaker_notes || [])
    .map((item) => item.content)
    .join("\n\n");
  const activeAgent = normalizeAgent(state?.active_agent_id);
  const selectedStatus =
    selectedAgent === activeAgent
      ? "正在执行课堂动作"
      : selectedAgent === "supervisor"
        ? "旁听记录，不参与课堂发言"
        : selectedAgentEvents.length
          ? "保持本轮身份，等待下一次课堂动作"
          : "尚未产生公开课堂表达";
  const selectedCurrentUnderstanding =
    selectedAgent === "teacher"
      ? notes || "当前页还没有可展示的 Speaker Note Block。"
      : selectedAgent === "supervisor"
        ? selectedObservations.length
          ? selectedObservations
              .map((item) => `${item.issue} 建议：${item.recommendation}`)
              .join("\n")
          : "当前页持续收集 PPT、讲解和互动证据，课后形成正式评价。"
        : cognitiveSummary
          ? `掌握度 ${Math.round(cognitiveSummary.mastery * 100)}%，信心 ${Math.round(cognitiveSummary.confidence * 100)}%。${cognitiveSummary.misconceptions.length ? ` 已暴露误区：${cognitiveSummary.misconceptions.join("、")}` : " 当前没有已记录误区。"}`
          : selectedEvent?.content || "当前页尚未形成该学生的公开理解证据。";
  const selectedIdentity =
    selectedAgent === "teacher"
      ? "课堂教师：执行 Lesson Blueprint、Speaker Notes 与课堂反馈。"
      : selectedAgent === "supervisor"
        ? "课后督导：只观察和引用证据，不在课堂中发言或改变流程。"
        : `${selectedPersona?.name || AGENT_NAMES[selectedAgent]} · ${selectedPersona?.level === "high" ? "拓展型" : selectedPersona?.level === "medium" ? "进阶型" : "基础型"} · 能力 ${selectedPersona ? Math.round(selectedPersona.ability * 100) : "--"}% · 参与倾向 ${selectedPersona ? Math.round(selectedPersona.engagement * 100) : "--"}%`;

  const resizeStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const startX = event.clientX;
    const initial = detailWidth;
    const move = (next: globalThis.PointerEvent) => {
      detailWidthRef.current = Math.min(
        520,
        Math.max(310, initial + startX - next.clientX),
      );
      setDetailWidth(detailWidthRef.current);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.localStorage.setItem(
        "platform.classroom-detail-width",
        String(detailWidthRef.current),
      );
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  const setStoredDetailWidth = (value: number) => {
    const next = Math.min(520, Math.max(310, value));
    detailWidthRef.current = next;
    setDetailWidth(next);
    window.localStorage.setItem(
      "platform.classroom-detail-width",
      String(next),
    );
  };

  return (
    <div className="classroom-rehearsal">
      <header className="classroom-rehearsal-summary">
        <div>
          <strong>第 1 轮 · 交互式课堂演练</strong>
          <span>第 {activeIndex + 1} / {version.slides.length} 页 · {latestEvent?.event_type.includes("summary") ? "本页小结" : latestEvent ? "课堂进行中" : "等待课堂事件"} · Supervisor Agent 仅旁听记录</span>
        </div>
        <dl>
          <div><dt>LESSON VERSION</dt><dd>PPT V{version.version_number}</dd></div>
          <div><dt>CURRENT SLIDE</dt><dd>{activeIndex + 1} / {version.slides.length}</dd></div>
          <div><dt>VIRTUAL TIME</dt><dd>{formatVirtualTime(state?.virtual_elapsed_seconds || 0)} / {formatVirtualTime((version.estimated_minutes || 45) * 60)}</dd></div>
        </dl>
        <div className="classroom-rehearsal-controls">
          <button type="button" disabled={!state || ["completed", "stopped"].includes(state.status)} onClick={() => void onControl(state?.status === "paused" ? "resume" : "pause")}>{state?.status === "paused" ? "继续" : "暂停"}</button>
          <button type="button" disabled={!state || ["completed", "stopped"].includes(state.status)} onClick={() => void onControl("stop")}>停止</button>
        </div>
      </header>
      <div
        className="classroom-rehearsal-stage"
        style={
          { "--classroom-detail-width": `${detailWidth}px` } as CSSProperties
        }
      >
        <div className="classroom-scene-column">
          <ClassroomScene3D
            slide={activeSlide}
            events={events}
            activeAgentId={state?.active_agent_id}
            eventType={latestEvent?.event_type}
            status={state?.status}
            selectedAgentId={selectedAgent}
            onSelectAgent={setSelectedAgent}
          />
          <section className="classroom-scene-evidence" aria-live="polite">
            <header><span>{AGENT_NAMES[selectedAgent]}</span><strong>{selectedStatus}</strong></header>
            <ul>
              <li>PPT：{activeSlide?.slide_id || "--"} · {activeSlide?.title || "等待当前页面"}</li>
              <li>本页目标依据：{activeSlide?.learning_objectives?.[0] || activeSlide?.purpose || "等待目标"}</li>
              <li>该 Agent 本页公开事件：{selectedAgentEvents.filter((event) => event.slide_id === activeSlide?.slide_id).length} 条</li>
              <li>本轮公开历史：{selectedAgentEvents.length} 条 · 当前活动：{activeAgent === selectedAgent ? "是" : "否"}</li>
            </ul>
            <div><b>当前页理解</b><p>{selectedCurrentUnderstanding}</p></div>
            <small>仅展示可观察工作状态与课堂证据，不展示隐藏思维链。</small>
          </section>
        </div>
        <div
          className="classroom-detail-resizer"
          role="separator"
          aria-label="调整课堂详情宽度"
          aria-orientation="vertical"
          aria-valuemin={310}
          aria-valuemax={520}
          aria-valuenow={detailWidth}
          tabIndex={0}
          onPointerDown={resizeStart}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft")
              setStoredDetailWidth(detailWidth + 16);
            if (event.key === "ArrowRight")
              setStoredDetailWidth(detailWidth - 16);
          }}
          onDoubleClick={() => setStoredDetailWidth(390)}
        />
        <aside className="classroom-teaching-detail">
          <header>
            <div>
              <span>
                {previewIndex === activeIndex ? "与黑板同步" : "课件浏览"}
              </span>
              <strong>
                Slide {previewIndex + 1} / {version.slides.length}
              </strong>
            </div>
            <nav>
              <button
                type="button"
                aria-label="上一页"
                disabled={previewIndex === 0}
                onClick={() =>
                  setPreviewIndex((index) => Math.max(0, index - 1))
                }
              >
                <ArrowLeft size={14} />
              </button>
              <button
                type="button"
                aria-label="下一页"
                disabled={previewIndex >= version.slides.length - 1}
                onClick={() =>
                  setPreviewIndex((index) =>
                    Math.min(version.slides.length - 1, index + 1),
                  )
                }
              >
                <ArrowRight size={14} />
              </button>
            </nav>
          </header>
          <LessonSlideCanvas
            slide={slide}
            index={previewIndex}
            total={version.slides.length}
          />
          <section className="classroom-live-delivery">
            <header><span>课堂实况</span><time>{formatVirtualTime(latestEvent?.virtual_timestamp || 0)}</time></header>
            <p>{latestEvent?.content || "课堂启动后，这里同步显示 Teacher 与 Student Agent 的真实课堂表达。"}</p>
          </section>
          <footer className="classroom-slide-progress">
            <button type="button" aria-label="上一页" disabled={previewIndex === 0} onClick={() => setPreviewIndex((index) => Math.max(0, index - 1))}><ArrowLeft size={14} /></button>
            <span>{previewIndex + 1} / {version.slides.length}</span>
            <i><b style={{ transform: `scaleX(${version.slides.length ? (activeIndex + 1) / version.slides.length : 0})` }} /></i>
            <button type="button" aria-label="下一页" disabled={previewIndex >= version.slides.length - 1} onClick={() => setPreviewIndex((index) => Math.min(version.slides.length - 1, index + 1))}><ArrowRight size={14} /></button>
          </footer>
          <section className="classroom-agent-detail">
            <nav className="agent-selector" aria-label="选择要查看的智能体">
              {AGENT_KEYS.map((key) => (
                <button type="button" key={key} className={selectedAgent === key ? "active" : ""} onClick={() => setSelectedAgent(key)} aria-pressed={selectedAgent === key}>
                  <span className={`agent-detail-avatar ${key.replace(":", "-")}`}>
                    {key === "teacher" ? "师" : key === "supervisor" ? "督" : key.endsWith("high") ? "拓" : key.endsWith("medium") ? "进" : "基"}
                  </span>
                  <span>{AGENT_NAMES[key]}</span>
                  {activeAgent === key && <i>当前</i>}
                </button>
              ))}
            </nav>
            <header>
              <span
                className={`agent-detail-avatar ${selectedAgent.replace(":", "-")}`}
              >
                {selectedAgent === "teacher"
                  ? "师"
                  : selectedAgent === "supervisor"
                    ? "督"
                    : selectedAgent.endsWith("high")
                      ? "拓"
                      : selectedAgent.endsWith("medium")
                        ? "进"
                        : "基"}
              </span>
              <div>
                <strong>{AGENT_NAMES[selectedAgent]}</strong>
                <small>
                   {selectedStatus}
                 </small>
               </div>
             </header>
            <div className="agent-understanding">
              <span>当前页理解</span>
              <p>{selectedCurrentUnderstanding}</p>
            </div>
            <div className="agent-identity">
              <span>稳定身份</span>
              <p>{selectedIdentity}</p>
            </div>
            {selectedAgent === "teacher" ? (
              <>
                <div className="agent-task">
                  <Bot size={14} />
                  <span>
                    <b>本页讲课稿</b>
                    {notes || "等待当前页讲稿"}
                  </span>
                </div>
                {selectedEvent && (
                  <div className="agent-public-event">
                    <b>最近课堂动作</b>
                    <p>{selectedEvent.content}</p>
                  </div>
                )}
              </>
            ) : selectedAgent === "supervisor" ? (
              <div className="agent-task">
                <ShieldCheck size={14} />
                <span>
                  <b>当前观察任务</b>
                  {selectedObservations.length
                    ? selectedObservations
                        .map((item) => item.recommendation)
                        .join("；")
                    : "持续记录 PPT、讲稿与师生互动证据；完成页面后形成可引用建议。"}
                </span>
              </div>
            ) : (
              <>
                <div className="agent-task">
                  <Eye size={14} />
                  <span>
                    <b>当前学习状态</b>
                    {selectedWasSilent
                      ? "本轮互动中未作答；这会作为课堂证据保留，不会伪造成学生表达。"
                      : selectedEvent
                        ? `${selectedEvent.event_type.includes("question") ? "对当前内容提出问题" : "已产生可观察课堂回应"}。`
                        : "正在听课，等待与自身层次匹配的互动机会。"}
                  </span>
                </div>
                <div className="student-public-state" aria-label="学生公开学习概况">
                  <div>
                    <span>学生层次</span>
                    <strong>
                      {selectedPersona?.level === "high"
                        ? "拓展型"
                        : selectedPersona?.level === "medium"
                          ? "进阶型"
                          : selectedPersona?.level === "low"
                            ? "基础型"
                            : selectedAgent.endsWith("high")
                              ? "拓展型"
                              : selectedAgent.endsWith("medium")
                                ? "进阶型"
                                : "基础型"}
                    </strong>
                  </div>
                  <div>
                    <span>参与倾向</span>
                    <strong>
                      {Math.round(
                        (cognitiveSummary?.engagement ??
                          selectedPersona?.engagement ??
                          0) * 100,
                      )}
                      %
                    </strong>
                  </div>
                  <div>
                    <span>当前掌握</span>
                    <strong>
                      {cognitiveSummary
                        ? `${Math.round(cognitiveSummary.mastery * 100)}%`
                        : "待观察"}
                    </strong>
                  </div>
                  <div>
                    <span>当前信心</span>
                    <strong>
                      {cognitiveSummary
                        ? `${Math.round(cognitiveSummary.confidence * 100)}%`
                        : "待观察"}
                    </strong>
                  </div>
                </div>
                {cognitiveSummary?.misconceptions.length ? (
                  <div className="student-misconceptions">
                    <b>已暴露误区</b>
                    <p>{cognitiveSummary.misconceptions.join("；")}</p>
                  </div>
                ) : null}
                {selectedEvent && (
                  <div className="agent-public-event">
                    <b>最近公开表达</b>
                    <p>
                      {selectedWasSilent
                        ? "本次未作答"
                        : selectedEvent.content || "暂无文本内容"}
                    </p>
                  </div>
                )}
              </>
            )}
            <section className="agent-history">
              <header><History size={13} /><strong>本轮公开历史</strong><span>{selectedAgentEvents.length} 条</span></header>
              {selectedAgentEvents.length ? (
                <ol>
                  {selectedAgentEvents.map((event) => (
                    <li key={event.event_id} className={event.slide_id === activeSlide?.slide_id ? "current" : ""}>
                      <div><b>EVT-{String(event.sequence).padStart(3, "0")}</b><time>{formatVirtualTime(event.virtual_timestamp || 0)} · {event.slide_id || "课堂"}</time></div>
                      <p>{event.content || "（该事件没有公开文本）"}</p>
                    </li>
                  ))}
                </ol>
              ) : <p className="agent-history-empty">该 Agent 尚无公开课堂发言或观察记录。</p>}
            </section>
          </section>
        </aside>
        <ClassroomGroupChat
          events={events}
          activeAgentId={state?.active_agent_id}
          status={state?.status}
          canIntervene={Boolean(
            state &&
              ["active", "paused"].includes(state.status) &&
              !["completed", "stopped", "failed"].includes(roundStatus || ""),
          )}
          sending={intervening}
          onIntervene={onIntervene}
        />
      </div>
    </div>
  );
}

function formatVirtualTime(seconds = 0) {
  const safe = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}
