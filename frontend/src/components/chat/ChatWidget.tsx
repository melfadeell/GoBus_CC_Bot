import { useCallback, useEffect, useRef, useState } from 'react'
import { ImagePlus, MessageSquareText, Send, Sparkles, Square, X } from 'lucide-react'
import { CHAT_CHANNELS } from '@/api/client'
import LanguageToggle from '@/components/layout/LanguageToggle'
import {
  ocrImage,
  uploadChatImage,
  useChatStream,
  validateImageFile,
  type StationCardData,
  type TripRow,
} from '@/hooks/useChatStream'
import { useLanguage } from '@/i18n/LanguageProvider'
import MessageBubble from './MessageBubble'

const SESSION_KEY = 'gobus_chat_session'
const CHANNEL_KEY = 'gobus_chat_channel'

function resolveChannel(): string {
  const stored = sessionStorage.getItem(CHANNEL_KEY)
  if (stored && (CHAT_CHANNELS as readonly string[]).includes(stored)) return stored
  return 'website'
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  imageUrl?: string
  sql?: string
  ttftMs?: number
  stations?: StationCardData[]
  destinations?: string[]
  trips?: TripRow[]
}

interface PendingImage {
  file: File
  previewUrl: string
}

interface ChatWidgetProps {
  fullPage?: boolean
}

