import React, { useState } from 'react';
import { ChevronDown, ChevronUp, BookOpen } from 'lucide-react';

interface TeacherLectureCardProps {
  content: string;
  iteration: number;
  isOptimized?: boolean;
}

// 解析并格式化讲授内容为连贯文章
const formatLectureContent = (content: string): React.ReactNode => {
  // 移除【模块名】标记，保留内容
  const cleanContent = content
    .replace(/【[^】]+】/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  
  const paragraphs = cleanContent.split('\n\n').filter(p => p.trim());
  
  return paragraphs.map((para, idx) => {
    const trimmed = para.trim();
    
    // 处理大标题（以-开头且较短的行）
    if (trimmed.match(/^[-\*]\s*[^：:]+$/) && trimmed.length < 30) {
      return (
        <h4 key={idx} className="text-base font-bold text-gray-800 mt-5 mb-3 flex items-center gap-2">
          <span className="w-1 h-5 bg-blue-500 rounded-full"></span>
          {trimmed.replace(/^[-\*]\s*/, '')}
        </h4>
      );
    }
    
    // 处理小标题（带冒号的短句）
    if (trimmed.match(/^[^：]{2,20}：/) && trimmed.length < 50) {
      const [title, ...rest] = trimmed.split('：');
      return (
        <div key={idx} className="mt-4 mb-2">
          <h5 className="text-sm font-bold text-gray-700">{title}</h5>
          {rest.length > 0 && (
            <p className="text-sm text-gray-600 mt-1 leading-relaxed">{rest.join('：')}</p>
          )}
        </div>
      );
    }
    
    // 处理列表项
    if (trimmed.match(/^[-\*•]\s/)) {
      return (
        <li key={idx} className="flex items-start gap-2 text-sm text-gray-700 mb-2 ml-4">
          <span className="text-blue-500 mt-1.5 text-xs">●</span>
          <span className="flex-1 leading-relaxed">{trimmed.replace(/^[-\*•]\s*/, '')}</span>
        </li>
      );
    }
    
    // 处理数字列表
    if (trimmed.match(/^\d+[.、]\s/)) {
      return (
        <li key={idx} className="flex items-start gap-2 text-sm text-gray-700 mb-2 ml-4">
          <span className="text-blue-500 font-medium mt-0.5 min-w-[20px]">
            {trimmed.match(/^(\d+)/)?.[1]}.
          </span>
          <span className="flex-1 leading-relaxed">{trimmed.replace(/^\d+[.、]\s*/, '')}</span>
        </li>
      );
    }
    
    // 处理加粗文本 **text**
    if (trimmed.includes('**')) {
      const parts = trimmed.split(/\*\*(.+?)\*\*/g);
      return (
        <p key={idx} className="text-sm text-gray-700 mb-3 leading-relaxed text-justify">
          {parts.map((part, pidx) => 
            pidx % 2 === 1 ? (
              <strong key={pidx} className="font-bold text-gray-900">{part}</strong>
            ) : (
              part
            )
          )}
        </p>
      );
    }
    
    // 普通段落
    return (
      <p key={idx} className="text-sm text-gray-700 mb-3 leading-relaxed text-justify indent-8">
        {trimmed}
      </p>
    );
  });
};

export const TeacherLectureCard: React.FC<TeacherLectureCardProps> = ({
  content,
  iteration,
  isOptimized = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  
  return (
    <div className={`rounded-xl border-2 shadow-md overflow-hidden transition-all duration-300 ${
      isOptimized 
        ? 'bg-gradient-to-br from-amber-50 to-white border-amber-300' 
        : 'bg-white border-blue-200'
    }`}>
      {/* 卡片头部 */}
      <div className={`px-5 py-3.5 flex items-center justify-between ${
        isOptimized 
          ? 'bg-gradient-to-r from-amber-400 to-amber-500' 
          : 'bg-gradient-to-r from-blue-500 to-blue-600'
      }`}>
        <div className="flex items-center gap-3">
          <BookOpen className={`w-5 h-5 ${isOptimized ? 'text-amber-900' : 'text-white'}`} />
          <div>
            <span className={`font-bold text-base ${isOptimized ? 'text-amber-900' : 'text-white'}`}>
              讲课内容
            </span>
            {isOptimized && (
              <span className="ml-2 px-2 py-0.5 bg-amber-100 text-amber-800 text-xs rounded-full font-medium">
                优化版
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs ${isOptimized ? 'text-amber-800' : 'text-blue-100'}`}>
            第 {iteration} 轮
          </span>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className={`p-1.5 rounded-full transition-colors ${
              isOptimized 
                ? 'hover:bg-amber-600 text-amber-900' 
                : 'hover:bg-blue-600 text-white'
            }`}
          >
            {isExpanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>
      
      {/* 内容区域 */}
      {isExpanded && (
        <div className="p-5 bg-white">
          <div className="prose prose-sm max-w-none">
            {formatLectureContent(content)}
          </div>
        </div>
      )}
      
      {/* 收起时显示摘要 */}
      {!isExpanded && (
        <div className="px-5 py-4 bg-gray-50">
          <p className="text-sm text-gray-500 leading-relaxed line-clamp-3">
            {content.slice(0, 150).replace(/【[^】]+】/g, '')}...
          </p>
        </div>
      )}
      
      {/* 底部信息 */}
      <div className={`px-5 py-2 border-t flex items-center justify-between text-xs ${
        isOptimized 
          ? 'bg-amber-50 border-amber-200 text-amber-700' 
          : 'bg-gray-50 border-gray-200 text-gray-500'
      }`}>
        <span>{content.length} 字符</span>
        <span>{isExpanded ? '点击收起' : '点击展开查看完整内容'}</span>
      </div>
    </div>
  );
};

export default TeacherLectureCard;
