import { useState, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy } from 'lucide-react';

/** 从 pre > code 的 React 子树中提取纯文本，供复制按钮使用。 */
function extractText(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(extractText).join('');
  if (node && typeof node === 'object' && 'props' in node) {
    return extractText((node as { props?: { children?: ReactNode } }).props?.children);
  }
  return '';
}

function PreWithCopy({ children, ...rest }: React.HTMLAttributes<HTMLPreElement>) {
  const [copied, setCopied] = useState(false);
  const code = extractText(children);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 剪贴板不可用时忽略，代码仍可手动选择 */
    }
  };
  return (
    <div className="code-block">
      <pre {...rest}>{children}</pre>
      {code.trim() && (<button type="button" className="code-copy" onClick={() => void copy()} title="复制代码" aria-label="复制代码">{copied ? <Check size={11} /> : <Copy size={11} />}</button>)}
    </div>
  );
}

/** 渲染智能体产出的 Markdown。讲授稿常含标题、列表、表格和代码示例，纯文本展示可读性差。 */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ pre: PreWithCopy }}>{children}</ReactMarkdown>
    </div>
  );
}
