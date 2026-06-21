export const TIME_OPTIONS = Array.from({ length: 24 }, (_, i) => {
  const hour = i % 12 || 12
  const period = i < 12 ? 'AM' : 'PM'
  return `${hour}:00 ${period}`
})

export function formatWorkingHours(
  is24: boolean,
  opensAt: string | null | undefined,
  closesAt: string | null | undefined
): string | null {
  if (is24) return '24 hours'
  if (opensAt && closesAt) return `${opensAt} – ${closesAt}`
  return null
}

export function parseWorkingHours(text: string | null | undefined): {
  is_24_hours: boolean
  opens_at: string
  closes_at: string
} {
  if (!text) return { is_24_hours: false, opens_at: '', closes_at: '' }
  const lower = text.toLowerCase()
  if (lower.includes('24') || lower.includes('مفتوح')) {
    return { is_24_hours: true, opens_at: '', closes_at: '' }
  }
  const parts = text.split(/[–\-—]/).map((p) => p.trim())
  if (parts.length === 2) {
    return { is_24_hours: false, opens_at: parts[0], closes_at: parts[1] }
  }
  return { is_24_hours: false, opens_at: '', closes_at: '' }
}
