export type ValidationMessages = {
  invalidEmail: string
  invalidPhone: string
  passwordTooShort: string
  nameTooShort: string
  passwordsMismatch: string
  generic: string
}

type ValidationItem = {
  type?: string
  loc?: unknown[]
  msg?: string
}

function fieldName(loc: unknown[] | undefined): string {
  if (!Array.isArray(loc) || loc.length === 0) return ''
  return String(loc[loc.length - 1] ?? '')
}

function mapValidationItem(item: ValidationItem, msgs: ValidationMessages): string | null {
  const type = String(item.type ?? '')
  const field = fieldName(item.loc)
  const msg = String(item.msg ?? '')

  if (type === 'value_error' && msg.includes('Passwords do not match')) {
    return msgs.passwordsMismatch
  }
  if (type === 'string_pattern_mismatch') {
    if (field === 'email' || field === 'guest_email') return msgs.invalidEmail
    if (field === 'phone' || field === 'guest_phone') return msgs.invalidPhone
  }
  if (type === 'string_too_short') {
    if (field === 'password' || field === 'confirm_password' || field === 'new_password') {
      return msgs.passwordTooShort
    }
    if (field === 'full_name') return msgs.nameTooShort
  }
  return null
}

/** Turn FastAPI/Pydantic 422 `detail` arrays into user-facing messages. */
export function formatValidationDetail(detail: unknown, msgs: ValidationMessages): string {
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return msgs.generic

  const seen = new Set<string>()
  const lines: string[] = []

  for (const raw of detail) {
    if (typeof raw !== 'object' || !raw) continue
    const text = mapValidationItem(raw as ValidationItem, msgs)
    if (text && !seen.has(text)) {
      seen.add(text)
      lines.push(text)
    }
  }

  return lines.length ? lines.join('\n') : msgs.generic
}

export const defaultValidationMessages: ValidationMessages = {
  invalidEmail: 'Please enter a valid email address',
  invalidPhone: 'Please enter a valid phone number',
  passwordTooShort: 'Password must be at least 6 characters',
  nameTooShort: 'Name must be at least 2 characters',
  passwordsMismatch: 'Passwords do not match',
  generic: 'Please check your details and try again',
}
