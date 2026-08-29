import { memo } from 'react';
import { getBezierPath, type EdgeProps } from '@xyflow/react';
import { cn } from '../../../utils/cn';
import type { AgentEdgeData } from '../../../types/visualization';

function MessageEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
  animated,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const edgeData = data as AgentEdgeData;
  const { count = 0, type = 'message' } = edgeData || {};

  const edgeColor = animated ? '#3b82f6' : selected ? '#3b82f6' : '#94a3b8';

  return (
    <>
      {/* Background path for better hit area */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        className="cursor-pointer"
      />

      {/* Main edge path */}
      <path
        id={id}
        d={edgePath}
        fill="none"
        stroke={edgeColor}
        strokeWidth={selected ? 3 : 2}
        className={cn(animated && 'animate-flow')}
        style={{
          strokeDasharray: type === 'broadcast' ? '5,5' : undefined,
        }}
      />

      {/* Animated flow effect */}
      {animated && (
        <path
          d={edgePath}
          fill="none"
          stroke="#60a5fa"
          strokeWidth={2}
          strokeDasharray="5,5"
          className="animate-dash"
        >
          <animate
            attributeName="stroke-dashoffset"
            from="10"
            to="0"
            dur="1s"
            repeatCount="indefinite"
          />
        </path>
      )}

      {/* Message count badge */}
      {count > 0 && (
        <foreignObject
          x={labelX - 15}
          y={labelY - 10}
          width={30}
          height={20}
          className="overflow-visible"
        >
          <div
            className={cn(
              'px-1.5 py-0.5 rounded-full text-xs font-medium text-white',
              animated ? 'bg-blue-500' : 'bg-slate-400'
            )}
          >
            {count}
          </div>
        </foreignObject>
      )}

      {/* Arrow marker */}
      <circle
        cx={targetX - (targetX - sourceX) * 0.05}
        cy={targetY - (targetY - sourceY) * 0.05}
        r={3}
        fill={edgeColor}
      />
    </>
  );
}

export const MessageEdge = memo(MessageEdgeComponent);