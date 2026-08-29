import './WelcomePanel.css';
import { BookOpen, GraduationCap, Play, Settings, ShieldCheck, Sparkles, Upload, Users } from 'lucide-react';

interface WelcomePanelProps {
  onUpload: () => void;
  onDemo: () => void;
}

const steps = [
  {
    icon: Upload,
    title: '上传课程材料',
    description: '支持 PDF / DOCX / PPTX / Markdown / TXT，一份材料即可开始',
  },
  {
    icon: BookOpen,
    title: '确认 AI 抽取的知识点',
    description: '系统自动识别重点、难点与核心知识结构，可随时调整',
  },
  {
    icon: Play,
    title: '启动教学',
    description: '智能体团队自动完成「剖析 → 设计 → 讲授 → 提问 → 答疑 → 督导改进」',
  },
];

const agents = [
  { icon: GraduationCap, label: '教师' },
  { icon: Users, label: '分层学生' },
  { icon: ShieldCheck, label: '教学督导' },
];

export function WelcomePanel({ onUpload, onDemo }: WelcomePanelProps) {
  return (
    <div className="welcome-panel">
      <div className="welcome-card">
        <div className="welcome-brand">
          <div className="welcome-logo">
            <Sparkles size={22} />
          </div>
          <h2 className="welcome-title">课程教学智能体平台</h2>
          <p className="welcome-subtitle">上传课程材料，教师、分层学生与教学督导协作完成从剖析到改进的完整教学设计。</p>
        </div>

        <div className="welcome-agents" aria-label="参与角色">
          {agents.map((agent) => {
            const Icon = agent.icon;
            return (
              <span key={agent.label}>
                <Icon size={13} />
                {agent.label}
              </span>
            );
          })}
        </div>

        <ol className="welcome-steps">
          {steps.map((step, index) => {
            const Icon = step.icon;
            return (
              <li className="welcome-step" key={step.title}>
                <div className="welcome-step-head">
                  <span className="welcome-step-badge">{index + 1}</span>
                  <Icon className="welcome-step-icon" size={18} />
                </div>
                <strong className="welcome-step-title">{step.title}</strong>
                <p className="welcome-step-desc">{step.description}</p>
              </li>
            );
          })}
        </ol>

        <div className="welcome-actions">
          <button type="button" className="welcome-btn welcome-btn-primary" onClick={onUpload}>
            <Upload size={16} />
            上传课程材料
          </button>
          <button type="button" className="welcome-btn welcome-btn-secondary" onClick={onDemo}>
            <Play size={15} fill="currentColor" />
            先看看效果 · 载入示例课程
          </button>
        </div>

        <p className="welcome-note">
          <Settings size={12} />
          默认使用本地演示模型，可在右上角「齿轮」切换到任意 OpenAI 兼容模型。
        </p>
      </div>
    </div>
  );
}
