import { ApiKeysForm } from './ApiKeysForm'

export function SettingsPanel({ onKeysChanged }: { onKeysChanged?: () => void }) {
  return (
    <div className="panel settings-panel">
      <h2 style={{ marginTop: 0 }}>API keys</h2>
      <p style={{ color: 'var(--muted)', marginTop: 0 }}>
        Enter your own OpenAI, Grok, and Google Fonts keys. They are stored locally and never
        shipped with a public build.
      </p>
      <ApiKeysForm onKeysChanged={onKeysChanged} />
    </div>
  )
}
