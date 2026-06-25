import { useRef, useState } from 'react'
import { toPng } from 'html-to-image'
import { Bot, Check, Copy, Database, Download, MapPin, User, Zap } from 'lucide-react'
import ChatMessageContent from './ChatMessageContent'
import StationCardList from './StationCard'
import TripsTable from './TripsTable'
import TicketForm from './TicketForm'
import TicketCardList from './TicketCardList'
import type { StationCardData, TripRow } from '@/hooks/useChatStream'
import type { TicketDraft, TicketSummary } from '@/api/client'
import { useLanguage } from '@/i18n/LanguageProvider'

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  isTyping?: boolean
  imageUrl?: string
  sql?: string
  ttftMs?: number
  stations?: StationCardData[]
  destinations?: string[]
  trips?: TripRow[]
  ticketDraft?: TicketDraft
  ticketLoggedIn?: boolean
  ticketsCrm?: TicketSummary[]
  ticketChannel?: string
  ticketSessionId?: string | null
}

const _isSeparatorRow = (line: string) =>
  /^\s*\|?[\s:|-]*-{3,}[\s:|-]*\|?\s*$/.test(line) && line.includes('-')

/** True when the markdown contains a GFM table (a `---|---` separator row). */
function hasMarkdownTable(md: string): boolean {
  return md.split('\n').some(_isSeparatorRow)
}

/** Remove any GFM table block from markdown. Used when the app renders a
 *  deterministic table/card itself, so a model-hallucinated table never shows. */
function stripMarkdownTables(md: string): string {
  const lines = md.split('\n')
  const drop = new Set<number>()
  for (let i = 0; i < lines.length; i++) {
    if (_isSeparatorRow(lines[i]) && i > 0 && lines[i - 1].includes('|')) {
      drop.add(i - 1) // header
      drop.add(i) // separator
      let j = i + 1
      while (j < lines.length && lines[j].includes('|')) {
        drop.add(j)
        j++
      }
    }
  }
  return lines
    .filter((_, i) => !drop.has(i))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function SqlBubble({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(sql)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard may be unavailable */
    }
  }
  return (
    <details className="sql-bubble mt-2 max-w-[min(80%,560px)] ms-[2.875rem]">
      <summary className="sql-summary">
        <Database size={13} />
        <span>SQL query</span>
        <span className="sql-summary-hint">— click to view</span>
      </summary>
      <div className="sql-panel" dir="ltr">
        <div className="sql-panel-head">
          <span className="sql-panel-title">
            <Database size={12} /> SQL
          </span>
          <button type="button" className="sql-copy" onClick={copy}>
            {copied ? <Check size={12} /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
        <pre className="sql-code">
          <code>{sql}</code>
        </pre>
      </div>
    </details>
  )
}

function TypingIndicator() {
  return (
    <span className="typing-dots" aria-label="يكتب...">
      <span /><span /><span />
    </span>
  )
}

export default function MessageBubble({ role, content, isTyping, imageUrl, sql, ttftMs, stations, destinations, trips, ticketDraft, ticketLoggedIn, ticketsCrm, ticketChannel, ticketSessionId }: MessageBubbleProps) {
  const isUser = role === 'user'
  const { t } = useLanguage()
  const bubbleRef = useRef<HTMLDivElement>(null)
  const [exporting, setExporting] = useState(false)
  const hasTrips = !!trips && trips.length > 0
  const hasDeterministic =
    hasTrips || (!!stations && stations.length > 0) || (!!destinations && destinations.length > 0)
  // When the app renders its own table/card/chips, drop any table the model
  // hallucinated in its text so the user never sees duplicate/fabricated data.
  const displayContent = !isUser && hasDeterministic ? stripMarkdownTables(content) : content
  const hasTable = !isUser && (hasMarkdownTable(content) || hasTrips)
  const showExport = hasTable && !isTyping

  async function exportTable() {
    const table = bubbleRef.current?.querySelector<HTMLElement>('.chat-md-table')
    if (!table) return
    setExporting(true)
    // Capture the LIVE, on-screen table (reliable) and add full borders for the
    // image via a temporary class. Explicit width/height avoid clipping.
    table.classList.add('exporting')
    try {
      const w = Math.ceil(table.scrollWidth)
      const h = Math.ceil(table.scrollHeight)
      const dataUrl = await toPng(table, {
        backgroundColor: '#ffffff',
        pixelRatio: 2,
        width: w + 24,
        height: h + 24,
        // Skip web-font embedding: it tries to read cssRules from the cross-origin
        // Google Fonts stylesheet and throws a SecurityError. The image still
        // renders with the system font fallback.
        skipFonts: true,
        style: {
          margin: '0',
          padding: '12px',
          background: '#ffffff',
          boxSizing: 'content-box',
          fontFamily: 'system-ui, "Segoe UI", Tahoma, Arial, sans-serif',
        },
      })
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
      const link = document.createElement('a')
      link.download = `gobus-trips-${stamp}.png`
      link.href = dataUrl
      link.click()
    } catch {
      // Non-fatal: keep the chat usable even if capture fails.
    } finally {
      table.classList.remove('exporting')
      setExporting(false)
    }
  }

  return (
    <div className="fade-in">
      <div className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : ''}`}>
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
          ref={bubbleRef}
          className={`message-bubble relative px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm ${
            hasTable ? 'message-bubble--with-table' : 'max-w-[min(80%,520px)]'
          } ${
            isUser
              ? 'bg-[var(--color-brand-primary)] text-white rounded-tr-md'
              : 'bg-white border border-[var(--color-border-default)] rounded-tl-md'
          }`}
          dir="auto"
        >
          {showExport ? (
            <button
              type="button"
              onClick={exportTable}
              disabled={exporting}
              className="msg-export-btn"
              title={t.chat.exportTable}
              aria-label={t.chat.exportTable}
            >
              <Download size={14} />
            </button>
          ) : null}

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
              {displayContent ? <ChatMessageContent content={displayContent} isUser={isUser} /> : null}
              {!isUser && hasTrips ? <TripsTable trips={trips!} /> : null}
              {!isUser && stations && stations.length > 0 ? (
                <StationCardList stations={stations} />
              ) : null}
              {!isUser && destinations && destinations.length > 0 ? (
                <div className="dest-chips mt-2">
                  {destinations.map((d) => (
                    <span key={d} className="dest-chip">
                      <MapPin size={12} />
                      {d}
                    </span>
                  ))}
                </div>
              ) : null}
              {!isUser && ticketDraft ? (
                <TicketForm
                  draft={ticketDraft}
                  loggedIn={!!ticketLoggedIn}
                  channel={ticketChannel || 'website'}
                  sessionId={ticketSessionId ?? null}
                />
              ) : null}
              {!isUser && ticketsCrm && ticketsCrm.length > 0 ? (
                <TicketCardList tickets={ticketsCrm} />
              ) : null}
            </>
          )}
        </div>
      </div>

      {!isUser && ttftMs != null ? (
        <div className="ms-[2.875rem] mt-1.5 flex items-center gap-3 text-xs">
          <span
            className="inline-flex items-center gap-1 text-[var(--color-text-muted)]"
            title={t.chat.firstTokenTime}
          >
            <Zap size={12} />
            <span>{(ttftMs / 1000).toFixed(2)}s</span>
          </span>
        </div>
      ) : null}

      {!isUser && sql ? <SqlBubble sql={sql} /> : null}
    </div>
  )
}
