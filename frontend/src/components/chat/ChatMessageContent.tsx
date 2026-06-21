import ReactMarkdown from 'react-markdown'

interface ChatMessageContentProps {
  content: string
  isUser?: boolean
}

export default function ChatMessageContent({ content, isUser }: ChatMessageContentProps) {
  if (isUser) {
    return <span className="chat-plain">{content}</span>
  }

  return (
    <div className="chat-markdown">
      <ReactMarkdown
        components={{
          h2: ({ children }) => <h3 className="chat-md-h">{children}</h3>,
          h3: ({ children }) => <h4 className="chat-md-h chat-md-h-sub">{children}</h4>,
          p: ({ children }) => <p className="chat-md-p">{children}</p>,
          ul: ({ children }) => <ul className="chat-md-ul">{children}</ul>,
          ol: ({ children }) => <ol className="chat-md-ol">{children}</ol>,
          li: ({ children }) => <li className="chat-md-li">{children}</li>,
          strong: ({ children }) => <strong className="chat-md-strong">{children}</strong>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
