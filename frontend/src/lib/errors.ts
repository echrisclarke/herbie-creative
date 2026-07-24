/** Turn API / network failures into short, human-readable copy (never raw JSON). */
export function formatApiError(err: unknown, fallback = 'Something went wrong. Try again.'): string {
  const raw = err instanceof Error ? err.message : String(err)
  if (!raw.trim()) return fallback

  if (/failed to fetch|networkerror|load failed|network request failed/i.test(raw)) {
    return 'Cannot reach the server. Check your connection and try again.'
  }

  return humanizeDetail(parseDetail(raw), fallback)
}

function parseDetail(raw: string): unknown {
  const trimmed = raw.trim()
  if (!(trimmed.startsWith('{') || trimmed.startsWith('['))) return trimmed
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown }
    if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
      return parsed.detail
    }
    return parsed
  } catch {
    return trimmed
  }
}

function humanizeDetail(detail: unknown, fallback: string): string {
  if (detail == null) return fallback

  if (typeof detail === 'string') {
    const text = detail.trim()
    if (!text) return fallback
    if (text.startsWith('{') || text.startsWith('[')) {
      return humanizeDetail(parseDetail(text), fallback)
    }
    return mapKnownMessage(text)
  }

  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg)
        }
        return ''
      })
      .map((s) => s.trim())
      .filter(Boolean)
    return parts.length ? mapKnownMessage(parts.join(' ')) : fallback
  }

  if (typeof detail === 'object') {
    const obj = detail as {
      message?: unknown
      error?: unknown
      requires_signup?: unknown
      detail?: unknown
    }
    if (obj.requires_signup) return 'Sign up or sign in to continue.'
    if (typeof obj.message === 'string' && obj.message.trim()) {
      return mapKnownMessage(obj.message.trim())
    }
    if (typeof obj.error === 'string' && obj.error.trim()) {
      return mapKnownMessage(obj.error.trim())
    }
    if (obj.detail != null) return humanizeDetail(obj.detail, fallback)
  }

  return fallback
}

function mapKnownMessage(text: string): string {
  if (/sign up to continue/i.test(text)) return 'Sign up or sign in to continue.'
  if (/not authenticated|unauthorized|401/i.test(text)) return 'Sign in to continue.'
  if (/forbidden|403/i.test(text)) return 'You do not have access to that.'
  if (/trial.*(over|ended|finished|exhausted)|no trial/i.test(text)) {
    return 'Free trial finished. Add your own OpenAI key in Settings to keep generating.'
  }
  return text
}
