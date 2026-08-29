import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import type { Agent } from '../types';
import { useMessageStore } from '../stores/messageStore';
import { useWebSocket } from '../hooks/useWebSocket';
import { MessageBubble } from './MessageBubble';
import { Search, Download, X, ChevronDown, ChevronUp, Sparkles } from 'lucide-react';

interface ChatWindowProps {
  agent: Agent;
}

// 快捷回复模板
const QUICK_REPLIES = [
  '你好，请介绍一下自己',
  '你能帮我做什么？',
  '请总结一下上面的内容',
  '有什么建议吗？',
  '谢谢你的帮助！',
];

export function ChatWindow({ agent }: ChatWindowProps) {
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showQuickReplies, setShowQuickReplies] = useState(false);
  const [currentSearchIndex, setCurrentSearchIndex] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const { filteredMessages, searchMessages, exportMessages, clearSearch, addMessage } = useMessageStore();
  const { sendMessage } = useWebSocket(agent.id);

  // 过滤当前 Agent 的消息
  const agentMessages = useMemo(() => {
    return filteredMessages.filter(
      m => m.from_agent === agent.name || m.to === agent.name
    );
  }, [filteredMessages, agent.name]);

  // 搜索匹配的消息
  const searchResults = useMemo(() => {
    if (!searchQuery) return [];
    return agentMessages.filter(m =>
      JSON.stringify(m.content).toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [agentMessages, searchQuery]);

  // Auto-scroll
  useEffect(() => {
    if (isAtBottom && !searchQuery) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [agentMessages, isAtBottom, searchQuery]);

  const handleScroll = useCallback(() => {
    if (!messagesContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
    const atBottom = scrollHeight - scrollTop - clientHeight < 100;
    setIsAtBottom(atBottom);
  }, []);

  // 搜索功能
  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query);
    searchMessages(query);
    setCurrentSearchIndex(0);
  }, [searchMessages]);

  const navigateSearch = useCallback((direction: 'up' | 'down') => {
    if (searchResults.length === 0) return;
    const newIndex = direction === 'up'
      ? Math.max(0, currentSearchIndex - 1)
      : Math.min(searchResults.length - 1, currentSearchIndex + 1);
    setCurrentSearchIndex(newIndex);
    // Scroll to result
    const resultElement = document.getElementById(`msg-${searchResults[newIndex]?.id}`);
    resultElement?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [searchResults, currentSearchIndex]);

  // 导出功能
  const handleExport = useCallback((format: 'markdown' | 'json') => {
    const content = exportMessages(format);
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat-with-${agent.name}-${new Date().toISOString().split('T')[0]}.${format === 'json' ? 'json' : 'md'}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [exportMessages, agent.name]);

  // 快捷回复
  const handleQuickReply = useCallback((text: string) => {
    setInput(text);
    setShowQuickReplies(false);
  }, []);

  const cleanResponse = useCallback((text: string): string => {
    if (!text) return '';
    return text
      .replace(/<think>[\s\S]*?<\/think>/g, '')
      .replace(/^###.*$/gm, '')
      .replace(/^##.*$/gm, '')
      .replace(/^\*\*.*\*\*$/gm, '')
      .replace(/^→.*$/gm, '')
      .replace(/^▸.*$/gm, '')
      .replace(/^░.*$/gm, '')
      .replace(/^█.*$/gm, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }, []);

  const handleSend = useCallback(async () => {
    if (!input.trim() || sending) return;

    setSending(true);
    const prompt = input.trim();
    const userMsgId = Date.now().toString();

    addMessage({
      id: userMsgId,
      msg_type: 'chat',
      priority: 'P2',
      from_agent: 'user',
      to: agent.name,
      content: { prompt },
      deadline: 'immediate',
      created_at: new Date().toISOString(),
    });

    setInput('');

    try {
      sendMessage({
        msg_type: 'chat',
        to: agent.name,
        content: { prompt },
        priority: 'P2',
      });

      const res = await fetch(`/api/agents/${agent.id}/think`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });

      if (res.ok) {
        const data = await res.json();
        const cleanText = cleanResponse(data.response);
        addMessage({
          id: (Date.now() + 1).toString(),
          msg_type: 'chat',
          priority: 'P2',
          from_agent: agent.name,
          to: 'user',
          content: { response: cleanText },
          deadline: 'immediate',
          created_at: new Date().toISOString(),
        });
      }
    } catch (err) {
      console.error('Failed to send message:', err);
    } finally {
      setSending(false);
      // 发送完成后聚焦输入框
      setTimeout(() => textareaRef.current?.focus(), 100);
    }
  }, [input, sending, agent.id, agent.name, addMessage, sendMessage, cleanResponse]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-gradient-to-br from-slate-50 to-blue-50">
      {/* Header */}
      <div className="flex-shrink-0 flex items-center gap-3 py-3 px-4 border-b border-slate-200 bg-white/80 backdrop-blur-sm">
        <span className="text-3xl">{agent.avatar}</span>
        <div className="flex-1 min-w-0">
          <h2 className="font-semibold text-lg truncate text-slate-800">{agent.name}</h2>
          <p className="text-sm text-slate-500 truncate">{agent.description}</p>
        </div>
        
        {/* 搜索按钮 */}
        <button
          onClick={() => {
            setShowSearch(!showSearch);
            if (!showSearch) {
              setTimeout(() => searchInputRef.current?.focus(), 100);
            } else {
              clearSearch();
              setSearchQuery('');
            }
          }}
          className={`p-2 rounded-lg transition-colors ${showSearch ? 'bg-blue-100 text-blue-600' : 'hover:bg-slate-100 text-slate-500'}`}
          title="搜索消息"
        >
          <Search className="w-5 h-5" />
        </button>

        {/* 导出按钮 */}
        <div className="relative group">
          <button
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 transition-colors"
            title="导出聊天记录"
          >
            <Download className="w-5 h-5" />
          </button>
          <div className="absolute right-0 top-full mt-1 hidden group-hover:block bg-white rounded-lg shadow-lg border border-slate-200 py-1 z-10 min-w-[120px]">
            <button
              onClick={() => handleExport('markdown')}
              className="w-full px-4 py-2 text-left text-sm hover:bg-slate-50 text-slate-700"
            >
              导出为 Markdown
            </button>
            <button
              onClick={() => handleExport('json')}
              className="w-full px-4 py-2 text-left text-sm hover:bg-slate-50 text-slate-700"
            >
              导出为 JSON
            </button>
          </div>
        </div>

        <span className={`px-3 py-1 text-xs rounded-full font-medium flex-shrink-0 ${
          agent.status === 'online' ? 'bg-emerald-100 text-emerald-700' :
          agent.status === 'busy' ? 'bg-amber-100 text-amber-700' : 'bg-slate-200 text-slate-600'
        }`}>
          {agent.status === 'online' ? '● 在线' : agent.status === 'busy' ? '◐ 忙碌' : '○ 离线'}
        </span>
      </div>

      {/* 搜索栏 */}
      {showSearch && (
        <div className="flex-shrink-0 px-4 py-2 bg-slate-50 border-b border-slate-200 flex items-center gap-2">
          <Search className="w-4 h-4 text-slate-400" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="搜索消息内容..."
            className="flex-1 bg-transparent border-none outline-none text-sm text-slate-700 placeholder-slate-400"
          />
          {searchQuery && (
            <>
              <span className="text-xs text-slate-500">
                {currentSearchIndex + 1} / {searchResults.length}
              </span>
              <button
                onClick={() => navigateSearch('up')}
                disabled={currentSearchIndex === 0}
                className="p-1 rounded hover:bg-slate-200 disabled:opacity-30"
              >
                <ChevronUp className="w-4 h-4" />
              </button>
              <button
                onClick={() => navigateSearch('down')}
                disabled={currentSearchIndex >= searchResults.length - 1}
                className="p-1 rounded hover:bg-slate-200 disabled:opacity-30"
              >
                <ChevronDown className="w-4 h-4" />
              </button>
              <button
                onClick={() => {
                  clearSearch();
                  setSearchQuery('');
                }}
                className="p-1 rounded hover:bg-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      )}

      {/* Messages */}
      <div
        ref={messagesContainerRef}
        className="flex-1 min-h-0 overflow-y-auto py-4 px-4 space-y-3 scroll-smooth"
        onScroll={handleScroll}
      >
        {agentMessages.length === 0 && (
          <div className="text-center text-slate-400 py-12">
            <div className="w-16 h-16 mx-auto mb-4 bg-slate-100 rounded-full flex items-center justify-center">
              <span className="text-3xl">💬</span>
            </div>
            <p className="text-lg mb-2 font-medium text-slate-600">开始与 {agent.name} 对话</p>
            <p className="text-sm">发送消息开始交流，或使用下方的快捷回复</p>
          </div>
        )}
        {agentMessages.map((message, index) => (
          <div
            key={message.id}
            id={`msg-${message.id}`}
            className={`animate-fadeIn ${searchResults[currentSearchIndex]?.id === message.id ? 'ring-2 ring-blue-400 rounded-lg' : ''}`}
            style={{ animationDelay: `${index * 50}ms` }}
          >
            <MessageBubble
              message={message}
              isOwn={message.from_agent === 'user'}
            />
          </div>
        ))}
        {sending && (
          <div className="flex justify-start animate-fadeIn">
            <div className="bg-white rounded-2xl rounded-bl-md px-4 py-3 shadow-sm border border-slate-100">
              <div className="flex items-center gap-2 text-slate-400">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span className="text-sm">思考中...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 快捷回复 */}
      {showQuickReplies && (
        <div className="flex-shrink-0 px-4 py-2 bg-slate-50 border-t border-slate-200">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="w-4 h-4 text-amber-500" />
            <span className="text-xs text-slate-500">快捷回复</span>
            <button
              onClick={() => setShowQuickReplies(false)}
              className="ml-auto text-slate-400 hover:text-slate-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {QUICK_REPLIES.map((text) => (
              <button
                key={text}
                onClick={() => handleQuickReply(text)}
                className="px-3 py-1.5 text-sm bg-white border border-slate-200 rounded-full hover:border-blue-300 hover:text-blue-600 transition-colors"
              >
                {text}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="flex-shrink-0 pt-3 pb-4 px-4 border-t border-slate-200 bg-white">
        {!showQuickReplies && (
          <button
            onClick={() => setShowQuickReplies(true)}
            className="mb-2 text-xs text-slate-400 hover:text-blue-500 flex items-center gap-1 transition-colors"
          >
            <Sparkles className="w-3 h-3" />
            显示快捷回复
          </button>
        )}
        <div className="flex gap-3">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`给 ${agent.name} 发送消息...`}
            className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 text-slate-700 placeholder-slate-400 transition-all"
            rows={2}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending}
            className="px-6 py-2 bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 disabled:bg-slate-300 disabled:cursor-not-allowed rounded-xl transition-all flex items-center gap-2 text-white font-medium shadow-lg shadow-blue-500/25 hover:shadow-xl hover:shadow-blue-500/30 disabled:shadow-none"
          >
            {sending ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span>发送中</span>
              </>
            ) : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}
