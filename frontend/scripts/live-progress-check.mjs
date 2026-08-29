import { chromium } from 'playwright';

const runId = 'browser-progress-check';
const createdAt = '2026-08-04T08:00:00.000Z';
const makeMessage = (id, content, phase) => ({
  id,
  agent_id: 'teacher',
  agent_name: '课程教师',
  agent_type: 'teacher',
  phase,
  iteration: 0,
  content,
  created_at: createdAt,
});
const run = {
  id: runId,
  thread_id: 'browser-progress-thread',
  template_id: 'teaching_design',
  objective: '实时进度回归测试课程',
  context: '',
  status: 'running',
  provider: 'mock:deterministic-mock',
  current_node: 'content_analysis',
  teaching_data: {
    document_name: '回归测试材料.md',
    document_text: '这是用于验证实时进度的课程材料。',
    messages: [makeMessage('initial-message', '初始分析已到达', 'design')],
    max_iterations: 1,
    current_iteration: 0,
  },
  pending_input: null,
  error: null,
  created_at: createdAt,
  updated_at: createdAt,
};
const started = (sequence, node, message, stepIndex, messages = []) => ({
  sequence,
  run_id: runId,
  event_type: 'node.started',
  node,
  message,
  payload: { step_index: stepIndex, total_steps: 7, task_started_at: createdAt, messages },
  created_at: createdAt,
});
const initialEvents = [
  { sequence: 1, run_id: runId, event_type: 'run.started', node: 'content_analysis', message: '流程已启动', payload: {}, created_at: createdAt },
  started(2, 'content_analysis', '教师正在剖析课程材料', 1),
];

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('console', (message) => message.type() === 'error' && errors.push(message.text()));
page.on('pageerror', (error) => errors.push(error.message));

await page.addInitScript(() => {
  const NativeWebSocket = window.WebSocket;
  class FakeEventSocket {
    onopen = null;
    onmessage = null;
    onerror = null;
    onclose = null;

    constructor() {
      window.setTimeout(() => {
        this.onopen?.();
        const events = [
          { sequence: 3, node: 'teaching_design', message: '教师正在按你的意见调整教学设计', stepIndex: 2, delay: 600, messages: [] },
          { sequence: 4, node: 'teach_knowledge', message: '教师开始第 1 轮知识讲授', stepIndex: 3, delay: 1400, messages: [] },
          { sequence: 5, node: 'student_question', message: '三类学生正在针对第 1 轮内容提问', stepIndex: 4, delay: 2200, messages: [{
            id: 'live-student-message', agent_id: 'student_low', agent_name: '基础型学生', agent_type: 'student', phase: 'student_question', iteration: 1, content: '实时学生问题已到达', level: 'low', created_at: '2026-08-04T08:00:01.000Z',
          }] },
        ];
        for (const event of events) {
          window.setTimeout(() => this.onmessage?.({ data: JSON.stringify({
            sequence: event.sequence,
            run_id: 'browser-progress-check',
            event_type: 'node.started',
            node: event.node,
            message: event.message,
            payload: { step_index: event.stepIndex, total_steps: 7, task_started_at: '2026-08-04T08:00:00.000Z', messages: event.messages },
            created_at: '2026-08-04T08:00:01.000Z',
          }) }), event.delay);
        }
      }, 50);
    }

    close() {
      this.onclose?.();
    }
  }
  function WebSocket(url, protocols) {
    if (!String(url).includes('/events/ws')) return new NativeWebSocket(url, protocols);
    return new FakeEventSocket();
  }
  WebSocket.OPEN = NativeWebSocket.OPEN;
  window.WebSocket = WebSocket;
});

await page.route('**/api/**', async (route) => {
  const url = new URL(route.request().url());
  if (url.pathname === '/api/settings/model') {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ provider: 'mock', base_url: 'https://api.openai.com/v1', model: 'deterministic-mock', temperature: 0.2, timeout_seconds: 90, has_api_key: false }) });
    return;
  }
  if (url.pathname === '/api/workflows/runs' && route.request().method() === 'GET') {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [run] }) });
    return;
  }
  if (url.pathname === `/api/workflows/runs/${runId}/events`) {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: initialEvents }) });
    return;
  }
  await route.continue();
});

await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle' });
await page.getByText('教学设计教师 · 第 2/7 步').waitFor();
const designOwnerSeen = await page.getByText('教学设计教师 · 第 2/7 步').count();
await page.getByText('课程教师 · 第 3/7 步').waitFor();
const lectureOwnerSeen = await page.getByText('课程教师 · 第 3/7 步').count();
await page.getByText('三类学生智能体 · 第 4/7 步').waitFor();
const studentOwnerSeen = await page.getByText('三类学生智能体 · 第 4/7 步').count();
await page.getByText('实时学生问题已到达').waitFor();

console.log(JSON.stringify({
  designOwnerSeen,
  lectureOwnerSeen,
  studentOwnerSeen,
  mergedMessageVisible: await page.getByText('实时学生问题已到达').count(),
  consoleErrors: errors,
}, null, 2));
await browser.close();
