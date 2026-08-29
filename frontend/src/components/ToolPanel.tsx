import type { Agent } from '../types';

interface ToolPanelProps {
  agent: Agent;
}

// Available tools in the system
const AVAILABLE_TOOLS = [
  { name: 'calculator', description: 'Execute mathematical calculations', category: 'computation' },
  { name: 'search', description: 'Search for information', category: 'search' },
  { name: 'code_executor', description: 'Execute Python code', category: 'code' },
  { name: 'text_processor', description: 'Process and transform text', category: 'data' },
  { name: 'current_time', description: 'Get current date and time', category: 'utility' },
];

export function ToolPanel({ agent }: ToolPanelProps) {
  const enabledTools = new Set(agent.tools);

  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'computation': return 'text-blue-400';
      case 'search': return 'text-green-400';
      case 'code': return 'text-purple-400';
      case 'data': return 'text-yellow-400';
      case 'utility': return 'text-gray-400';
      default: return 'text-gray-400';
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Tools</h3>
        <span className="text-sm text-gray-400">
          {enabledTools.size} / {AVAILABLE_TOOLS.length} enabled
        </span>
      </div>

      {/* Tool List */}
      <div className="space-y-2">
        {AVAILABLE_TOOLS.map(tool => {
          const isEnabled = enabledTools.has(tool.name);

          return (
            <div
              key={tool.name}
              className={`
                flex items-center justify-between p-3 rounded-lg transition-colors
                ${isEnabled ? 'bg-gray-700' : 'bg-gray-800 opacity-60'}
              `}
            >
              <div className="flex items-center gap-3">
                <span className={`text-lg ${
                  isEnabled ? 'opacity-100' : 'opacity-40'
                }`}>
                  {tool.category === 'computation' && '🔢'}
                  {tool.category === 'search' && '🔍'}
                  {tool.category === 'code' && '💻'}
                  {tool.category === 'data' && '📊'}
                  {tool.category === 'utility' && '⚙️'}
                </span>
                <div>
                  <p className={`font-medium ${isEnabled ? '' : 'line-through'}`}>
                    {tool.name}
                  </p>
                  <p className={`text-xs ${getCategoryColor(tool.category)}`}>
                    {tool.description}
                  </p>
                </div>
              </div>
              <span className={`text-xs px-2 py-1 rounded ${
                isEnabled ? 'bg-green-600' : 'bg-gray-600'
              }`}>
                {isEnabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
          );
        })}
      </div>

      {/* Note */}
      <p className="text-xs text-gray-500 pt-2 border-t border-gray-700">
        Tool permissions can be configured when creating or editing an agent.
      </p>
    </div>
  );
}
