import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Clock3,
  Pause,
  Play,
  Radio,
  RefreshCw,
  ShieldCheck,
  Square,
} from "lucide-react";
import {
  classroomApi,
  lessonVersionExportUrl,
  type ClassroomStartStatus,
} from "../lib/api";
import { useClassroomEvents } from "../hooks/useClassroomEvents";
import { RoleSettingsDialog } from './RoleSettingsDialog';
import './ClassroomWorkspace.css';
import { LessonPreparationProgress } from "./LessonPreparationProgress";
import { LessonReviewWorkspace } from "./LessonReviewWorkspace";
import { LessonSlideCanvas } from "./LessonSlideCanvas";
import type {
  ClassroomEvent,
  ClassroomState,
  LessonVersion,
  RevisionPatch,
  SimulationRound,
  StudentCognitiveState,
  StudentPersona,
  SupervisorObservation,
  SupervisorProfile,
  SupervisorReport,
  TeacherDirective,
  WorkflowRun,
} from "../types/workflow";

type View =
  "preparation" | "ppt" | "rehearsal" | "review" | "versions" | "debug";
const fmtTime = (seconds = 0) =>
  `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.max(0, Math.floor(seconds) % 60)).padStart(2, "0")}`;
const pendingPhases = new Set([
  "queued",
  "blueprint_generating",
  "classroom_starting",
]);
const dimensionLabels: Record<string, string> = {
  content_accuracy: "内容准确性",
  objective_achievement: "目标达成度",
  explanation_clarity: "讲解清晰度",
  interaction_quality: "课堂互动质量",
  questioning_quality: "提问质量",
  feedback_quality: "反馈质量",
  misconception_handling: "误区处理",
  pacing: "课堂节奏",
  ppt_speech_alignment: "PPT 与讲稿一致性",
};
const severityLabels: Record<string, string> = {
  info: "有效证据",
  minor: "一般问题",
  major: "重要问题",
  critical: "严重问题",
};
const observationTypeLabels: Record<string, string> = {
  content_accuracy: "PPT 内容",
  objective_achievement: "目标达成",
  explanation_clarity: "教师讲解",
  ppt_speech_alignment: "PPT · 讲稿一致性",
  interaction_quality: "师生互动",
  questioning_quality: "提问质量",
  feedback_quality: "教师反馈",
  misconception_handling: "误区处理",
  pacing: "课堂节奏",
};
const analysisLabels: Record<string, string> = {
  ppt_alignment: "PPT 对齐",
  teaching_coverage: "讲解覆盖",
  student_response_analysis: "学生反应",
  feedback_analysis: "反馈分析",
  misconception_analysis: "误区分析",
  objective_evidence: "目标证据",
};
const ClassroomRehearsalStage = lazy(() =>
  import("./ClassroomRehearsalStage").then((module) => ({
    default: module.ClassroomRehearsalStage,
  })),
);

