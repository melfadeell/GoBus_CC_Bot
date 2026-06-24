import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { runtimeHotline } from '@/api/client'

interface ChatMessageContentProps {
  content: string
  isUser?: boolean
}

/** Always render the GoBus hotline number in bold, collapsing any existing bold.
 *  Uses the runtime (admin-configured) hotline value. */
function emphasizeHotline(md: string): string {
  const h = (runtimeHotline || '19567').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return md.replace(new RegExp(`\\*{0,2}\\b${h}\\b\\*{0,2}`, 'g'), `**${runtimeHotline}**`)
}

export default function ChatMessageContent({ content, isUser }: ChatMessageContentProps) {
  if (isUser) {
    return <span className="chat-plain">{content}</span>
  }

  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h2: ({ children }) => <h3 className="chat-md-h">{children}</h3>,
          h3: ({ children }) => <h4 className="chat-md-h chat-md-h-sub">{children}</h4>,
          p: ({ children }) => <p className="chat-md-p">{children}</p>,
          ul: ({ children }) => <ul className="chat-md-ul">{children}</ul>,
          ol: ({ children }) => <ol className="chat-md-ol">{children}</ol>,
          li: ({ children }) => <li className="chat-md-li">{children}</li>,
          strong: ({ children }) => <strong className="chat-md-strong">{children}</strong>,
          a: ({ href, children }) => (
            <a className="chat-md-link" href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="chat-md-table-wrap">
              <table className="chat-md-table">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="chat-md-thead">{children}</thead>,
          th: ({ children }) => <th className="chat-md-th">{children}</th>,
          td: ({ children }) => <td className="chat-md-td">{children}</td>,
        }}
      >
        {emphasizeHotline(content)}
      </ReactMarkdown>
    </div>
  )
}