export default function ChatWidget({ fullPage = false }: ChatWidgetProps) {
  const { t, locale } = useLanguage()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [hotline] = useState('19567')
  const [error, setError] = useState<string | null>(null)
  const [initialized, setInitialized] = useState(false)
  const [pendingImage, setPendingImage] = useState<PendingImage | null>(null)
  const [readingImage, setReadingImage] = useState(false)
  const [channel, setChannel] = useState(resolveChannel)
  const sessionRef = useRef<string | null>(sessionStorage.getItem(SESSION_KEY))
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const hasUserSentRef = useRef(false)
  const { sendMessage, isStreaming, cancel } = useChatStream()

  const greeting = t.chat.greeting

  useEffect(() => {
    if (!hasUserSentRef.current) {
      setMessages([{ id: 'greeting', role: 'assistant', content: greeting }])
      setInitialized(true)
    }
  }, [greeting, locale])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming, pendingImage, readingImage])

  useEffect(() => {
    return () => {
      if (pendingImage?.previewUrl) URL.revokeObjectURL(pendingImage.previewUrl)
    }
  }, [pendingImage])

  const clearPendingImage = useCallback(() => {
    setPendingImage((prev) => {
      if (prev?.previewUrl) URL.revokeObjectURL(prev.previewUrl)
      return null
    })
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [])

  function handleImageSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    const validationKey = validateImageFile(file)
    if (validationKey) {
      setError(t.chat[validationKey as keyof typeof t.chat] as string)
      e.target.value = ''
      return
    }

    setError(null)
    clearPendingImage()
    setPendingImage({ file, previewUrl: URL.createObjectURL(file) })
  }

  const submit = useCallback(
    async (text: string, image?: PendingImage) => {
      const trimmed = text.trim()
      const hasImage = Boolean(image)
      if ((!trimmed && !hasImage) || isStreaming || readingImage) return

      hasUserSentRef.current = true
      setError(null)
      setInput('')

      const displayText = trimmed || (hasImage ? t.chat.imageOnlyMessage : '')
      const apiMessage = trimmed || (hasImage ? t.chat.imageOnlyMessage : '')
      const imageUrl = image?.previewUrl
      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: 'user',
        content: displayText,
        imageUrl,
      }
      const assistantId = `a-${Date.now()}`
      setMessages((prev) => [...prev, userMsg, { id: assistantId, role: 'assistant', content: '' }])

      let ocrText: string | undefined
      let persistedImageUrl: string | undefined
      if (image) {
        setReadingImage(true)
        try {
          persistedImageUrl = await uploadChatImage(image.file)
          ocrText = await ocrImage(image.file)
        } catch (err) {
          setError((err as Error).message || t.chat.ocrFailed)
          ocrText = ''
          setMessages((prev) => prev.filter((m) => m.id !== userMsg.id && m.id !== assistantId))
          return
        } finally {
          setReadingImage(false)
          setPendingImage(null)
          if (fileInputRef.current) fileInputRef.current.value = ''
        }
      }

      if (persistedImageUrl) {
        setMessages((prev) =>
          prev.map((m) => (m.id === userMsg.id ? { ...m, imageUrl: persistedImageUrl } : m))
        )
      }

      await sendMessage(apiMessage, sessionRef.current, {
        onSession: (sid) => {
          sessionRef.current = sid
          sessionStorage.setItem(SESSION_KEY, sid)
        },
        onToken: (token) => {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + token } : m))
          )
        },
        onMeta: (meta) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    sql: meta.sql ?? m.sql,
                    ttftMs: meta.ttft_ms ?? m.ttftMs,
                    stations: meta.stations ?? m.stations,
                    destinations: meta.destinations ?? m.destinations,
                    trips: meta.trips ?? m.trips,
                  }
                : m
            )
          )
        },
        onError: (msg) => {
          setError(msg)
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content || t.chat.errorFallback }
                : m
            )
          )
        },
      }, { ocrText: hasImage ? (ocrText ?? '') : undefined, imageUrl: persistedImageUrl, channel })
    },
    [isStreaming, readingImage, sendMessage, t.chat, clearPendingImage, channel]
  )

  function handleSubmit() {
    submit(input, pendingImage ?? undefined)
  }

  function newChat() {
    cancel()
    sessionRef.current = null
    sessionStorage.removeItem(SESSION_KEY)
    hasUserSentRef.current = false
    setError(null)
    setMessages((prev) => {
      prev.forEach((m) => {
        if (m.imageUrl) URL.revokeObjectURL(m.imageUrl)
      })
      return [{ id: 'greeting', role: 'assistant', content: greeting }]
    })
    clearPendingImage()
  }

  // In full-page mode the demo prompts live in the left sidebar, so don't
  // duplicate them inline on the first screen.
  const showPrompts = initialized && messages.length <= 1 && !isStreaming && !fullPage
  const demoPrompts = locale === 'ar' ? t.chat.promptsAr : t.chat.promptsEn
  const canSend = (input.trim() || pendingImage) && !isStreaming && !readingImage && initialized

  const channelLabel = (ch: string) => {
    const key = ch as keyof typeof t.dashboard.channels
    return t.dashboard.channels[key] ?? ch
  }

  const panel = (
    <div
      className={`flex flex-col overflow-hidden ${
        fullPage
          ? 'flex-1 min-w-0 h-dvh bg-[var(--color-surface-default)]'
          : 'card h-[620px] max-w-2xl mx-auto shadow-md'
      }`}
    >
      <div
        className="px-3 sm:px-4 py-3 sm:py-3.5 flex items-center justify-between gap-2 shrink-0"
        style={{ background: 'var(--color-brand-primary)', color: 'white' }}
      >
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <img src="/gobus_logo.jpg" alt="GoBus" className="h-8 w-8 sm:h-9 sm:w-9 rounded-full ring-2 ring-white/30 object-cover bg-white shrink-0" />
          <div className="min-w-0">
            <div className="font-bold text-sm truncate">{t.chat.title}</div>
            <div className="text-xs opacity-85 truncate">{t.common.hotline}: {hotline}</div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          <select
            className="chat-channel-select"
            value={channel}
            onChange={(e) => {
              setChannel(e.target.value)
              sessionStorage.setItem(CHANNEL_KEY, e.target.value)
            }}
            title={t.chat.channel}
            disabled={isStreaming}
          >
            {CHAT_CHANNELS.map((ch) => (
              <option key={ch} value={ch} className="text-[var(--color-text-default)]">
                {channelLabel(ch)}
              </option>
            ))}
          </select>
          <LanguageToggle className="inline-flex" onDark />
          <button
            type="button"
            className="btn-ghost text-white border-white/25 text-xs hover:bg-white/10"
            onClick={newChat}
          >
            {t.chat.newChat}
          </button>
        </div>
      </div>

      <div className={`flex-1 overflow-y-auto p-4 space-y-4 bg-[var(--color-surface-muted)] ${fullPage ? 'px-4 sm:px-6 md:px-8' : ''}`}>
        {!initialized ? (
          <LoadingPlaceholder />
        ) : (
          <>
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                role={msg.role}
                content={msg.content}
                imageUrl={msg.imageUrl}
                sql={msg.sql}
                ttftMs={msg.ttftMs}
                stations={msg.stations}
                destinations={msg.destinations}
                trips={msg.trips}
                isTyping={isStreaming && msg.role === 'assistant' && !msg.content}
              />
            ))}

            {readingImage && (
              <div className="text-sm text-[var(--color-text-muted)] fade-in">{t.chat.readingImage}</div>
            )}

            {showPrompts && (
              <div className="pt-2">
                <div className="text-xs font-medium text-[var(--color-text-muted)] mb-2">{t.chat.demoScenarios}</div>
                <div className={`flex flex-wrap gap-2 ${fullPage ? '' : 'max-h-40 overflow-y-auto'}`}>
                  {demoPrompts.map((prompt) => (
                    <button key={prompt} type="button" className="prompt-chip" onClick={() => submit(prompt)}>
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {error && <div className="alert-error text-sm">{error}</div>}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <div className={`border-t bg-white shrink-0 ${fullPage ? 'px-4 sm:px-6 md:px-8' : ''}`}>
        {pendingImage && (
          <div className="px-3 pt-3 flex items-start gap-2">
            <div className="relative shrink-0">
              <img
                src={pendingImage.previewUrl}
                alt=""
                className="h-16 w-16 rounded-lg object-cover border border-[var(--color-border-default)]"
              />
              <button
                type="button"
                className="absolute -top-2 -end-2 p-0.5 rounded-full bg-white border border-[var(--color-border-default)] shadow-sm hover:bg-[var(--color-surface-muted)]"
                onClick={clearPendingImage}
                title={t.chat.removeImage}
              >
                <X size={12} />
              </button>
            </div>
          </div>
        )}

        <div className="p-3 flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="hidden"
            onChange={handleImageSelect}
          />
          <button
            type="button"
            className="btn-ghost px-3 shrink-0"
            onClick={() => fileInputRef.current?.click()}
            disabled={isStreaming || readingImage || !initialized}
            title={t.chat.attachImage}
          >
            <ImagePlus size={18} />
          </button>
          <input
            className="input-field flex-1"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && canSend && handleSubmit()}
            placeholder={t.chat.placeholder}
            dir="auto"
            disabled={isStreaming || readingImage || !initialized}
          />
          {isStreaming ? (
            <button type="button" className="btn-ghost px-3" onClick={cancel} title="Stop">
              <Square size={16} />
            </button>
          ) : (
            <button
              type="button"
              className="btn-accent flex items-center gap-1 px-4"
              onClick={handleSubmit}
              disabled={!canSend}
            >
              <Send size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  )

  if (!fullPage) return panel

  return (
    <div className="flex h-dvh w-full">
      <aside className="demo-sidebar hidden md:flex flex-col w-72 shrink-0 overflow-y-auto">
        <div className="demo-sidebar-header">
          <div className="flex items-center gap-2">
            <span className="demo-sidebar-icon">
              <Sparkles size={15} />
            </span>
            <span className="demo-sidebar-title">{t.chat.demoScenarios}</span>
          </div>
          <span className="demo-pill">Demo</span>
        </div>
        <div className="flex flex-col gap-2 p-3">
          {demoPrompts.map((prompt, i) => (
            <button
              key={prompt}
              type="button"
              className="demo-item"
              onClick={() => submit(prompt)}
              disabled={isStreaming || readingImage || !initialized}
            >
              <span className="demo-item-num">{i + 1}</span>
              <MessageSquareText size={14} className="demo-item-icon shrink-0" />
              <span className="demo-item-text">{prompt}</span>
            </button>
          ))}
        </div>
      </aside>
      {panel}
    </div>
  )
}

function LoadingPlaceholder() {
  return (
    <div className="space-y-4">
      <div className="h-12 w-3/4 bg-white rounded-2xl animate-pulse" />
      <div className="h-8 w-1/2 bg-white rounded-2xl animate-pulse ms-auto" />
    </div>
  )
}
