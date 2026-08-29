import React, { useState } from 'react';
import { ThumbsUp, Lightbulb, ChevronDown, ChevronUp, MessageSquare } from 'lucide-react';

interface ParsedComment {
  dimension: string;
  advantages: string[];
  suggestions: string[];
  summary?: string;
}

interface SupervisorCommentCardProps {
  content: string;
  agentName: string;
  iteration: number;
  createdAt: string;
}

// 解析督导点评内容
const parseComment = (content: string): ParsedComment[] => {
  const comments: ParsedComment[] = [];
  
  // 按维度分割内容（支持【维度名】格式）
  const dimensionRegex = /【(.+?)】/g;
  const parts = content.split(dimensionRegex);
  
  for (let i = 1; i < parts.length; i += 2) {
    const dimension = parts[i].trim();
    const section = parts[i + 1] || '';
    
    const advantages: string[] = [];
    const suggestions: string[] = [];
    
    // 提取优点（支持"优点："、"✓"、"-"等格式）
    const advantageRegex = /(?:优点|优势|亮点)[：:]\s*([^\n]+(?:\n(?!(?:建议|不足|缺点)[：:]).*)*)/i;
    const advantageMatch = section.match(advantageRegex);
    if (advantageMatch) {
      const advantageText = advantageMatch[1];
      // 分割列表项
      const items = advantageText.split(/[\n;；]/).map(s => s.trim()).filter(s => s && !s.match(/^[\d一二三四五六七八九十]+[.、]/));
      advantages.push(...items.slice(0, 3)); // 最多取3条
    }
    
    // 提取建议（支持"建议："、"不足："、"改进："等格式）
    const suggestionRegex = /(?:建议|不足|缺点|改进)[：:]\s*([^\n]+(?:\n(?!(?:优点|优势|亮点)[：:]).*)*)/i;
    const suggestionMatch = section.match(suggestionRegex);
    if (suggestionMatch) {
      const suggestionText = suggestionMatch[1];
      // 分割列表项
      const items = suggestionText.split(/[\n;；]/).map(s => s.trim()).filter(s => s && !s.match(/^[\d一二三四五六七八九十]+[.、]/));
      suggestions.push(...items.slice(0, 3)); // 最多取3条
    }
    
    // 如果没匹配到结构化内容，尝试按行分割
    if (advantages.length === 0 && suggestions.length === 0) {
      const lines = section.split('\n').map(l => l.trim()).filter(l => l.length > 5);
      const midPoint = Math.ceil(lines.length / 2);
      advantages.push(...lines.slice(0, midPoint).slice(0, 2));
      suggestions.push(...lines.slice(midPoint).slice(0, 2));
    }
    
    comments.push({
      dimension: dimension.replace('点评', '').trim(),
      advantages: advantages.length > 0 ? advantages : ['内容充实，结构完整'],
      suggestions: suggestions.length > 0 ? suggestions : ['建议进一步优化细节'],
    });
  }
  
  // 如果没有解析到任何维度，作为整体处理
  if (comments.length === 0) {
    const lines = content.split('\n').map(l => l.trim()).filter(l => l.length > 5);
    const midPoint = Math.ceil(lines.length / 2);
    comments.push({
      dimension: '综合评价',
      advantages: lines.slice(0, midPoint).slice(0, 3),
      suggestions: lines.slice(midPoint).slice(0, 3),
    });
  }
  
  return comments;
};

// 获取维度颜色
const getDimensionColor = (dimension: string) => {
  const colorMap: Record<string, { bg: string; border: string; icon: string }> = {
    '教学设计': { bg: 'bg-blue-50', border: 'border-blue-400', icon: '📐' },
    '讲授方式': { bg: 'bg-emerald-50', border: 'border-emerald-400', icon: '🎤' },
    '回答质量': { bg: 'bg-purple-50', border: 'border-purple-400', icon: '💬' },
    '综合评价': { bg: 'bg-orange-50', border: 'border-orange-400', icon: '📊' },
  };
  return colorMap[dimension] || { bg: 'bg-gray-50', border: 'border-gray-400', icon: '📝' };
};

export const SupervisorCommentCard: React.FC<SupervisorCommentCardProps> = ({
  content,
  agentName,
  iteration,
  createdAt,
}) => {
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set([0]));
  const parsedComments = parseComment(content);
  
  const toggleSection = (index: number) => {
    const newSet = new Set(expandedSections);
    if (newSet.has(index)) {
      newSet.delete(index);
    } else {
      newSet.add(index);
    }
    setExpandedSections(newSet);
  };
  
  return (
    <div className="space-y-3">
      {parsedComments.map((comment, index) => {
        const colors = getDimensionColor(comment.dimension);
        const isExpanded = expandedSections.has(index);
        
        return (
          <div
            key={index}
            className={`rounded-lg border-2 ${colors.border} overflow-hidden transition-all duration-200`}
          >
            {/* 维度标题 - 可点击展开/收起 */}
            <button
              onClick={() => toggleSection(index)}
              className={`w-full px-3 py-2 ${colors.bg} flex items-center justify-between hover:opacity-80 transition-opacity`}
            >
              <div className="flex items-center gap-2">
                <span className="text-lg">{colors.icon}</span>
                <span className="font-bold text-gray-800 text-sm">{comment.dimension}</span>
                <span className="text-xs text-gray-500 ml-2">
                  {comment.advantages.length}优点 {comment.suggestions.length}建议
                </span>
              </div>
              {isExpanded ? (
                <ChevronUp className="w-4 h-4 text-gray-600" />
              ) : (
                <ChevronDown className="w-4 h-4 text-gray-600" />
              )}
            </button>
            
            {/* 展开的内容 */}
            {isExpanded && (
              <div className="p-3 space-y-3 bg-white">
                {/* 优点区域 */}
                <div className="bg-green-50 rounded-lg p-3 border border-green-200">
                  <div className="flex items-center gap-2 mb-2">
                    <ThumbsUp className="w-4 h-4 text-green-600" />
                    <span className="font-semibold text-green-800 text-sm">优点</span>
                  </div>
                  <ul className="space-y-1.5">
                    {comment.advantages.map((adv, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-gray-700">
                        <span className="text-green-500 mt-0.5">✓</span>
                        <span className="flex-1 leading-relaxed">{adv}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                
                {/* 建议区域 */}
                <div className="bg-amber-50 rounded-lg p-3 border border-amber-200">
                  <div className="flex items-center gap-2 mb-2">
                    <Lightbulb className="w-4 h-4 text-amber-600" />
                    <span className="font-semibold text-amber-800 text-sm">改进建议</span>
                  </div>
                  <ul className="space-y-1.5">
                    {comment.suggestions.map((sug, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-gray-700">
                        <span className="text-amber-500 mt-0.5">💡</span>
                        <span className="flex-1 leading-relaxed">{sug}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
            
            {/* 收起时显示摘要 */}
            {!isExpanded && (
              <div className="px-3 py-2 bg-gray-50 text-xs text-gray-600 flex items-center gap-2">
                <MessageSquare className="w-3 h-3" />
                <span className="truncate">
                  {comment.advantages[0] || '点击展开查看详细点评'}
                </span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default SupervisorCommentCard;
