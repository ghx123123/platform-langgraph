// GraphView.tsx — 图谱画布 (Enterprise SaaS 风格): 中心根节点大卡 + 环形子节点卡 + 连线关系标签 + 可拖动/折叠/缩放
import { useRef, useState } from 'react';
import type { ReactElement } from 'react';

export interface GraphNodeItem {
  id: string;
  title: string;
  parent_id?: string | null;
  content?: string;
  section_title?: string;
}

interface Props {
  nodes: GraphNodeItem[];
  selectedId: string;
  onSelect: (id: string) => void;
  zoom: number;
  onZoom: (value: number) => void;
  zoomResetToken?: number; // 递增 -> 视野重置为 1x 并居中
}

const RING1 = 150; // 第一环半径(中心到环上子节点)
const RING_STEP = 104; // 后续环半径步长
const CARD_W = 86; // 根节点卡片宽
const CARD_H = 66; // 根节点卡片高
const CHILD_W = 58; // 子节点卡片宽
const CHILD_H = 46; // 子节点卡片高

// 层级: 0=根, 1=第一环, 2=第二环, ...(后代环)
function tierOf(nodes: GraphNodeItem[], id: string): number {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  let cur = byId.get(id);
  let tier = 0;
  const seen = new Set<string>();
  while (cur?.parent_id && byId.has(cur.parent_id) && !seen.has(cur.id)) {
    seen.add(cur.id);
    tier += 1;
    cur = byId.get(cur.parent_id);
  }
  return tier;
}

// 环状配色: 0=中心深蓝, 1=浅蓝, 2=薄荷绿, 3=淡紫(第3环以上复用淡紫)
const RING_COLORS = [
  { fill: '#2563eb', stroke: '#2563eb', accent: '#ffffff', label: '#ffffff', labelBg: 'rgba(37,99,235,.14)', line: '#2563eb' },
  { fill: '#e8f2ff', stroke: '#bcd9ff', accent: '#2563eb', label: '#3a6bca', labelBg: '#ffffff', line: '#2563eb' },
  { fill: '#e5f8ee', stroke: '#b7e6cc', accent: '#1f9d61', label: '#217d51', labelBg: '#ffffff', line: '#1f9d61' },
  { fill: '#f0ecff', stroke: '#d3c8f5', accent: '#7b61d4', label: '#6653b4', labelBg: '#ffffff', line: '#7b61d4' },
];
const ringColor = (tier: number) => RING_COLORS[Math.min(Math.max(tier, 0), 3)];

function radialLayout(nodes: GraphNodeItem[]) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const children = new Map<string, GraphNodeItem[]>();
  const roots: GraphNodeItem[] = [];
  for (const n of nodes) {
    const p = n.parent_id && byId.has(n.parent_id) ? n.parent_id : '';
    if (!p) roots.push(n);
    else {
      if (!children.has(p)) children.set(p, []);
      children.get(p)!.push(n);
    }
  }
  const center = roots[0];
  const center2 = center ? byId.get(center.id) : undefined;
  const pos = new Map<string, { x: number; y: number; isCenter: boolean }>();
  if (center2) pos.set(center2.id, { x: 0, y: 0, isCenter: true });
  // 第一环: center 的子节点
  const firstKids = (center2 && children.get(center2.id)) || [];
  firstKids.forEach((k, i) => {
    const angle = (Math.PI * 2 * i) / Math.max(firstKids.length, 1) - Math.PI / 2;
    pos.set(k.id, { x: Math.cos(angle) * RING1, y: Math.sin(angle) * RING1, isCenter: false });
  });
  // 其他根(旁支) 也辐射
  roots.slice(1).forEach((k, i) => {
    const angle = (Math.PI * 2 * i) / Math.max(roots.length - 1, 1) - Math.PI / 3;
    const r = RING1 * 1.35;
    pos.set(k.id, { x: Math.cos(angle) * r, y: Math.sin(angle) * r, isCenter: false });
  });
  // 第二环及更深: 以父节点为基准向外放射
  let changed = true;
  while (changed) {
    changed = false;
    for (const parent of nodes) {
      const kids = children.get(parent.id) || [];
      for (const kid of kids) {
        if (pos.has(kid.id)) continue;
        const pPos = pos.get(parent.id);
        if (!pPos) continue;
        const pAngle = Math.atan2(pPos.y, pPos.x);
        const r = Math.hypot(pPos.x, pPos.y) + RING_STEP;
        const kidsCount = kids.length;
        const kidIndex = kids.findIndex((x) => x.id === kid.id);
        const angle = pAngle + (kidsCount > 1 ? (kidIndex - (kidsCount - 1) / 2) * 0.45 : 0);
        pos.set(kid.id, { x: Math.cos(angle) * r, y: Math.sin(angle) * r, isCenter: false });
        changed = true;
      }
    }
  }
  return { pos, children, center: center2, roots, byId };
}

