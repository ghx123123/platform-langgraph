import type { LucideIcon } from 'lucide-react';
import { Clipboard, FileText, GraduationCap, Layers3, ShieldCheck, Users } from 'lucide-react';

export type AgentRoleKind = 'analyst' | 'designer' | 'teacher' | 'student' | 'supervisor' | 'finalizer';
export type AgentRolePhase = 'content_analysis' | 'teaching_design' | 'teach_knowledge' | 'student_question' | 'teacher_answer' | 'supervisor_comment' | 'finalize';

export interface AgentRoleDefinition {
  key: string;
  name: string;
  role: string;
  responsibility: string;
  input: string;
  output: string;
  kind: AgentRoleKind;
  phase: AgentRolePhase;
  icon: LucideIcon;
}

/** Role contracts are the stable UI boundary; workflow phases only adapt into them. */
export const AGENT_ROLE_DEFINITIONS: AgentRoleDefinition[] = [
  { key: 'analysis', name: '教材分析员', role: '内容理解角色', responsibility: '建立知识边界，识别重难点与证据', input: '教材原文 · 知识范围', output: '内容分析 · 知识点证据', kind: 'analyst', phase: 'content_analysis', icon: FileText },
  { key: 'design', name: '教学设计员', role: '方案编排角色', responsibility: '把知识点组织成可执行的课堂方案', input: '内容分析 · 教学约束', output: '目标 · 环节 · 练习', kind: 'designer', phase: 'teaching_design', icon: Layers3 },
  { key: 'teach', name: '讲授教师', role: '课堂表达角色', responsibility: '将方案转化为清晰、可讲授的教学内容', input: '教学方案 · 知识证据', output: '讲授稿 · 课堂提示', kind: 'teacher', phase: 'teach_knowledge', icon: GraduationCap },
  { key: 'students', name: '分层学生', role: '学习者模拟角色', responsibility: '从不同基础检验理解门槛与疑问', input: '讲授内容 · 学习目标', output: '分层问题 · 认知盲点', kind: 'student', phase: 'student_question', icon: Users },
  { key: 'answer', name: '答疑教师', role: '反馈澄清角色', responsibility: '针对真实疑问补充解释并纠正误解', input: '学生问题 · 讲授稿', output: '答疑稿 · 澄清策略', kind: 'teacher', phase: 'teacher_answer', icon: GraduationCap },
  { key: 'supervisor', name: '教学督导', role: '质量评审角色', responsibility: '独立检查目标、证据、节奏与可实施性', input: '完整教学方案 · 互动记录', output: '评分 · 改进建议', kind: 'supervisor', phase: 'supervisor_comment', icon: ShieldCheck },
  { key: 'finalize', name: '成果整理员', role: '交付整合角色', responsibility: '汇总各角色产出，形成可编辑教案', input: '方案 · 讲授 · 答疑 · 评审', output: '教案定稿 · 导出数据', kind: 'finalizer', phase: 'finalize', icon: Clipboard },
];
