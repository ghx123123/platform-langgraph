import { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { AgentNode } from './AgentNode';
import { MessageEdge } from './MessageEdge';
import { useExecutionStore } from '../../../stores/executionStore';
import { cn } from '../../../utils/cn';
import type { AgentNodeData } from '../../../types/visualization';

interface AgentGraphViewProps {
  className?: string;
  onAgentClick?: (agentId: string) => void;
}

export function AgentGraphView({ className, onAgentClick }: AgentGraphViewProps) {
  const { agentNodes, agentEdges, activeAgentId } = useExecutionStore();

  // Convert AgentNodeData to React Flow nodes
  const initialNodes = useMemo(() => {
    const positions = getNodePositions(agentNodes.length);

    return agentNodes.map((node, index) => ({
      id: node.id,
      type: 'agent' as const,
      position: positions[index],
      data: node,
      selected: node.id === activeAgentId,
    }));
  }, [agentNodes, activeAgentId]);

  // Convert AgentEdgeData to React Flow edges
  const initialEdges = useMemo(() => {
    return agentEdges.map((edge) => ({
      id: `${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      type: 'message' as const,
      data: edge,
      animated: edge.animated,
    }));
  }, [agentEdges]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect = useCallback(
    (params: Connection) => {
      setEdges((eds) => addEdge({ ...params, type: 'message' }, eds));
    },
    [setEdges]
  );

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: { id: string; data: AgentNodeData }) => {
      onAgentClick?.(node.id);
    },
    [onAgentClick]
  );

  // Update nodes when agentNodes changes
  useMemo(() => {
    const positions = getNodePositions(agentNodes.length);
    const newNodes = agentNodes.map((node, index) => ({
      id: node.id,
      type: 'agent' as const,
      position: positions[index],
      data: node,
      selected: node.id === activeAgentId,
    }));
    setNodes(newNodes);
  }, [agentNodes, activeAgentId, setNodes]);

  // Update edges when agentEdges changes
  useMemo(() => {
    const newEdges = agentEdges.map((edge) => ({
      id: `${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      type: 'message' as const,
      data: edge,
      animated: edge.animated,
    }));
    setEdges(newEdges);
  }, [agentEdges, setEdges]);

  if (agentNodes.length === 0) {
    return (
      <div className={cn('flex items-center justify-center h-full bg-slate-50 rounded-2xl', className)}>
        <div className="text-center text-slate-400">
          <div className="text-5xl mb-4">🔗</div>
          <p className="font-medium">暂无 Agent 协作图</p>
          <p className="text-sm mt-1">开始对话后会自动生成</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('h-full w-full', className)}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        nodeTypes={{ agent: AgentNode }}
        edgeTypes={{ message: MessageEdge }}
        fitView
        attributionPosition="bottom-left"
        proOptions={{ hideAttribution: true }}
      >
        <Controls className="bg-white rounded-lg shadow-lg border border-slate-200" />
        <MiniMap
          className="bg-white rounded-lg shadow-lg border border-slate-200"
          nodeColor={(node) => {
            const status = node.data?.status;
            switch (status) {
              case 'thinking':
              case 'speaking':
                return '#3b82f6';
              case 'waiting':
                return '#f59e0b';
              case 'completed':
                return '#10b981';
              case 'error':
                return '#ef4444';
              default:
                return '#94a3b8';
            }
          }}
          maskColor="rgba(241, 245, 249, 0.8)"
        />
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e2e8f0" />
      </ReactFlow>
    </div>
  );
}

// Helper to position nodes in a circle
function getNodePositions(count: number): { x: number; y: number }[] {
  if (count === 0) return [];
  if (count === 1) return [{ x: 250, y: 150 }];

  const positions: { x: number; y: number }[] = [];
  const centerX = 250;
  const centerY = 150;
  const radius = 180;
  const angleStep = (2 * Math.PI) / count;

  for (let i = 0; i < count; i++) {
    const angle = i * angleStep - Math.PI / 2;
    positions.push({
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    });
  }

  return positions;
}