import { useEffect, useMemo } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import { Bot, Check, Circle, Loader2, ShieldAlert } from 'lucide-react';
import '@xyflow/react/dist/style.css';
import type { RunEvent, WorkflowTemplate } from '../../types/workflow';

type NodeStatus = 'idle' | 'active' | 'completed' | 'error';

interface AgentNodeData extends Record<string, unknown> {
  label: string;
  description: string;
  accent: string;
  status: NodeStatus;
}

type AgentFlowNode = Node<AgentNodeData, 'agent'>;

function AgentNode({ data, selected }: NodeProps<AgentFlowNode>) {
  const StateIcon = data.status === 'active' ? Loader2 : data.status === 'completed' ? Check : data.status === 'error' ? ShieldAlert : Circle;
  return (
    <div className={`agent-node status-${data.status} ${selected ? 'is-selected' : ''}`} style={{ '--agent-accent': data.accent } as React.CSSProperties}>
      <Handle type="target" position={Position.Top} />
      <div className="agent-node-icon"><Bot size={16} aria-hidden="true" /></div>
      <div className="agent-node-copy">
        <strong>{data.label}</strong>
        <span>{data.description}</span>
      </div>
      <StateIcon className="agent-node-state" size={15} aria-hidden="true" />
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

interface WorkflowGraphProps {
  template: WorkflowTemplate | null;
  events: RunEvent[];
  selectedNode: string | null;
  onSelectNode: (nodeId: string) => void;
}

export function WorkflowGraph({ template, events, selectedNode, onSelectNode }: WorkflowGraphProps) {
  const graph = useMemo(() => {
    if (!template) return { nodes: [] as AgentFlowNode[], edges: [] as Edge[] };
    const statuses = new Map<string, NodeStatus>();
    template.agents.forEach((agent) => statuses.set(agent.id, 'idle'));
    statuses.set('finalize', 'idle');
    events.forEach((event) => {
      if (!event.node) return;
      if (event.event_type === 'node.started') statuses.set(event.node, 'active');
      if (['node.completed', 'review.completed'].includes(event.event_type)) statuses.set(event.node, 'completed');
      if (event.event_type === 'run.failed') statuses.set(event.node, 'error');
    });

    const planner = template.agents.find((agent) => agent.role === 'planner');
    const experts = template.agents.filter((agent) => !['planner', 'synthesizer', 'reviewer'].includes(agent.role));
    const synthesizer = template.agents.find((agent) => agent.role === 'synthesizer');
    const reviewer = template.agents.find((agent) => agent.role === 'reviewer');
    const centerX = 390;
    const expertGap = 250;
    const expertStart = centerX - ((experts.length - 1) * expertGap) / 2;
    const specs = [
      ...(planner ? [{ ...planner, position: { x: centerX, y: 30 } }] : []),
      ...experts.map((agent, index) => ({ ...agent, position: { x: expertStart + index * expertGap, y: 185 } })),
      ...(synthesizer ? [{ ...synthesizer, position: { x: centerX, y: 350 } }] : []),
      ...(reviewer ? [{ ...reviewer, position: { x: centerX, y: 505 } }] : []),
      { id: 'finalize', name: '最终交付', role: 'finalize', description: '锁定结果与审阅记录', accent: '#2563eb', position: { x: centerX, y: 660 } },
    ];
    const nodes: AgentFlowNode[] = specs.map((agent) => ({
      id: agent.id,
      type: 'agent',
      position: agent.position,
      initialWidth: 198,
      initialHeight: 68,
      selected: selectedNode === agent.id,
      data: { label: agent.name, description: agent.description, accent: agent.accent, status: statuses.get(agent.id) || 'idle' },
    }));
    const edges: Edge[] = [
      ...experts.map((agent) => ({ id: `planner-${agent.id}`, source: planner?.id || 'planner', target: agent.id, animated: statuses.get(agent.id) === 'active' })),
      ...experts.map((agent) => ({ id: `${agent.id}-synthesizer`, source: agent.id, target: synthesizer?.id || 'synthesizer' })),
      { id: 'synthesizer-reviewer', source: synthesizer?.id || 'synthesizer', target: reviewer?.id || 'reviewer' },
      { id: 'reviewer-finalize', source: reviewer?.id || 'reviewer', target: 'finalize' },
      { id: 'reviewer-revise', source: reviewer?.id || 'reviewer', target: synthesizer?.id || 'synthesizer', label: '修订', type: 'smoothstep', style: { strokeDasharray: '5 5' } },
    ];
    return { nodes, edges };
  }, [events, selectedNode, template]);

  const [nodes, setNodes, onNodesChange] = useNodesState<AgentFlowNode>(graph.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(graph.edges);

  useEffect(() => {
    setNodes(graph.nodes);
    setEdges(graph.edges);
  }, [graph, setEdges, setNodes]);

  if (!template) return <div className="graph-empty">请选择一个工作流模板</div>;

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={nodeTypes}
      onNodeClick={(_, node) => onSelectNode(node.id)}
      nodesDraggable={false}
      nodesConnectable={false}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      minZoom={0.5}
      maxZoom={1.35}
      proOptions={{ hideAttribution: true }}
    >
      <Controls showInteractive={false} />
      <MiniMap pannable zoomable nodeColor={(node) => String(node.data?.accent || '#94a3b8')} maskColor="rgba(248, 250, 252, 0.72)" />
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#e2e8f0" />
    </ReactFlow>
  );
}
