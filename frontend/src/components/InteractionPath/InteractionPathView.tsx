// InteractionPathView.tsx - 互动路径可视化组件
import { useState, useEffect, useMemo } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import * as ScrollArea from '@radix-ui/react-scroll-area';
import * as Avatar from '@radix-ui/react-avatar';
import { 
  X, 
  Clock, 
  MessageCircle, 
  HelpCircle, 
  CheckCircle, 
  AlertCircle,
  ChevronRight,
  ChevronDown,
  BarChart3,
  GitBranch,
  AlignLeft,
  Sparkles,
  TrendingUp
} from 'lucide-react';
import { 
  fetchInteractionPath, 
  InteractionNode, 
  InteractionStatistics,
  groupByTimeline,
  buildTreeStructure,
  getNodeTypeConfig,
} from '../../services/interactionApi';

interface InteractionPathViewProps {
  sessionId: string;
  className?: string;
}

type ViewMode = 'timeline' | 'chain';

// 统计卡片组件
function StatCard({ 
  title, 
  value, 
  icon: Icon, 
  color,
  subtitle 
}: { 
  title: string; 
  value: string | number; 
  icon: React.ElementType;
  color: string;
  subtitle?: string;
}) {
  const colorClasses: Record<string, { bg: string; text: string; border: string }> = {
    blue: { bg: 'bg-blue-50', text: 'text-blue-600', border: 'border-blue-200' },
    emerald: { bg: 'bg-emerald-50', text: 'text-emerald-600', border: 'border-emerald-200' },
    orange: { bg: 'bg-orange-50', text: 'text-orange-600', border: 'border-orange-200' },
    purple: { bg: 'bg-purple-50', text: 'text-purple-600', border: 'border-purple-200' },
    slate: { bg: 'bg-slate-50', text: 'text-slate-600', border: 'border-slate-200' },
  };
  
  const colors = colorClasses[color] || colorClasses.slate;
  
  return (
    <div className={`p-4 rounded-lg border ${colors.bg} ${colors.border}`}>
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg bg-white ${colors.text}`}>
          <Icon size={20} />
        </div>
        <div>
          <div className="text-xs text-slate-500">{title}</div>
          <div className={`text-xl font-bold ${colors.text}`}>{value}</div>
          {subtitle && <div className="text-xs text-slate-400">{subtitle}</div>}
        </div>
      </div>
    </div>
  );
}

// 节点详情弹窗
function NodeDetailDialog({ 
  node, 
  open, 
  onOpenChange,
  allNodes 
}: { 
  node: InteractionNode | null; 
  open: boolean; 
  onOpenChange: (open: boolean) => void;
  allNodes: InteractionNode[];
}) {
  if (!node) return null;
  
  const config = getNodeTypeConfig(node.interaction_type);
  const parentNode = node.parent_id ? allNodes.find(n => n.id === node.parent_id) : null;
  const childNodes = allNodes.filter(n => n.parent_id === node.id);
  
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-50 animate-fadeIn" />
        <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-2xl max-h-[80vh] bg-white rounded-xl shadow-2xl z-50 overflow-hidden animate-scaleIn">
          {/* 头部 */}
          <div className={`px-6 py-4 border-b ${config.bgColor} ${config.borderColor}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{node.agent_avatar || config.icon}</span>
                <div>
                  <Dialog.Title className="text-lg font-bold text-slate-800">
                    {node.agent_name}
                  </Dialog.Title>
                  <div className="flex items-center gap-2 text-sm">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium bg-white ${config.color}`}>
                      {config.label}
                    </span>
                    <span className="text-slate-500">
                      {new Date(node.created_at).toLocaleString()}
                    </span>
                  </div>
                </div>
              </div>
              <Dialog.Close className="p-2 hover:bg-white/50 rounded-lg transition-colors">
                <X size={20} className="text-slate-500" />
              </Dialog.Close>
            </div>
          </div>
          
          {/* 内容 */}
          <ScrollArea.Root className="overflow-hidden">
            <ScrollArea.Viewport className="max-h-[60vh]">
              <div className="p-6 space-y-6">
                {/* 关联信息 */}
                {parentNode && (
                  <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                    <div className="text-xs font-medium text-slate-500 mb-2">回复自</div>
                    <div className="flex items-center gap-2">
                      <span>{parentNode.agent_avatar}</span>
                      <span className="text-sm font-medium text-slate-700">{parentNode.agent_name}</span>
                      <ChevronRight size={16} className="text-slate-400" />
                      <span className="text-sm text-slate-600 truncate flex-1">
                        {parentNode.content.slice(0, 50)}...
                      </span>
                    </div>
                  </div>
                )}
                
                {/* 主要内容 */}
                <div>
                  <div className="text-xs font-medium text-slate-500 mb-2">内容</div>
                  <div className="p-4 bg-slate-50 rounded-lg border border-slate-200">
                    <p className="text-sm text-slate-800 whitespace-pre-wrap leading-relaxed">
                      {node.content}
                    </p>
                  </div>
                </div>
                
                {/* 子回复 */}
                {childNodes.length > 0 && (
                  <div>
                    <div className="text-xs font-medium text-slate-500 mb-2">
                      相关回复 ({childNodes.length})
                    </div>
                    <div className="space-y-2">
                      {childNodes.map(child => {
                        const childConfig = getNodeTypeConfig(child.interaction_type);
                        return (
                          <div 
                            key={child.id} 
                            className={`p-3 rounded-lg border ${childConfig.bgColor} ${childConfig.borderColor}`}
                          >
                            <div className="flex items-center gap-2 mb-1">
                              <span>{child.agent_avatar}</span>
                              <span className="text-sm font-medium text-slate-700">{child.agent_name}</span>
                              <span className={`text-xs px-1.5 py-0.5 rounded ${childConfig.color} bg-white`}>
                                {childConfig.label}
                              </span>
                            </div>
                            <p className="text-sm text-slate-600 truncate">
                              {child.content.slice(0, 80)}...
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                
                {/* 元信息 */}
                <div className="flex items-center gap-4 text-xs text-slate-400 pt-4 border-t border-slate-200">
                  <span>ID: {node.id.slice(0, 8)}...</span>
                  <span>第 {node.iteration} 轮</span>
                  {node.phase && <span>阶段: {node.phase}</span>}
                </div>
              </div>
            </ScrollArea.Viewport>
            <ScrollArea.Scrollbar className="w-2 bg-slate-100" orientation="vertical">
              <ScrollArea.Thumb className="bg-slate-300 rounded-full" />
            </ScrollArea.Scrollbar>
          </ScrollArea.Root>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// 时间线节点组件
function TimelineNode({ 
  node, 
  onClick,
  isFrequent 
}: { 
  node: InteractionNode; 
  onClick: (node: InteractionNode) => void;
  isFrequent: boolean;
}) {
  const config = getNodeTypeConfig(node.interaction_type);
  const [isExpanded, setIsExpanded] = useState(false);
  
  return (
    <div 
      className="relative pl-8 pb-6 last:pb-0 group"
      onClick={() => onClick(node)}
    >
      {/* 时间线 */}
      <div className={`absolute left-3 top-0 bottom-0 w-0.5 ${config.bgColor}`}>
        <div className={`absolute top-4 left-1/2 -translate-x-1/2 w-3 h-3 rounded-full ${config.bgColor} ${config.borderColor} border-2 group-hover:scale-125 transition-transform`} />
      </div>
      
      {/* 卡片 */}
      <div 
        className={`
          p-4 rounded-lg border-2 cursor-pointer transition-all
          ${config.bgColor} ${config.borderColor}
          hover:shadow-md hover:border-opacity-100
          ${isFrequent ? 'ring-2 ring-yellow-400 ring-offset-1' : ''}
        `}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Avatar.Root className="w-8 h-8 rounded-full bg-white flex items-center justify-center text-lg shadow-sm">
              <Avatar.Fallback>{node.agent_avatar}</Avatar.Fallback>
            </Avatar.Root>
            <div>
              <div className="text-sm font-bold text-slate-800">{node.agent_name}</div>
              <div className="flex items-center gap-1 text-xs text-slate-500">
                <Clock size={10} />
                {new Date(node.created_at).toLocaleTimeString()}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isFrequent && (
              <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 text-xs rounded-full font-medium">
                🔥 高频
              </span>
            )}
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium bg-white ${config.color}`}>
              {config.icon} {config.label}
            </span>
          </div>
        </div>
        
        {/* 内容摘要 */}
        <p className={`text-sm text-slate-700 leading-relaxed ${isExpanded ? '' : 'line-clamp-2'}`}>
          {node.content}
        </p>
        
        {/* 展开/收起提示 */}
        {node.content.length > 100 && (
          <div className="mt-2 text-xs text-slate-400 flex items-center gap-1">
            {isExpanded ? (
              <><ChevronDown size={12} /> 点击收起</>
            ) : (
              <><ChevronRight size={12} /> 点击展开</>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// 问答链节点组件
function ChainNode({ 
  node, 
  onClick, 
  depth = 0,
  frequentQuestionIds 
}: { 
  node: InteractionNode & { children?: InteractionNode[] }; 
  onClick: (node: InteractionNode) => void;
  depth?: number;
  frequentQuestionIds: Set<string>;
}) {
  const config = getNodeTypeConfig(node.interaction_type);
  const isFrequent = frequentQuestionIds.has(node.id);
  const hasChildren = node.children && node.children.length > 0;
  const [expanded, setExpanded] = useState(true);
  
  return (
    <div className="relative" style={{ marginLeft: depth > 0 ? '24px' : '0' }}>
      {/* 连接线 */}
      {depth > 0 && (
        <div className="absolute left-0 top-6 w-6 h-0.5 bg-slate-300" />
      )}
      
      {/* 节点卡片 */}
      <div 
        className={`
          relative mb-3 p-3 rounded-lg border-2 cursor-pointer transition-all
          bg-white hover:shadow-md
          ${config.borderColor}
          ${isFrequent ? 'ring-2 ring-yellow-400' : ''}
        `}
        onClick={() => onClick(node)}
      >
        <div className="flex items-center gap-3">
          {/* 展开按钮 */}
          {hasChildren && (
            <button 
              className="p-1 hover:bg-slate-100 rounded transition-colors"
              onClick={(e) => {
                e.stopPropagation();
                setExpanded(!expanded);
              }}
            >
              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
          )}
          
          {/* 头像 */}
          <Avatar.Root className={`w-10 h-10 rounded-full flex items-center justify-center text-lg ${config.bgColor}`}>
            <Avatar.Fallback>{node.agent_avatar}</Avatar.Fallback>
          </Avatar.Root>
          
          {/* 信息 */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-slate-800">{node.agent_name}</span>
              <span className={`text-xs px-1.5 py-0.5 rounded ${config.bgColor} ${config.color}`}>
                {config.label}
              </span>
              {isFrequent && (
                <span className="text-xs px-1.5 py-0.5 bg-yellow-100 text-yellow-700 rounded">
                  🔥 高频
                </span>
              )}
            </div>
            <p className="text-sm text-slate-600 truncate">
              {node.content.slice(0, 60)}{node.content.length > 60 ? '...' : ''}
            </p>
            <div className="text-xs text-slate-400 mt-1">
              {new Date(node.created_at).toLocaleString()}
            </div>
          </div>
        </div>
      </div>
      
      {/* 子节点 */}
      {hasChildren && expanded && (
        <div className="relative">
          {/* 垂直连接线 */}
          <div className="absolute left-3 top-0 bottom-3 w-0.5 bg-slate-200" />
          {node.children!.map(child => (
            <ChainNode 
              key={child.id} 
              node={child} 
              onClick={onClick}
              depth={depth + 1}
              frequentQuestionIds={frequentQuestionIds}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// 主组件
export function InteractionPathView({ sessionId, className = '' }: InteractionPathViewProps) {
  const [nodes, setNodes] = useState<InteractionNode[]>([]);
  const [statistics, setStatistics] = useState<InteractionStatistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('timeline');
  const [selectedNode, setSelectedNode] = useState<InteractionNode | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [showFrequentOnly, setShowFrequentOnly] = useState(false);

  // 加载数据
  useEffect(() => {
    loadData();
  }, [sessionId]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchInteractionPath(sessionId);
      setNodes(data.nodes);
      setStatistics(data.statistics);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  // 计算高频问题ID集合
  const frequentQuestionIds = useMemo(() => {
    if (!statistics?.frequent_questions) return new Set<string>();
    const ids = new Set<string>();
    statistics.frequent_questions.forEach(fq => {
      fq.similarity_group.forEach(id => ids.add(id));
    });
    return ids;
  }, [statistics]);

  // 按时间线分组
  const timelineGroups = useMemo(() => groupByTimeline(nodes), [nodes]);

  // 树形结构
  const treeNodes = useMemo(() => buildTreeStructure(nodes), [nodes]);

  // 处理节点点击
  const handleNodeClick = (node: InteractionNode) => {
    setSelectedNode(node);
    setDialogOpen(true);
  };

  if (loading) {
    return (
      <div className={`flex items-center justify-center p-12 ${className}`}>
        <div className="text-center">
          <div className="w-10 h-10 mx-auto mb-3 border-4 border-blue-200 border-t-blue-500 rounded-full animate-spin" />
          <p className="text-slate-500 text-sm">加载互动路径数据...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`p-8 ${className}`}>
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <AlertCircle className="w-10 h-10 text-red-500 mx-auto mb-3" />
          <h3 className="text-lg font-bold text-red-800 mb-2">加载失败</h3>
          <p className="text-sm text-red-600 mb-4">{error}</p>
          <button 
            onClick={loadData}
            className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
          >
            重新加载
          </button>
        </div>
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className={`flex items-center justify-center p-12 ${className}`}>
        <div className="text-center text-slate-400">
          <MessageCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-sm">暂无互动数据</p>
          <p className="text-xs mt-1">教学开始后这里将显示问答路径</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex flex-col h-full ${className}`}>
      {/* 统计面板 */}
      {statistics && (
        <div className="p-4 border-b border-slate-200 bg-slate-50">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard 
              title="总互动数" 
              value={statistics.total_interactions} 
              icon={BarChart3}
              color="slate"
            />
            <StatCard 
              title="学生提问" 
              value={statistics.question_count} 
              icon={HelpCircle}
              color="blue"
              subtitle={`${statistics.frequent_questions.length} 个高频`}
            />
            <StatCard 
              title="教师回答" 
              value={statistics.answer_count} 
              icon={CheckCircle}
              color="emerald"
            />
            <StatCard 
              title="回答覆盖率" 
              value={`${statistics.qa_coverage}%`} 
              icon={TrendingUp}
              color="purple"
            />
          </div>
          
          {/* 高频问题提示 */}
          {statistics.frequent_questions.length > 0 && (
            <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="w-4 h-4 text-yellow-600" />
                <span className="text-sm font-medium text-yellow-800">高频问题</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {statistics.frequent_questions.map((fq, idx) => (
                  <span 
                    key={idx}
                    className="px-2 py-1 bg-yellow-100 text-yellow-700 text-xs rounded-full"
                    title={`出现 ${fq.count} 次`}
                  >
                    {fq.content} ({fq.count}次)
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 工具栏 */}
      <div className="flex items-center justify-between p-3 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewMode('timeline')}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
              ${viewMode === 'timeline' 
                ? 'bg-blue-500 text-white' 
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}
            `}
          >
            <AlignLeft size={16} />
            时间线
          </button>
          <button
            onClick={() => setViewMode('chain')}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
              ${viewMode === 'chain' 
                ? 'bg-blue-500 text-white' 
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}
            `}
          >
            <GitBranch size={16} />
            问答链
          </button>
        </div>
        
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-sm text-slate-600 cursor-pointer">
            <input 
              type="checkbox"
              checked={showFrequentOnly}
              onChange={(e) => setShowFrequentOnly(e.target.checked)}
              className="rounded border-slate-300"
            />
            仅看高频
          </label>
          <span className="text-xs text-slate-400">
            共 {nodes.length} 条记录
          </span>
        </div>
      </div>

      {/* 内容区域 */}
      <ScrollArea.Root className="flex-1 overflow-hidden">
        <ScrollArea.Viewport className="h-full">
          <div className="p-4">
            {viewMode === 'timeline' ? (
              // 时间线视图
              <div className="space-y-6">
                {timelineGroups.map(group => (
                  <div key={group.iteration} className="space-y-4">
                    <div className="flex items-center gap-3">
                      <div className="px-3 py-1 bg-blue-100 text-blue-700 text-sm font-bold rounded-full">
                        第 {group.iteration} 轮
                      </div>
                      <div className="flex-1 h-px bg-slate-200" />
                      <span className="text-xs text-slate-400">
                        {group.nodes.length} 条记录
                      </span>
                    </div>
                    <div className="space-y-2">
                      {group.nodes
                        .filter(n => !showFrequentOnly || frequentQuestionIds.has(n.id))
                        .map(node => (
                          <TimelineNode 
                            key={node.id} 
                            node={node} 
                            onClick={handleNodeClick}
                            isFrequent={frequentQuestionIds.has(node.id)}
                          />
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              // 问答链视图
              <div className="space-y-4">
                {treeNodes.length === 0 ? (
                  <div className="text-center py-8 text-slate-400">
                    <GitBranch className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p className="text-sm">暂无问答链数据</p>
                  </div>
                ) : (
                  treeNodes
                    .filter(n => !showFrequentOnly || frequentQuestionIds.has(n.id) || hasFrequentDescendant(n, frequentQuestionIds))
                    .map(node => (
                      <ChainNode 
                        key={node.id} 
                        node={node as InteractionNode & { children?: InteractionNode[] }} 
                        onClick={handleNodeClick}
                        frequentQuestionIds={frequentQuestionIds}
                      />
                    ))
                )}
              </div>
            )}
          </div>
        </ScrollArea.Viewport>
        <ScrollArea.Scrollbar className="w-2 bg-slate-100" orientation="vertical">
          <ScrollArea.Thumb className="bg-slate-300 rounded-full" />
        </ScrollArea.Scrollbar>
      </ScrollArea.Root>

      {/* 节点详情弹窗 */}
      <NodeDetailDialog 
        node={selectedNode}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        allNodes={nodes}
      />
    </div>
  );
}

// 辅助函数：检查节点是否有高频后代
function hasFrequentDescendant(node: InteractionNode & { children?: InteractionNode[] }, frequentIds: Set<string>): boolean {
  if (frequentIds.has(node.id)) return true;
  if (node.children) {
    return node.children.some(child => hasFrequentDescendant(child, frequentIds));
  }
  return false;
}

// 默认导出
export default InteractionPathView;
