import { Bot, User } from 'lucide-react'
import ChatMessageContent from './ChatMessageContent'

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  isTyping?: boolean
  imageUrl?: string
}

function TypingIndicator() {
  return (
    <span className="typing-dots" aria-label="يكتب...">
      <span /><span /><span />
    </span>
  )
}

export default function MessageBubble({ role, content, isTyping, imageUrl }: MessageBubbleProps) {
  const isUser = role === 'user'

  return (
    <div className={`flex gap-2.5 fade-in ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className="shrink-0 w-9 h-9 rounded-full flex items-center justify-center shadow-sm"
        style={{
          background: isUser ? 'var(--color-brand-accent)' : 'var(--color-brand-primary)',
          color: 'white',
        }}
      >
        {isUser ? <User size={17} /> : <Bot size={17} />}
      </div>
      <div
        className={`message-bubble max-w-[min(80%,520px)] px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm ${
          isUser
            ? 'bg-[var(--color-brand-primary)] text-white rounded-tr-md'
            : 'bg-white border border-[var(--color-border-default)] rounded-tl-md'
        }`}
        dir="auto"
      >
        {isTyping && !content ? (
          <TypingIndicator />
        ) : (
          <>
            {imageUrl && (
              <img
                src={imageUrl}
                alt=""
                className="chat-message-image mb-2 rounded-lg max-w-full max-h-48 object-contain"
              />
            )}
            {content ? <ChatMessageContent content={content} isUser={isUser} /> : null}
          </>
        )}
      </div>
    </div>
  )
}
