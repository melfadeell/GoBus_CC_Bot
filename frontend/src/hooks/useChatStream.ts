import { useCallback, useRef, useState } from 'react'

export interface StationCardData {
  name: string
  address: string
  working_hours: string
  map_url: string
  city: string
}

export interface TripRow {
  origin: string
  destination: string
  date: string
  departure: string
  arrival: string
  bus_class: string
  available_seats: number
  total_seats: number
  price_egp: number
  bookable: boolean
}

interface StreamCallbacks {
  onToken: (token: string) => void
  onSession?: (sessionId: string) => void
  onMeta?: (meta: {
    sql?: string
    ttft_ms?: number
    stations?: StationCardData[]
    destinations?: string[]
    trips?: TripRow[]
  }) => void
  onDone?: () => void
  onError?: (error: string) => void
}

export interface SendMessageOptions {
  ocrText?: string
  imageUrl?: string
  channel?: string
}

const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif'])

/** Parse SSE stream from fetch body — handles \n and \r\n line endings. */
function createSseParser(onEvent: (event: string, data: string) => void) {
  let buffer = ''
  let currentEvent = 'message'
  let currentData: string[] = []

  const flushEvent = () => {
    if (currentData.length === 0) return
    onEvent(currentEvent, currentData.join('\n'))
    currentEvent = 'message'
    currentData = []
  }

  const feed = (chunk: string) => {
    buffer += chunk
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line === '') {
        flushEvent()
        continue
      }
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        currentData.push(line.slice(5).trimStart())
      }
    }
  }

  const finish = () => {
    if (buffer.trim()) {
      for (const line of buffer.split(/\r?\n/)) {
        if (line === '') flushEvent()
        else if (line.startsWith('event:')) currentEvent = line.slice(6).trim()
        else if (line.startsWith('data:')) currentData.push(line.slice(5).trimStart())
      }
    }
    flushEvent()
  }

  return { feed, finish }
}

export function validateImageFile(file: File): string | null {
  if (!ALLOWED_IMAGE_TYPES.has(file.type)) return 'invalidImageType'
  if (file.size > MAX_IMAGE_BYTES) return 'imageTooLarge'
  return null
}

export async function uploadChatImage(file: File): Promise<string> {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch('/api/chat/upload-image', { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Upload failed' }))
    throw new Error(formatApiError(err.detail))
  }
  const data = (await res.json()) as { image_url?: string }
  if (!data.image_url) throw new Error('Upload failed')
  return data.image_url
}

export async function ocrImage(file: File): Promise<string> {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch('/api/chat/ocr', { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'OCR failed' }))
    throw new Error(formatApiError(err.detail))
  }

  const data = (await res.json()) as { text?: string }
  return data.text ?? ''
}

export function useChatStream() {
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(
    async (
      message: string,
      sessionId: string | null,
      callbacks: StreamCallbacks,
      options?: SendMessageOptions
    ) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      setIsStreaming(true)

      // Inactivity watchdog: abort if no data arrives for a while (hung request).
      const TIMEOUT_MS = 45000
      let timedOut = false
      let watchdog = setTimeout(() => {
        timedOut = true
        controller.abort()
      }, TIMEOUT_MS)
      const resetWatchdog = () => {
        clearTimeout(watchdog)
        watchdog = setTimeout(() => {
          timedOut = true
          controller.abort()
        }, TIMEOUT_MS)
      }

      try {
        const body: Record<string, string | null | undefined> = {
          message,
          session_id: sessionId,
        }
        if (options?.ocrText !== undefined) {
          body.ocr_text = options.ocrText
        }
        if (options?.imageUrl) {
          body.image_url = options.imageUrl
        }
        if (options?.channel) {
          body.channel = options.channel
        }

        const res = await fetch('/api/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
          body: JSON.stringify(body),
          signal: controller.signal,
        })

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Server connection failed' }))
          throw new Error(formatApiError(err.detail))
        }

        if (!res.body) throw new Error('No response body')

        const reader = res.body.getReader()
        const decoder = new TextDecoder()

        const parser = createSseParser((event, data) => {
          let payload: Record<string, unknown>
          try {
            payload = JSON.parse(data)
          } catch {
            return
          }
          if (event === 'session' && typeof payload.session_id === 'string') {
            callbacks.onSession?.(payload.session_id)
          } else if (event === 'token' && typeof payload.content === 'string') {
            callbacks.onToken(payload.content)
          } else if (event === 'meta') {
            callbacks.onMeta?.({
              sql: typeof payload.sql === 'string' ? payload.sql : undefined,
              ttft_ms: typeof payload.ttft_ms === 'number' ? payload.ttft_ms : undefined,
              stations: Array.isArray(payload.stations)
                ? (payload.stations as StationCardData[])
                : undefined,
              destinations: Array.isArray(payload.destinations)
                ? (payload.destinations as string[])
                : undefined,
              trips: Array.isArray(payload.trips) ? (payload.trips as TripRow[]) : undefined,
            })
          } else if (event === 'error') {
            callbacks.onError?.(typeof payload.error === 'string' ? payload.error : 'Error')
          } else if (event === 'done') {
            callbacks.onDone?.()
          }
        })

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          resetWatchdog()
          parser.feed(decoder.decode(value, { stream: true }))
        }
        parser.finish()
      } catch (err) {
        if (timedOut) {
          callbacks.onError?.('The request timed out. Please try again.')
        } else if ((err as Error).name !== 'AbortError') {
          callbacks.onError?.((err as Error).message || 'Unexpected error')
        }
      } finally {
        clearTimeout(watchdog)
        setIsStreaming(false)
      }
    },
    []
  )

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    setIsStreaming(false)
  }, [])

  return { sendMessage, isStreaming, cancel }
}

function formatApiError(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === 'object' && d && 'msg' in d ? String(d.msg) : String(d)))
      .join(', ')
  }
  return 'Server connection failed'
}
