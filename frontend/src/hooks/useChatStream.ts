import { useCallback, useRef, useState } from 'react'

interface StreamCallbacks {
  onToken: (token: string) => void
  onSession?: (sessionId: string) => void
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
          let payload: Record<string, string>
          try {
            payload = JSON.parse(data)
          } catch {
            return
          }
          if (event === 'session' && payload.session_id) {
            callbacks.onSession?.(payload.session_id)
          } else if (event === 'token' && typeof payload.content === 'string') {
            callbacks.onToken(payload.content)
          } else if (event === 'error') {
            callbacks.onError?.(payload.error || 'Error')
          } else if (event === 'done') {
            callbacks.onDone?.()
          }
        })

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          parser.feed(decoder.decode(value, { stream: true }))
        }
        parser.finish()
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          callbacks.onError?.((err as Error).message || 'Unexpected error')
        }
      } finally {
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
