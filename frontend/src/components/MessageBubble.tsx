import type { Message } from '../types';

interface MessageBubbleProps {
  message: Message;
  isOwn: boolean;
}

export function MessageBubble({ message, isOwn }: MessageBubbleProps) {
  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const isUser = message.from_agent === 'user';
  const displayContent = message.content.prompt || message.content.response || message.content.text || '';

  return (
    <div className={`flex ${isOwn ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`
          max-w-[85%] rounded-2xl px-4 py-3
          ${isUser
            ? 'bg-blue-600 text-white rounded-br-md'
            : 'bg-gray-700 text-gray-100 rounded-bl-md'
          }
        `}
      >
        {/* Sender for agent messages */}
        {!isUser && (
          <p className="text-xs text-blue-400 mb-1 font-medium">{message.from_agent}</p>
        )}

        {/* Content */}
        <p className="text-sm whitespace-pre-wrap leading-relaxed">
          {displayContent}
        </p>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 mt-1">
          <span className={`text-xs ${isUser ? 'text-blue-200' : 'text-gray-400'}`}>
            {formatTime(message.created_at)}
          </span>
        </div>
      </div>
    </div>
  );
}