export function ClassroomWorkspace({ run }: { run: WorkflowRun | null }) {
  const runId = run?.id ?? null;
  const [rounds, setRounds] = useState<SimulationRound[]>([]);
  const [versions, setVersions] = useState<LessonVersion[]>([]);
  const [roundId, setRoundId] = useState<string | null>(null);
  const [state, setState] = useState<ClassroomState | null>(null);
  const [view, setView] = useState<View>("preparation");
  const [report, setReport] = useState<SupervisorReport | null>(null);
  const [observations, setObservations] = useState<SupervisorObservation[]>([]);
  const [studentPersonas, setStudentPersonas] = useState<StudentPersona[]>([]);
  const [studentCognitiveStates, setStudentCognitiveStates] = useState<
    StudentCognitiveState[]
  >([]);
  const [patches, setPatches] = useState<RevisionPatch[]>([]);
  const [reviewPlan, setReviewPlan] = useState<Record<string, string>>({});
  const [reviewFocusSlideId, setReviewFocusSlideId] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(runId));
  const [loadedRunId, setLoadedRunId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  // 「PPT 生成后暂停」下 approve(auto_start=false) 只把版本置 ready 并停在审阅门；
  // 该标记驱动显式的「开始课堂演练」按钮（见 startClassroom）。
  const [awaitingStart, setAwaitingStart] = useState(false);
  const [startingClassroom, setStartingClassroom] = useState(false);
  const [intervening, setIntervening] = useState(false);
  const [startStatus, setStartStatus] = useState<ClassroomStartStatus | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [reviewNotice, setReviewNotice] = useState<{ roundId: string; roundNumber: number } | null>(null);
  // 纠正类介入改了课件后的提示(可跳到版本对比查看/回滚)
  const [directiveNotice, setDirectiveNotice] = useState<string | null>(null);
  const [supervisorProfile, setSupervisorProfile] = useState<SupervisorProfile | null>(null);
  const autoPrepareRunRef = useRef<string | null>(null);
  const selectedRound =
    rounds.find((item) => item.id === roundId) ||
    rounds[rounds.length - 1] ||
    null;
  const latestVersion = versions[versions.length - 1] || null;
  const selectedVersion =
    versions.find((item) => item.id === selectedRound?.lesson_version_id) ||
    latestVersion;
  // 复盘/审阅要"当前这一轮的课件"，不是最新版本：本轮结束后 revision 会生成 V(n+1)，
  // 用最新版本会让本轮复盘拿到尚未开课的下一版（实测导致复盘 tab 直接消失）。
  const workingVersion = selectedVersion || latestVersion;
  const workingIsDraft = workingVersion?.status === "draft";
  const terminalRound = ["completed", "stopped", "failed"].includes(
    selectedRound?.status || "",
  );
  const { events, connection, announcedRoundId } = useClassroomEvents(
    runId,
    selectedRound?.id || null,
    !terminalRound,
  );
  const latestEvent = events[events.length - 1];
  const eventById = useMemo(
    () => new Map(events.map((event) => [event.event_id, event])),
    [events],
  );

  /** 撤销一条生效中的教师指令；复盘视图负责本地状态更新。 */
  const cancelDirective = useCallback(
    async (directiveId: string) => {
      if (!runId) return;
      await classroomApi.cancelDirective(runId, directiveId);
    },
    [runId],
  );

  const load = useCallback(
    async (preferredView?: View) => {
      if (!runId) {
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const [roundResponse, versionResponse, patchResponse] =
          await Promise.all([
            classroomApi.listRounds(runId),
            classroomApi.listLessonVersions(runId),
            classroomApi.listPatches(runId),
          ]);
        const nextRounds = roundResponse.items || [];
        const nextVersions = versionResponse.items || [];
        setRounds(nextRounds);
        setVersions(nextVersions);
        setPatches(patchResponse.items || []);
        const saved = window.localStorage.getItem(
          `platform.classroom.${runId}.round_id`,
        );
        setRoundId(
          saved && nextRounds.some((item) => item.id === saved)
            ? saved
            : nextRounds[nextRounds.length - 1]?.id || null,
        );
        setLoadedRunId(runId);
        // 生成失败时必须停在「生成过程」: 失败原因和重试入口都在那里。
        // 否则会被下方分支带到 PPT 审阅, 教师既看不到为什么失败, 也找不到重试。
        const status = await classroomApi.getStartStatus(runId);
        setStartStatus(status);
        if (status.phase === "failed") setView("preparation");
        else if (preferredView) setView(preferredView);
        else if (nextRounds.length) setView("rehearsal");
        else if (nextVersions[nextVersions.length - 1]?.status === "draft")
          setView("ppt");
        else setView("preparation");
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "课堂数据加载失败");
      } finally {
        setLoading(false);
      }
    },
    [runId],
  );

  useEffect(() => {
    setLoadedRunId(null);
    setStartStatus(null);
    autoPrepareRunRef.current = null;
    if (!runId) {
      setLoading(false);
      setRounds([]);
      setVersions([]);
      setRoundId(null);
      setState(null);
      setStudentPersonas([]);
      setStudentCognitiveStates([]);
      setView("preparation");
      return;
    }
    window.localStorage.setItem("platform.classroom.run_id", runId);
    void load();
  }, [runId, load]);

  useEffect(() => {
    if (!runId) return;
    let active = true;
    let timer: number | undefined;
    let ticks = 0;
    const poll = async () => {
      try {
        const response = await classroomApi.getStartStatus(runId);
        if (!active) return;
        const next: ClassroomStartStatus =
          response.phase === "idle" && run?.status === "failed"
            ? {
                ...response,
                phase: "failed" as const,
                message: run.error
                  ? `PPT 生成失败：${run.error}`
                  : "PPT 生成失败，可重新生成",
              }
            : response;
        setStartStatus(next);
        setStarting(pendingPhases.has(next.phase));
        if (next.phase === "failed") setError(next.message);
        if (next.phase === "awaiting_review" && !versions.length)
          await load("ppt");
        if (next.phase === "classroom_running" && !rounds.length)
          await load("rehearsal");
        // classroom_starting 期间回合行可能先于 phase 翻转到 classroom_running 落库，
        // 若此处因 rounds.length>0 停轮询，phase 会永久停在 classroom_starting。
        // 故只要仍是 pending phase 就继续轮询（上限 60 次 ≈ 54s 防挂死）。
        if (pendingPhases.has(next.phase) && ticks < 60) {
          ticks += 1;
          timer = window.setTimeout(poll, 900);
        } else if (
          (next.phase === "awaiting_review" && !versions.length) ||
          (next.phase === "classroom_running" && !rounds.length)
        )
          timer = window.setTimeout(poll, 900);
      } catch {
        if (active) timer = window.setTimeout(poll, 1800);
      }
    };
    void poll();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [
    runId,
    rounds.length,
    versions.length,
    load,
    startStatus?.phase,
    run?.status,
    run?.error,
  ]);

  useEffect(() => {
    if (
      !runId ||
      loadedRunId !== runId ||
      autoPrepareRunRef.current === runId ||
      rounds.length ||
      versions.length ||
      !run
    )
      return;
    if (
      run.teaching_data?.workflow_version !== "classroom_v2" ||
      startStatus?.phase !== "idle" ||
      run.status === "failed"
    )
      return;
    autoPrepareRunRef.current = runId;
    setStarting(true);
    setView("preparation");
    classroomApi
      .prepare(runId)
      .then(setStartStatus)
      .catch((reason) => {
        setStarting(false);
        setError(reason instanceof Error ? reason.message : "PPT 准备启动失败");
      });
  }, [
    runId,
    loadedRunId,
    run,
    rounds.length,
    versions.length,
    startStatus?.phase,
  ]);

  useEffect(() => {
    if (runId && roundId)
      window.localStorage.setItem(
        `platform.classroom.${runId}.round_id`,
        roundId,
      );
  }, [runId, roundId]);

  useEffect(() => {
    if (!runId) {
      setSupervisorProfile(null);
      return;
    }
    let active = true;
    classroomApi.getSupervisorProfile(runId)
      .then((profile) => { if (active) setSupervisorProfile(profile); })
      .catch(() => { if (active) setSupervisorProfile(null); });
    return () => { active = false; };
  }, [runId]);

  useEffect(() => {
    if (!selectedRound || !runId) return;
    const completed = selectedRound.status === "completed" || events.some((event) =>
      event.round_id === selectedRound.id && ["classroom.evaluation.completed", "classroom.revision.completed"].includes(event.event_type),
    );
    if (completed && view !== "review") {
      setReviewNotice({ roundId: selectedRound.id, roundNumber: selectedRound.round_number });
    }
  }, [runId, selectedRound?.id, selectedRound?.status, events, view]);
  useEffect(() => {
    if (!announcedRoundId || announcedRoundId === roundId) return;
    void load("rehearsal");
  }, [announcedRoundId, roundId, load]);
  useEffect(() => {
    if (
      !runId ||
      !latestEvent ||
      ![
        "classroom.evaluation.completed",
        "classroom.revision.completed",
      ].includes(latestEvent.event_type)
    )
      return;
    Promise.all([
      classroomApi.listRounds(runId),
      classroomApi.listLessonVersions(runId),
      classroomApi.listPatches(runId),
    ])
      .then(([roundResponse, versionResponse, patchResponse]) => {
        setRounds(roundResponse.items || []);
        setVersions(versionResponse.items || []);
        setPatches(patchResponse.items || []);
      })
      .catch(() => undefined);
  }, [runId, latestEvent?.event_id]);
  useEffect(() => {
    if (!runId || !selectedRound) {
      setState(null);
      return;
    }
    let active = true;
    classroomApi
      .getSnapshot(runId, selectedRound.id)
      .then((snapshot) => {
        if (!active) return;
        setState(snapshot.state);
        setStudentPersonas(snapshot.student_personas || []);
        setStudentCognitiveStates(snapshot.student_cognitive_states || []);
      })
      .catch(() => {
        if (!active) return;
        setState(null);
        setStudentPersonas([]);
        setStudentCognitiveStates([]);
      });
    return () => {
      active = false;
    };
  }, [runId, selectedRound?.id, events.length]);
  useEffect(() => {
    if (!runId || !selectedRound) {
      setReport(null);
      setObservations([]);
      return;
    }
    const evaluationReady =
      selectedRound.status === "completed" ||
      events.some(
        (event) => event.event_type === "classroom.evaluation.completed",
      );
    const observationsReady =
      evaluationReady ||
      view === "review" ||
      events.some((event) => event.event_type === "classroom.slide.completed");
    if (evaluationReady)
      classroomApi
        .getReport(runId, selectedRound.id)
        .then(setReport)
        .catch(() => setReport(null));
    else setReport(null);
    if (observationsReady)
      classroomApi
        .listObservations(runId, selectedRound.id)
        .then((response) => setObservations(response.items))
        .catch(() => setObservations([]));
    else setObservations([]);
  }, [runId, selectedRound?.id, selectedRound?.status, view, events]);

  const control = async (action: "pause" | "resume" | "stop") => {
    if (!runId || !selectedRound) return;
    try {
      setState(await classroomApi[action](runId, selectedRound.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "课堂控制失败");
    }
  };
  /** 显式开启课堂演练：审批时勾了「教学设计后暂停」后的唯一入口。 */
  const startClassroom = async () => {
    if (!runId || startingClassroom) return;
    setStartingClassroom(true);
    setError(null);
    try {
      await classroomApi.start(runId, Number(run?.teaching_data?.max_iterations || 1));
      setAwaitingStart(false);
      await load("rehearsal");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "课堂演练启动失败");
    } finally {
      setStartingClassroom(false);
    }
  };
  const intervene = async (
    content: string,
    options?: { intent?: 'question' | 'correct' | 'require'; scope?: 'slide' | 'round' | 'lesson' },
  ) => {
    if (!runId || !selectedRound) return;
    setIntervening(true);
    setError(null);
    try {
      const result = await classroomApi.intervene(runId, selectedRound.id, content, options);
      setState(result.state);
      if (result.patches?.length) {
        setDirectiveNotice(`已按你的纠正修改课件（${result.patches.length} 处），可在「版本对比」查看或回滚`);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "课堂介入失败");
      throw reason;
    } finally {
      setIntervening(false);
    }
  };
  const retryPreparation = async (options?: { retry?: boolean; maxSlides?: number }) => {
    if (!runId) return;
    setError(null);
    setStarting(true);
    setView("preparation");
    try {
      const next = await classroomApi.prepare(runId, options);
      setStartStatus(next);
      setVersions([]);
      autoPrepareRunRef.current = runId;
    } catch (reason) {
      setStarting(false);
      setError(
        reason instanceof Error ? reason.message : "PPT 准备重新启动失败",
      );
    }
  };

  if (!run)
    return (
      <div className="classroom-empty">
        <Bot size={24} />
        <strong>创建或选择一个教学会话</strong>
        <span>启动教学设计后，资料分析与 PPT 生成会立即显示在这里。</span>
      </div>
    );
  if (loading && loadedRunId !== runId)
    return (
      <div className="classroom-empty">
        <RefreshCw className="spin" size={20} />
        正在恢复课程设计状态
      </div>
    );

  const maxRounds = Number(run.teaching_data?.max_iterations || 1);
  const phaseIndex = selectedRound
    ? 3
    : workingIsDraft
      ? 2
      : workingVersion
        ? 2
        : startStatus?.phase === "blueprint_generating"
          ? 1
          : 0;
  const tabs: Array<{ key: View; label: string; disabled?: boolean }> = [
    { key: "preparation", label: "生成过程" },
    { key: "ppt", label: "PPT 审阅", disabled: !workingVersion },
    { key: "rehearsal", label: "课堂演练", disabled: !selectedRound },
    { key: "review", label: "本轮复盘", disabled: !selectedRound },
    { key: "versions", label: "版本对比", disabled: !versions.length },
    { key: "debug", label: "Agent 调试", disabled: !selectedRound },
  ];
  // 版本已 ready 且尚无轮次 = 停在「PPT 已确认、等教师开始课堂」这一步（勾选暂停后）。
  const canStartClassroom =
    awaitingStart ||
    (Boolean(latestVersion) &&
      latestVersion!.status !== "draft" &&
      !selectedRound &&
      startStatus?.phase === "blueprint_ready");
  return (
    <section
      className="classroom-workspace"
      aria-label="课程设计与课堂演练工作台"
    >
      {runId && <RoleSettingsDialog runId={runId} />}
      {canStartClassroom && (
        <div className="classroom-start-gate" role="region" aria-label="开始课堂演练">
          <div>
            <strong>PPT 已确认并冻结，等待你开始课堂演练</strong>
            <small>
              你选择了「PPT 生成后暂停」。确认无误后点击右侧按钮，多智能体课堂将按这份
              V{latestVersion?.version_number ?? 1} 逐页讲稿开始演练。
            </small>
          </div>
          <button
            type="button"
            className="primary-button"
            onClick={() => void startClassroom()}
            disabled={startingClassroom}
          >
            {startingClassroom ? (
              <RefreshCw className="spin" size={15} />
            ) : (
              <Play size={15} fill="currentColor" />
            )}
            {startingClassroom ? "正在启动课堂…" : "开始课堂演练"}
          </button>
        </div>
      )}
      {view !== "rehearsal" && <div className="classroom-flowbar">
        <ol>
          {[
            "资料分析",
            "PPT V1",
            "用户审阅",
            "课堂演练",
            "督导复盘",
            "版本修订",
            "定稿",
          ].map((label, index) => (
            <li
              className={
                index < phaseIndex
                  ? "done"
                  : index === phaseIndex
                    ? "active"
                    : ""
              }
              key={label}
            >
              <span>{index < phaseIndex ? "✓" : index + 1}</span>
              <b>{label}</b>
            </li>
          ))}
        </ol>
        <div>
          <span className={`classroom-connection ${connection}`}>
            <Radio size={12} />
            {selectedRound
              ? connection === "live"
                ? "实时同步"
                : "历史恢复"
              : starting
                ? "DSH 生成中"
                : workingIsDraft
                  ? "等待审阅"
                  : "准备中"}
          </span>
          {selectedVersion && (
            <span className="classroom-chip">
              V{selectedVersion.version_number} ·{" "}
              {selectedVersion.slides.length} 页
            </span>
          )}
        </div>
      </div>}
      {error && (
        <div className="classroom-inline-error" role="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>
            关闭
          </button>
        </div>
      )}
      {directiveNotice && (
        <div className="classroom-review-notice" role="status">
          <div>
            <strong>课件已按你的纠正更新</strong>
            <span>{directiveNotice}</span>
          </div>
          <button type="button" onClick={() => { setDirectiveNotice(null); setView("versions"); }}>
            查看版本对比
          </button>
        </div>
      )}
      {reviewNotice && reviewNotice.roundId === selectedRound?.id && view !== "review" && (
        <div className="classroom-review-notice" role="status">
          <div>
            <strong>第 {reviewNotice.roundNumber} 轮课堂演练已完成</strong>
            <span>督导报告已经生成。请先查看本轮复盘，自主确认逐页优化方案，再决定是否进入下一轮。</span>
          </div>
          <button type="button" onClick={() => { setReviewNotice(null); setView("review"); }}>
            查看本轮复盘
          </button>
        </div>
      )}
      {selectedRound && view !== "rehearsal" && (
        <div className="classroom-toolbar">
          <div className="round-picker">
            <label htmlFor="classroom-round">课堂轮次</label>
            <select
              id="classroom-round"
              value={selectedRound.id}
              onChange={(event) => setRoundId(event.target.value)}
            >
              {rounds.map((item) => (
                <option key={item.id} value={item.id}>
                  第 {item.round_number} / {maxRounds} 轮 · {item.status}
                </option>
              ))}
            </select>
          </div>
          <div className="classroom-clock">
            <Clock3 size={15} />
            <strong>
              {fmtTime(
                state?.virtual_elapsed_seconds ??
                  selectedRound.virtual_elapsed_seconds,
              )}
            </strong>
            <small>
              / {fmtTime((selectedVersion?.estimated_minutes || 45) * 60)}
            </small>
          </div>
          <div className="classroom-current-action">
            <span>
              {latestEvent
                ? latestEvent.event_type.replace("classroom.", "")
                : "等待课堂事件"}
            </span>
            <strong>
              {latestEvent?.content || "课堂将在完整 Agent Action 持久化后更新"}
            </strong>
          </div>
          <div className="classroom-controls">
            <button
              className="secondary-button"
              onClick={() =>
                void control(state?.status === "paused" ? "resume" : "pause")
              }
              disabled={
                !state || ["completed", "stopped"].includes(state.status)
              }
            >
              {state?.status === "paused" ? (
                <Play size={14} />
              ) : (
                <Pause size={14} />
              )}
              {state?.status === "paused" ? "继续" : "暂停"}
            </button>
            <button
              className="secondary-button danger"
              onClick={() => void control("stop")}
              disabled={
                !state || ["completed", "stopped"].includes(state.status)
              }
            >
              <Square size={13} />
              停止
            </button>
          </div>
        </div>
      )}
      <nav className="classroom-tabs" role="tablist" aria-label="课程设计视图">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={view === tab.key}
            aria-disabled={tab.disabled}
            disabled={tab.disabled}
            className={view === tab.key ? "active" : ""}
            onClick={() => setView(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      {view === "preparation" && (
        <>
          {runId && (
            <SupervisorProfileEditor
              runId={runId}
              profile={supervisorProfile}
              onSaved={setSupervisorProfile}
              onError={setError}
            />
          )}
          <LessonPreparationProgress
            run={run}
            status={startStatus}
            onRetry={retryPreparation}
          />
        </>
      )}
      {view === "ppt" && workingVersion && runId && (
          <LessonReviewWorkspace
            runId={runId}
            version={workingVersion!}
            maxRounds={maxRounds}
            reviewPlan={reviewPlan}
            focusSlideId={reviewFocusSlideId}
          onVersionChange={(updated) =>
            setVersions((items) =>
              items.map((item) => (item.id === updated.id ? updated : item)),
            )
          }
          pauseAfterDesign={Boolean(
            (run?.teaching_data?.interventions as { after_design?: boolean } | undefined)
              ?.after_design,
          )}
          onApproved={async (info) => {
            // 「教学设计后暂停」勾选时 approve 只把版本置为 ready 并返回 awaiting_start；
            // 此时必须给教师一个显式的「开始课堂演练」入口（classroomApi.start），
            // 否则版本已 ready(canEdit=false)、审阅控件全部禁用，整条流程永久卡死。
            if (info?.awaitingStart) {
              setAwaitingStart(true);
              await load("ppt");
              return;
            }
            setAwaitingStart(false);
            await load("rehearsal");
          }}
          onError={setError}
        />
      )}
      {view === "rehearsal" && selectedVersion && selectedRound && (
        <Suspense
          fallback={
            <div className="classroom-empty">
              <RefreshCw className="spin" size={20} />
              正在载入交互式 3D 教室
            </div>
          }
        >
          <ClassroomRehearsalStage
            version={selectedVersion}
            state={state}
            events={events}
            observations={observations}
            studentPersonas={studentPersonas}
            studentCognitiveStates={studentCognitiveStates}
            intervening={intervening}
            roundStatus={selectedRound?.status}
            onIntervene={intervene}
            onControl={control}
          />
        </Suspense>
      )}
      {view === "review" && (
        <ReviewView
          report={report}
          version={selectedVersion}
          observations={observations}
          events={eventById}
          runId={runId || ""}
          roundId={selectedRound?.id || null}
          onCancelDirective={cancelDirective}
          supervisorProfile={supervisorProfile}
          onSupervisorProfileChange={setSupervisorProfile}
          onError={setError}
          onBackToPpt={(plan, focusSlideId) => {
            if (plan) setReviewPlan(plan);
            setReviewFocusSlideId(focusSlideId || null);
            setView("ppt");
          }}
          onVersions={() => setView("versions")}
        />
      )}
      {view === "versions" && runId && (
        <VersionView runId={runId} versions={versions} patches={patches} />
      )}
      {view === "debug" && runId && (
        <DebugView
          runId={runId}
          round={selectedRound}
          state={state}
          events={events}
        />
      )}
    </section>
  );
}

const genericObservationPhrases = new Set([
  "slide evidence was recorded.",
  "slide execution events were recorded.",
  "review the cited slide events.",
  "review the cited interaction evidence.",
  "已记录课堂证据。",
  "建议查看相关课堂事件。",
]);

function isGenericObservation(observation: SupervisorObservation) {
  const issue = observation.issue.trim().toLowerCase();
  const recommendation = observation.recommendation.trim().toLowerCase();
  return (
    !recommendation ||
    genericObservationPhrases.has(issue) ||
    genericObservationPhrases.has(recommendation) ||
    (observation.category === "other" && issue.length < 36)
  );
}

function SupervisorProfileEditor({ runId }: { runId: string; profile: SupervisorProfile | null; onSaved: (profile: SupervisorProfile) => void; onError: (message: string | null) => void }) {
  return <RoleSettingsDialog key={runId} runId={runId} />;
}

/** 随内容自动增高的多行输入。

    计划正文常有 80+ 字，rows=2 时只显示 55px、内容 99px —— 后两行被藏在滚动条里，
    教师以为建议只有一句话。改为按 scrollHeight 自适应，并封顶避免一屏占满。
 */
function AutoGrowTextarea({
  value,
  onChange,
  placeholder,
  minRows = 2,
  maxHeight = 260,
  disabled,
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  minRows?: number;
  maxHeight?: number;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [value, maxHeight]);
  return (
    <textarea
      ref={ref}
      value={value}
      rows={minRows}
      disabled={disabled}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

function formatEventEvidence(event: ClassroomEvent | undefined, fallbackId: string) {
  if (!event) return fallbackId;
  const eventType = event.event_type.replace(/^classroom\./, "").replace(/\./g, " · ");
  const virtualSeconds = Math.max(0, Math.floor(event.virtual_timestamp || 0));
  const virtualTime = `${String(Math.floor(virtualSeconds / 60)).padStart(2, "0")}:${String(virtualSeconds % 60).padStart(2, "0")}`;
  return `EVT-${String(event.sequence).padStart(3, "0")} · ${event.actor_role} · ${eventType} · ${virtualTime}`;
}

function ReviewView({
  runId,
  roundId,
  report,
  version,
  observations,
  events,
  supervisorProfile,
  onSupervisorProfileChange,
  onError,
  onBackToPpt,
  onVersions,
  onCancelDirective,
}: {
  runId: string;
  roundId: string | null;
  report: SupervisorReport | null;
  version: LessonVersion | null;
  observations: SupervisorObservation[];
  events: Map<string, ClassroomEvent>;
  supervisorProfile: SupervisorProfile | null;
  onSupervisorProfileChange: (profile: SupervisorProfile) => void;
  onError: (message: string | null) => void;
  onBackToPpt: (plan?: Record<string, string>, focusSlideId?: string) => void;
  onVersions: () => void;
  onCancelDirective?: (directiveId: string) => Promise<void> | void;
}) {
  const cancelDirective = async (directiveId: string) => {
    if (!onCancelDirective) return;
    const previous = directives;
    // 乐观更新：撤销是幂等的用户意图，先反馈再回滚比让按钮"什么都不发生"更好。
    setDirectives((items) =>
      items.map((item) =>
        item.directive_id === directiveId
          ? { ...item, status: "cancelled" as TeacherDirective["status"] }
          : item,
      ),
    );
    try {
      await onCancelDirective(directiveId);
    } catch (reason) {
      setDirectives(previous);
      onError(reason instanceof Error ? reason.message : "撤销教师指令失败");
    }
  };
  const [accepted, setAccepted] = useState<Record<string, boolean>>(() => {
    // 逐页修改计划草稿在切到「PPT 审阅」再切回时会被卸载，这里按 run+轮次 持久化，
    // 避免教师刚确认的修改计划在切换视图或刷新后无声丢失。
    if (typeof window === "undefined" || !runId) return {};
    try {
      const raw = window.sessionStorage.getItem(
        `platform.classroom.${runId}.review-plan`,
      );
      const parsed = raw ? JSON.parse(raw) : null;
      return parsed && parsed.roundId === roundId && parsed.accepted
        ? (parsed.accepted as Record<string, boolean>)
        : {};
    } catch {
      return {};
    }
  });
  const [planDraft, setPlanDraft] = useState<Record<string, string>>(() => {
    if (typeof window === "undefined" || !runId) return {};
    try {
      const raw = window.sessionStorage.getItem(
        `platform.classroom.${runId}.review-plan`,
      );
      const parsed = raw ? JSON.parse(raw) : null;
      return parsed && parsed.roundId === roundId && parsed.notes
        ? (parsed.notes as Record<string, string>)
        : {};
    } catch {
      return {};
    }
  });
  useEffect(() => {
    if (typeof window === "undefined" || !runId) return;
    try {
      window.sessionStorage.setItem(
        `platform.classroom.${runId}.review-plan`,
        JSON.stringify({ roundId, accepted, notes: planDraft }),
      );
    } catch {
      /* 存储不可用时不阻塞复盘页 */
    }
  }, [runId, roundId, accepted, planDraft]);
  // E3-7: 本轮教师指令 + 落实情况(说了什么/是否被遵守/改了哪些地方)
  const [directives, setDirectives] = useState<TeacherDirective[]>([]);
  const [directivePatches, setDirectivePatches] = useState<RevisionPatch[]>([]);
  const [directivesOpen, setDirectivesOpen] = useState(true);
  useEffect(() => {
    let active = true;
    // 这是「本轮复盘」视图：必须按当前轮过滤，否则会混入其它轮的指令和补丁，
    // 标题写着"本轮"却统计了整场课堂。
    void Promise.all([
      classroomApi.listDirectives(runId, roundId || undefined),
      classroomApi.listPatches(runId, roundId || undefined),
    ])
      .then(([directiveResponse, patchResponse]) => {
        if (!active) return;
        setDirectives(directiveResponse.items || []);
        setDirectivePatches(
          (patchResponse.items || []).filter(
            (item) => (item.source_intervention_ids || []).length > 0,
          ),
        );
      })
      .catch(() => {
        if (active) setDirectives([]);
      });
    return () => {
      active = false;
    };
  }, [runId, roundId, report?.id]);

  const slideOrder = useMemo(
    () => new Map((version?.slides || []).map((slide, index) => [slide.slide_id, index])),
    [version],
  );
  const sortedObservations = useMemo(
    () => observations.slice().sort((left, right) => {
      const leftOrder = slideOrder.get(left.slide_id) ?? Number.MAX_SAFE_INTEGER;
      const rightOrder = slideOrder.get(right.slide_id) ?? Number.MAX_SAFE_INTEGER;
      return leftOrder - rightOrder || (left.created_at || "").localeCompare(right.created_at || "") || left.observation_id.localeCompare(right.observation_id);
    }),
    [observations, slideOrder],
  );
  const planItems = sortedObservations.map((observation) => {
    const unusable = isGenericObservation(observation);
    const fallbackPlan = unusable ? "" : observation.recommendation.trim();
    return {
    ...observation,
    unusable,
    plan:
      planDraft[observation.observation_id] ?? fallbackPlan,
    };
  });
  const acceptedCount = planItems.filter(
    (item) => accepted[item.observation_id],
  ).length;
  const acceptedPlans = planItems.reduce<Record<string, string>>((result, item) => {
    if (!accepted[item.observation_id] || !item.plan.trim()) return result;
    result[item.slide_id] = [result[item.slide_id], item.plan.trim()].filter(Boolean).join("\n");
    return result;
  }, {});
  const usableCount = planItems.filter((item) => !item.unusable).length;
  const qualityWarning = observations.length > 0 && usableCount === 0;
  return (
    <>
      <SupervisorProfileEditor
        runId={runId}
        profile={supervisorProfile}
        onSaved={onSupervisorProfileChange}
        onError={onError}
      />
      <div className="classroom-review">
      <div className="review-section-heading" style={{gridColumn: "1/-1"}}>
        <div>
          <h3>
            <ShieldCheck size={16} />
            本轮复盘
          </h3>
          <p className="review-explanation">
            左列是督导综合评价，中列是逐页修改计划，右列是逐页证据。确认计划后回到
            PPT 审阅提交修改，平台不会自动覆盖整套课件。
          </p>
        </div>
      </div>
      <div className="review-score">
        <span>有证据的综合评价</span>
        <strong>{report?.overall_score ?? "--"}</strong>
        <small>{report ? "/ 100" : "本轮结束后生成"}</small>
      </div>
      <div className="review-content review-content-structured">
        <section className="review-panel">
          <h3>
            <ShieldCheck size={16} />
            Supervisor Report
          </h3>
          {report ? (
            <>
              {qualityWarning && (
                <div className="review-quality-warning" role="status">
                  <AlertCircle size={15} />
                  <span>本轮督导返回了事件记录，但没有形成可执行的逐页判断。以下证据仅供核对，不能直接生成修订计划。</span>
                </div>
              )}
              <div className="dimension-grid">
                {Object.entries(report.dimension_scores || {}).map(
                  ([key, value]) => (
                    <div key={key}>
                      <span>{dimensionLabels[key] || key}</span>
                      <strong>{value}</strong>
                    </div>
                  ),
                )}
              </div>
              <h4>优势</h4>
              <ul>
                {report.strengths.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <h4>关键问题</h4>
              {report.critical_issues.length ? (
                <ul>
                  {report.critical_issues.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted">本轮没有达到“重要”级别的问题。</p>
              )}
            </>
          ) : (
            <p className="muted">
              督导只在页面或本轮完成后，根据已持久化事件形成评价，不在课堂中发言。
            </p>
          )}
        </section>
        <section className="review-panel review-plan-panel">
          <header className="review-section-heading">
            <div>
              <span className="eyebrow">TEACHER AGENT · POST-CLASS</span>
              <h3>逐页修改计划</h3>
            </div>
            <span>{acceptedCount} / {planItems.length} 条已确认</span>
          </header>
          <p className="review-explanation">
            Teacher Agent 依据督导观察、证据事件和原始 Slide，先提出局部修改计划。确认后回到 PPT 审阅，修改仍需由你最终提交，不会自动覆盖整套课件。
          </p>
          {planItems.length ? planItems.map((item) => (
            <article className="revision-plan" key={item.observation_id}>
              <header>
                <strong>{item.slide_id}</strong>
                <span>{observationTypeLabels[item.category] || item.category} · {severityLabels[item.severity] || item.severity} · {item.observation_id}</span>
              </header>
              {item.unusable && <div className="revision-plan-status"><AlertCircle size={13} />督导观察过于泛化，先重新运行督导评价后再制定修改。</div>}
              <p><b>督导发现：</b>{item.issue}</p>
              <label>
                <span>Teacher Agent 建议动作</span>
                <AutoGrowTextarea
                  value={item.plan}
                  onChange={(next) => setPlanDraft((current) => ({ ...current, [item.observation_id]: next }))}
                  minRows={2}
                  disabled={item.unusable}
                  placeholder={item.unusable ? "暂无可验证的页面修改建议" : "请确认或补充本页的具体修改动作"}
                />
              </label>
              <small>课堂证据：{item.event_ids.map((id) => formatEventEvidence(events.get(id), id)).join("；") || "未关联事件"}</small>
              <button type="button" disabled={item.unusable || !item.plan.trim()} className={accepted[item.observation_id] ? "accepted" : ""} onClick={() => setAccepted((current) => ({ ...current, [item.observation_id]: !current[item.observation_id] }))}>
                {accepted[item.observation_id] ? "已确认此页修改计划" : "确认此页计划"}
              </button>
            </article>
          )) : <p className="muted">本轮尚未生成逐页观察，课堂结束后这里会出现带证据的修改计划。</p>}
          {directives.length > 0 && (
            <div className="review-directives">
              <button type="button" className="review-directives-head" onClick={() => setDirectivesOpen((value) => !value)}>
                <strong>本轮教师指令 <em>{directives.length}</em></strong>
                <span>
                  生效中 {directives.filter((item) => item.status === "active").length} 条
                  {" · "}
                  已落实 {directives.filter((item) => item.status === "resolved").length} 条
                  {directivePatches.length > 0 ? ` · 改课件 ${directivePatches.length} 处` : ""}
                </span>
              </button>
              {directivesOpen && (
                <ul>
                  {directives.map((directive) => {
                    const patches = directivePatches.filter((item) =>
                      (item.source_intervention_ids || []).includes(directive.directive_id),
                    );
                    const aligned = observations.filter(
                      (item) =>
                        item.category === "alignment" &&
                        item.analysis?.directive_id === directive.directive_id,
                    );
                    // 「已落实」只能由证据支撑：要么有改课件补丁，要么督导明确判定对齐。
                    // 过去用 `aligned.length === 0 && status !== 'active'` 反推——督导没返回
                    // directive_compliance 时一条 alignment 都没有，于是任何 resolved 指令
                    // 都被显示成「已落实 / 督导未发现偏离」，是凭空推断。
                    const settled = directive.status !== "active";
                    const followed =
                      settled &&
                      (patches.length > 0 ||
                        aligned.some((item) => item.severity === "info"));
                    const verdict = !settled
                      ? null
                      : followed
                        ? "已落实"
                        : aligned.length
                          ? "未落实"
                          : "无督导判定";
                    return (
                      <li key={directive.directive_id}>
                        <div className="review-directive-meta">
                          <span className={`review-directive-intent intent-${directive.intent}`}>
                            {directive.intent === "correct" ? "纠正" : directive.intent === "require" ? "要求" : "提问"}
                          </span>
                          <span className="review-directive-scope">
                            {directive.scope === "slide" ? "本页" : directive.scope === "lesson" ? "整节课" : "本轮"}
                          </span>
                          <span className={`review-directive-status status-${directive.status}`}>
                            {directive.status === "active" ? "生效中" : directive.status === "superseded" ? "已被新指令覆盖" : directive.status === "cancelled" ? "已撤销" : verdict}
                          </span>
                          {directive.status === "active" && onCancelDirective && (
                            <button
                              type="button"
                              className="review-directive-cancel"
                              onClick={() => void cancelDirective(directive.directive_id)}
                            >
                              撤销
                            </button>
                          )}
                        </div>
                        <p>{directive.content}</p>
                        {aligned.length > 0 && (
                          <small className="review-directive-miss">督导判定未落实：{aligned[0].issue}</small>
                        )}
                        {patches.length > 0 && (
                          <small className="review-directive-patch">
                            已改课件：{patches.map((item) => `${item.field_path}（${String(item.reason).slice(0, 40)}）`).join("；")}
                          </small>
                        )}
                        {settled && !followed && aligned.length === 0 && (
                          <small className="review-directive-unknown">督导本轮未返回该指令的遵循度判定，无法确认是否落实。</small>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}
          <footer className="review-next-actions">
            <button type="button" disabled={!acceptedCount} onClick={() => onBackToPpt(acceptedPlans, Object.keys(acceptedPlans)[0])}>回到 PPT 审阅</button>
            <button type="button" onClick={onVersions}>查看版本对比</button>
          </footer>
        </section>
        <section className="review-panel">
          <h3>
            逐页证据 <span>{observations.length}</span>
          </h3>
          {observations.length ? (
            sortedObservations.map((obs) => (
              <article
                className={`observation severity-${obs.severity}${isGenericObservation(obs) ? " is-unusable" : ""}`}
                key={obs.observation_id}
              >
                <header>
                  <strong>{obs.slide_id}</strong>
                  <span>
                    {observationTypeLabels[obs.category] || obs.category} · {severityLabels[obs.severity] || obs.severity}
                  </span>
                </header>
                {isGenericObservation(obs) && <div className="observation-quality"><AlertCircle size={12} />证据已保存，但缺少可执行判断</div>}
                <p>{obs.issue}</p>
                {obs.analysis && Object.keys(obs.analysis).length > 0 && (
                  <div className="observation-analysis">
                    {Object.entries(obs.analysis).map(([key, value]) => (
                      <div key={key}><b>{analysisLabels[key] || key}</b><span>{value}</span></div>
                    ))}
                  </div>
                )}
                <div className="observation-events">
                  {obs.event_ids.map((id) => {
                    const event = events.get(id);
                    return (
                      <div key={id}>
                        <b>{formatEventEvidence(event, id)}</b>
                        <span>{event?.content || obs.evidence}</span>
                      </div>
                    );
                  })}
                </div>
                <footer>建议：{obs.recommendation || "暂无可执行建议"}</footer>
              </article>
            ))
          ) : (
            <p className="muted">
              当前还没有可回溯到 Slide 与 Event 的督导观察。
            </p>
          )}
        </section>
      </div>
      </div>
    </>
  );
}

function VersionView({
  runId,
  versions,
  patches,
}: {
  runId: string;
  versions: LessonVersion[];
  patches: RevisionPatch[];
}) {
  const [leftVersionId, setLeftVersionId] = useState(versions[0]?.id || "");
  const [rightVersionId, setRightVersionId] = useState(
    versions[versions.length - 1]?.id || "",
  );
  const [slideIndex, setSlideIndex] = useState(0);
  const leftVersion = versions.find((item) => item.id === leftVersionId) || versions[0];
  const rightVersion = versions.find((item) => item.id === rightVersionId) || versions[versions.length - 1];
  const leftSlide = leftVersion?.slides[slideIndex];
  const rightSlide = rightVersion?.slides[slideIndex];
  const activeSlideId = rightSlide?.slide_id || leftSlide?.slide_id;
  const relatedPatches = patches.filter((patch) => patch.slide_id === activeSlideId);
  return (
    <div className="version-view">
      <header>
        <div>
          <span className="eyebrow">VERSION PROVENANCE</span>
          <h3>版本对比与修改溯源</h3>
        </div>
        <span>
          {versions.length} 个版本 · {patches.length} 个 Patch
        </span>
      </header>
      <div className="version-strip">
        {versions.map((version) => (
          <div className={`version-card ${version.id === rightVersion?.id ? "selected" : ""}`} key={version.id} role="button" tabIndex={0} onClick={() => { setRightVersionId(version.id); setSlideIndex(0); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setRightVersionId(version.id); setSlideIndex(0); } }}>
            <strong>V{version.version_number}</strong>
            <span>{version.status || "draft"}</span>
            <small>
              {version.slides.length} 页 · {version.estimated_minutes || 0} 分钟
            </small>
            <div className="version-actions">
              <a href={lessonVersionExportUrl(runId, version.id, "html")}>
                演示稿
              </a>
              <a href={lessonVersionExportUrl(runId, version.id, "json")}>
                JSON
              </a>
              <a href={lessonVersionExportUrl(runId, version.id, "md")}>讲稿</a>
            </div>
          </div>
        ))}
      </div>
      <section className="version-preview-panel">
        <header>
          <div>
            <span className="eyebrow">SLIDE-BY-SLIDE PREVIEW</span>
            <h4>逐页查看修改前后</h4>
          </div>
          <div className="version-pickers">
            <label>基准版本<select value={leftVersion?.id || ""} onChange={(event) => { setLeftVersionId(event.target.value); setSlideIndex(0); }}>{versions.map((version) => <option key={version.id} value={version.id}>V{version.version_number}</option>)}</select></label>
            <span>对比</span>
            <label>当前版本<select value={rightVersion?.id || ""} onChange={(event) => { setRightVersionId(event.target.value); setSlideIndex(0); }}>{versions.map((version) => <option key={version.id} value={version.id}>V{version.version_number}</option>)}</select></label>
          </div>
        </header>
        <div className="version-slide-nav">
          <button type="button" disabled={slideIndex === 0} onClick={() => setSlideIndex((index) => Math.max(0, index - 1))}>上一页</button>
          <strong>第 {slideIndex + 1} 页 / {Math.max(leftVersion?.slides.length || 0, rightVersion?.slides.length || 0)} 页</strong>
          <button type="button" disabled={slideIndex >= Math.max(leftVersion?.slides.length || 1, rightVersion?.slides.length || 1) - 1} onClick={() => setSlideIndex((index) => index + 1)}>下一页</button>
        </div>
        <div className="version-slide-compare">
          <article><header><span>V{leftVersion?.version_number ?? "-"} · 修改前</span><small>{leftSlide?.slide_id || "本页不存在"}</small></header><LessonSlideCanvas slide={leftSlide} index={slideIndex} total={leftVersion?.slides.length || 0} /></article>
          <article><header><span>V{rightVersion?.version_number ?? "-"} · 修改后</span><small>{rightSlide?.slide_id || "本页不存在"}</small></header><LessonSlideCanvas slide={rightSlide} index={slideIndex} total={rightVersion?.slides.length || 0} /></article>
        </div>
        <div className="version-slide-provenance">
          <strong>本页修改溯源</strong>
          {relatedPatches.length ? relatedPatches.map((patch) => <p key={patch.patch_id}><b>{patch.field_path}</b>：{patch.reason} · 证据 {patch.source_observation_ids.join("、") || "--"}</p>) : <span>本页没有记录到 RevisionPatch，内容保持不变。</span>}
        </div>
      </section>
      <div className="patch-list">
        {patches.length ? (
          patches.map((patch) => (
            <article className="patch-card" key={patch.patch_id}>
              <header>
                <span>
                  {patch.slide_id}
                  {patch.block_id ? ` · ${patch.block_id}` : ""}
                </span>
                <em>{patch.status}</em>
              </header>
              <p>{patch.reason}</p>
              <div>
                <del>{String(patch.before)}</del>
                <span>→</span>
                <ins>{String(patch.after)}</ins>
              </div>
              <small>
                来源观察：{patch.source_observation_ids.join(", ") || "--"}
              </small>
            </article>
          ))
        ) : (
          <div className="classroom-empty">
            <CheckCircle2 size={19} />
            尚未产生课堂证据驱动的版本修改
          </div>
        )}
      </div>
    </div>
  );
}

function DebugView({
  runId,
  round,
  state,
  events,
}: {
  runId: string;
  round: SimulationRound | null;
  state: ClassroomState | null;
  events: ClassroomEvent[];
}) {
  const scope = round ? `${runId}:r${round.round_number}` : `${runId}:r-`;
  return (
    <div className="debug-view">
      <header>
        <Bot size={18} />
        <div>
          <h3>Agent 编排 / 调试</h3>
          <p>显示持久化动作与 Runtime Session，不显示隐藏 Chain-of-Thought。</p>
        </div>
      </header>
      <div className="debug-grid">
        <div>
          <span>run_id</span>
          <code>{runId}</code>
        </div>
        <div>
          <span>round</span>
          <code>
            {round ? `${round.round_number} · ${round.scenario_seed}` : "--"}
          </code>
        </div>
        <div>
          <span>phase</span>
          <code>{state?.phase || "--"}</code>
        </div>
        <div>
          <span>active agent</span>
          <code>{state?.active_agent_id || "--"}</code>
        </div>
        <div>
          <span>turns</span>
          <code>{state?.turn_count ?? 0}</code>
        </div>
        <div>
          <span>events</span>
          <code>{events.length}</code>
        </div>
      </div>
      <section className="session-list">
        <h4>Harness Session 映射</h4>
        {[
          "teacher",
          "student:high",
          "student:medium",
          "student:low",
          "supervisor",
        ].map((key) => (
          <div key={key}>
            <span>{key}</span>
            <code>
              {scope}:{key}
            </code>
          </div>
        ))}
      </section>
      <details className="trace-disclosure">
        <summary>Runtime trace ({events.length})</summary>
        <pre>
          {events
            .map(
              (event) =>
                `${event.sequence} ${event.actor_role} ${event.event_type}: ${event.content}`,
            )
            .join("\n")}
        </pre>
      </details>
    </div>
  );
}