export default function GraphView({ nodes, selectedId, onSelect, zoom, onZoom, zoomResetToken }: Props): ReactElement | null {
  const [offsets, setOffsets] = useState<Map<string, { dx: number; dy: number }>>(new Map());
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const dragging = useRef<{ id: string; px: number; py: number; off: { dx: number; dy: number } } | null>(null);
  const lastZoomReset = useRef(-1);
  // 当 zoomResetToken 递增时, 重复的缩放状态被清除 (fit/center 键)
  if (zoomResetToken !== undefined && zoomResetToken !== lastZoomReset.current) {
    lastZoomReset.current = zoomResetToken;
    if (zoom !== 1) onZoom(1);
  }
  if (!nodes.length) return <div style={{ color: '#8190a0', fontSize: 12, padding: 12 }}>暂无图谱节点</div>;
  const { pos, children } = radialLayout(nodes);
  const colorOf = (id: string) => ringColor(tierOf(nodes, id));

  const hasChildren = (id: string) => (children.get(id) || []).length > 0;
  const isCollapsed = (id: string) => collapsed.has(id);
  const collectDescendants = (id: string): string[] => {
    const out: string[] = [];
    for (const k of children.get(id) || []) out.push(k.id, ...collectDescendants(k.id));
    return out;
  };
  const visibleIds = new Set<string>(nodes.map((n) => n.id));
  for (const id of collapsed) for (const d of collectDescendants(id)) visibleIds.delete(d);
  const visibleNodes = nodes.filter((n) => visibleIds.has(n.id));
  const toggle = (id: string) => {
    setCollapsed((cur) => { const next = new Set(cur); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };

  const nodeAnchor = (id: string): { x: number; y: number; isCenter: boolean } | null => {
    const p = pos.get(id);
    if (!p) return null;
    const o = offsets.get(id);
    return { x: p.x + (o?.dx || 0), y: p.y + (o?.dy || 0), isCenter: p.isCenter };
  };
  const cardDims = (isCenter: boolean) => ({ w: isCenter ? CARD_W : CHILD_W, h: isCenter ? CARD_H : CHILD_H });

  // ---- 内容包围盒 (卡片+标签) ----
  const anchors = visibleNodes.map((n) => ({ node: n, a: nodeAnchor(n.id)! })).filter((v) => v.a !== null);
  const LABEL_PAD = 46;
  const PAD = 46;
  const minX = Math.min(...anchors.map((v) => { const { w } = cardDims(v.a.isCenter); return v.a.x - w / 2; }));
  const minY = Math.min(...anchors.map((v) => { const { h } = cardDims(v.a.isCenter); return v.a.y - h / 2; }));
  const maxX = Math.max(...anchors.map((v) => { const { w } = cardDims(v.a.isCenter); return v.a.x + w / 2 + LABEL_PAD; }));
  const maxY = Math.max(...anchors.map((v) => { const { h } = cardDims(v.a.isCenter); return v.a.y + h / 2 + LABEL_PAD; }));
  let vbX = minX - PAD, vbY = minY - PAD;
  let vbW = Math.max(360, maxX - minX + PAD * 2);
  let vbH = Math.max(200, maxY - minY + PAD * 2);
  const z = Math.min(2.5, Math.max(0.5, zoom || 1));
  const cX = vbX + vbW / 2, cY = vbY + vbH / 2;
  vbW = Math.max(240, vbW / z);
  vbH = Math.max(160, vbH / z);
  vbX = cX - vbW / 2;
  vbY = cY - vbH / 2;

  const edges: Array<{ from: string; to: string }> = [];
  for (const n of visibleNodes) if (n.parent_id && visibleIds.has(n.parent_id)) edges.push({ from: n.parent_id, to: n.id });

  const onPointerDown = (id: string, e: React.PointerEvent<SVGGElement>) => {
    dragging.current = { id, px: e.clientX, py: e.clientY, off: offsets.get(id) || { dx: 0, dy: 0 } };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const d = dragging.current;
    if (!d) return;
    const dx = d.off.dx + (e.clientX - d.px);
    const dy = d.off.dy + (e.clientY - d.py);
    setOffsets((cur) => { const next = new Map(cur); next.set(d.id, { dx, dy }); return next; });
  };
  const onPointerUp = () => { dragging.current = null; };

  return (
    <div className="gv-scroll">
      <svg ref={undefined} width={vbW} height={vbH} className="gv-svg" onPointerMove={onPointerMove} onPointerUp={onPointerUp} role="img" aria-label="图谱节点关系(放射, 可拖动)" style={{ maxWidth: '100%', height: 'auto' }}>
        <g transform={`translate(${-vbX} ${-vbY})`}>
          {edges.map((e) => {
            const f = nodeAnchor(e.from);
            const t = nodeAnchor(e.to);
            if (!f || !t) return null;
            const c1 = { x: f.x * 0.55 + t.x * 0.45, y: f.y * 0.55 + t.y * 0.45 };
            const c2 = { x: f.x * 0.45 + t.x * 0.55, y: f.y * 0.45 + t.y * 0.55 };
            const mx = (f.x + t.x) / 2;
            const my = (f.y + t.y) / 2;
            const lineColor = colorOf(e.from).line;
            // 关系标签: 0/1 环之间=包含, 更深=关联
            const fromTier = tierOf(nodes, e.from);
            const relation = fromTier === 0 ? '包含' : fromTier === 1 ? '关联' : '延伸';
            return (
              <g key={`${e.from}-${e.to}`}>
                <path d={`M ${f.x} ${f.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${t.x} ${t.y}`} fill="none" stroke={lineColor} strokeOpacity="0.5" strokeWidth="1.5" />
                <rect x={mx - 19} y={my - 9} width="38" height="18" rx="9" fill="#ffffff" stroke="#dfe8f3" />
                <text x={mx} y={my + 4} textAnchor="middle" fontSize="10.5" fill="#7285a0">{relation}</text>
              </g>
            );
          })}
          {visibleNodes.map((n) => {
            const a = nodeAnchor(n.id);
            if (!a) return null;
            const selected = n.id === selectedId;
            const { w, h } = cardDims(a.isCenter);
            const color = colorOf(n.id);
            const x = a.x - w / 2;
            const y = a.y - h / 2;
            const folded = isCollapsed(n.id);
            const canFold = hasChildren(n.id);
            const label = n.title.length > 14 ? n.title.slice(0, 14) + '…' : n.title;
            const btnX = a.x + w / 2 - 3;
            const btnY = a.y - h / 2 - 8;
            return (
              <g key={n.id} onClick={() => onSelect(n.id)} onPointerDown={(e) => onPointerDown(n.id, e)} style={{ cursor: 'grab' }}>
                {selected && <rect x={x - 5} y={y - 5} width={w + 10} height={h + 10} rx={a.isCenter ? 12 : 9} fill="#5da0ff" fillOpacity="0.12" stroke="#2563eb" strokeOpacity="0.55" strokeWidth="1.5" />}
                <rect x={x} y={y} width={w} height={h} rx={a.isCenter ? 12 : 9} fill={color.fill} stroke={selected ? '#2563eb' : color.stroke} strokeWidth={a.isCenter ? 1.8 : 1.2} style={{ filter: selected || a.isCenter ? 'drop-shadow(0 4px 10px rgba(37,99,235,.18))' : 'drop-shadow(0 2px 6px rgba(35,60,90,.10))' }} />
                {/* 卡片内图标(线性): 根=深蓝凹刻白色书形; 子=彩色小方图标 */}
                {a.isCenter
                  ? <><rect x={a.x - 11} y={a.y - 12} width="22" height="18" rx="4" fill="#ffffff" fillOpacity="0.16" /><path d={`M ${a.x - 4} ${a.y - 7} q 4 -3 8 0 v 12 q -4 -3 -8 0 z`} fill="#ffffff" /><text x={a.x} y={a.y + 26} textAnchor="middle" fontSize="11.5" fontWeight="700" fill={color.label}>{label}</text></>
                  : <><rect x={a.x - 9} y={a.y - 16} width="18" height="14" rx="3.5" fill="#ffffff" fillOpacity="0.75" stroke={color.accent} strokeWidth="1" /><text x={a.x} y={a.y + 12} textAnchor="middle" fontSize="8.5">▤</text><text x={a.x} y={a.y + 34} textAnchor="middle" fontSize="11" fill={color.label}>{label}</text></>}
                {canFold && <g onClick={(e) => { e.stopPropagation(); toggle(n.id); }} style={{ cursor: 'pointer' }}><circle cx={btnX} cy={btnY} r={9} fill={folded ? '#b9cbdf' : '#ffffff'} stroke="#c6d5e6" strokeWidth="1" /><path d={`M ${btnX - 3} ${btnY} h 6 ${folded ? 'M ' + btnX + ' ' + (btnY - 3) + ' v 6' : ''}`} stroke={folded ? '#ffffff' : '#5a6b82'} strokeWidth="1.6" strokeLinecap="round" /></g>}
                <title>{n.title}{canFold ? (folded ? ' (点击 + 展开子节点)' : ' (点击 − 折叠子节点)') : ''}</title>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}