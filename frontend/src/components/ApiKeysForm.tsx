import { useEffect, useState } from 'react'
import {
  clearApiKey,
  fetchSettingsKeys,
  saveSettingsKeys,
  type SettingsKeys,
} from '../lib/api'
import { formatApiError } from '../lib/errors'

export function ApiKeysForm({
  onKeysChanged,
  compact,
  saveLabel = 'Save keys',
}: {
  onKeysChanged?: () => void
  compact?: boolean
  saveLabel?: string
}) {
  const [data, setData] = useState<SettingsKeys | null>(null)
  const [openai, setOpenai] = useState('')
  const [xai, setXai] = useState('')
  const [googleFonts, setGoogleFonts] = useState('')
  const [reveal, setReveal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function load(showValues: boolean) {
    setError(null)
    try {
      const snap = await fetchSettingsKeys(showValues)
      setData(snap)
      if (showValues) {
        setOpenai(snap.openai.value || '')
        setXai(snap.xai.value || '')
        setGoogleFonts(snap.google_fonts?.value || '')
      }
    } catch (err) {
      setError(
        formatApiError(
          err,
          'Cannot load API key settings. If you are running locally, keep the server terminal open and refresh.',
        ),
      )
    }
  }

  useEffect(() => {
    void load(false)
  }, [])

  async function handleSave() {
    setBusy(true)
    setMessage(null)
    setError(null)
    try {
      const snap = await saveSettingsKeys({
        openai_api_key: openai.trim() || undefined,
        xai_api_key: xai.trim() || undefined,
        google_fonts_api_key: googleFonts.trim() || undefined,
      })
      setData(snap)
      setOpenai('')
      setXai('')
      setGoogleFonts('')
      setReveal(false)
      setMessage('Keys saved to local settings.')
      onKeysChanged?.()
    } catch (err) {
      setError(formatApiError(err, 'Could not save keys. Try again.'))
    } finally {
      setBusy(false)
    }
  }

  async function handleClear(which: 'openai' | 'xai' | 'google_fonts') {
    setBusy(true)
    setMessage(null)
    setError(null)
    try {
      const snap = await clearApiKey(which)
      setData(snap)
      if (which === 'openai') setOpenai('')
      else if (which === 'xai') setXai('')
      else setGoogleFonts('')
      setMessage(
        which === 'openai'
          ? 'OpenAI key cleared from settings.'
          : which === 'xai'
            ? 'Grok key cleared from settings.'
            : 'Google Fonts key cleared from settings.',
      )
      onKeysChanged?.()
    } catch (err) {
      setError(formatApiError(err, 'Could not clear that key.'))
    } finally {
      setBusy(false)
    }
  }

  async function toggleReveal() {
    const next = !reveal
    setReveal(next)
    await load(next)
  }

  return (
    <div className={compact ? 'api-keys-form is-compact' : 'api-keys-form'}>
      {error && <div className="banner banner-danger">{error}</div>}
      {message && <div className="banner">{message}</div>}

      <div className="settings-key-grid">
        <KeyCard
          label={data?.openai.label || 'OpenAI API key'}
          help={data?.openai.help}
          configured={Boolean(data?.openai.configured)}
          source={data?.openai.source}
          hint={data?.openai.hint}
          value={openai}
          onChange={setOpenai}
          placeholder={
            reveal && data?.openai.value
              ? data.openai.value
              : data?.openai.hint
                ? `Current: ${data.openai.hint}`
                : 'sk-...'
          }
          onClear={() => void handleClear('openai')}
          busy={busy}
        />
        <KeyCard
          label={data?.xai.label || 'Grok / xAI API key'}
          help={data?.xai.help}
          configured={Boolean(data?.xai.configured)}
          source={data?.xai.source}
          hint={data?.xai.hint}
          value={xai}
          onChange={setXai}
          placeholder={
            reveal && data?.xai.value
              ? data.xai.value
              : data?.xai.hint
                ? `Current: ${data.xai.hint}`
                : 'xai-...'
          }
          onClear={() => void handleClear('xai')}
          busy={busy}
        />
        <KeyCard
          label={data?.google_fonts?.label || 'Google Fonts API key'}
          help={data?.google_fonts?.help}
          configured={Boolean(data?.google_fonts?.configured)}
          source={data?.google_fonts?.source}
          hint={data?.google_fonts?.hint}
          value={googleFonts}
          onChange={setGoogleFonts}
          placeholder={
            reveal && data?.google_fonts?.value
              ? data.google_fonts.value
              : data?.google_fonts?.hint
                ? `Current: ${data.google_fonts.hint}`
                : 'AIza...'
          }
          onClear={() => void handleClear('google_fonts')}
          busy={busy}
        />
      </div>

      <div className="settings-actions">
        <button type="button" className="btn" disabled={busy} onClick={() => void handleSave()}>
          {saveLabel}
        </button>
        <button
          type="button"
          className="btn-ghost"
          disabled={busy}
          onClick={() => void toggleReveal()}
        >
          {reveal ? 'Hide values' : 'Show current keys'}
        </button>
      </div>
    </div>
  )
}

function KeyCard({
  label,
  help,
  configured,
  source,
  hint,
  value,
  onChange,
  placeholder,
  onClear,
  busy,
}: {
  label: string
  help?: string
  configured: boolean
  source?: string | null
  hint?: string | null
  value: string
  onChange: (v: string) => void
  placeholder: string
  onClear: () => void
  busy: boolean
}) {
  return (
    <div className="settings-key-card">
      <div className="settings-key-head">
        <strong>{label}</strong>
        <span className={configured ? 'pill-ok' : 'pill-muted'}>
          {configured ? `Set (${source || 'local'})` : 'Not set'}
        </span>
      </div>
      {help && <p className="settings-help">{help}</p>}
      {hint && !value && (
        <p className="settings-hint">
          Stored hint: <code>{hint}</code>
        </p>
      )}
      <input
        className="field"
        type="password"
        autoComplete="off"
        spellCheck={false}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      <button type="button" className="btn-ghost" disabled={busy || !configured} onClick={onClear}>
        Clear from settings
      </button>
    </div>
  )
}
