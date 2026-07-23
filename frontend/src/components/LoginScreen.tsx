import { useState, type FormEvent } from 'react'
import { login, publicUrl, signup } from '../lib/api'

type Mode = 'signin' | 'signup'

function errorMessage(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err)
  try {
    const parsed = JSON.parse(raw) as { detail?: string }
    if (parsed.detail) return parsed.detail
  } catch {
    /* keep raw */
  }
  return raw
}

export function LoginScreen({
  onSignedIn,
  initialMode = 'signin',
  trialMessage,
  onBack,
}: {
  onSignedIn: () => void
  initialMode?: Mode
  trialMessage?: string
  onBack?: () => void
}) {
  const [mode, setMode] = useState<Mode>(initialMode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'signup') {
        if (password !== confirm) {
          throw new Error('Passwords do not match')
        }
        await signup(email.trim(), password)
      } else {
        await login(email.trim(), password)
      }
      onSignedIn()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="install-setup" aria-label={mode === 'signup' ? 'Sign up' : 'Sign in'}>
      <div
        className="install-setup-media"
        style={{ backgroundImage: `url(${publicUrl('/brand/hero.png')})` }}
      />
      <div className="install-setup-scrim" />
      <div className="install-setup-panel">
        <h1 className="name-header page-title header-text-style install-setup-brand">
          HERBIE CREATIVE
        </h1>
        <p className="install-setup-product">Campaign Pipeline</p>
        <p className="install-setup-lead">
          {trialMessage ||
            (mode === 'signup'
              ? 'Create an account, then add your own OpenAI key in Settings to generate creatives.'
              : 'Sign in to your account.')}
        </p>

        <div className="auth-mode-toggle" role="tablist" aria-label="Account">
          <button
            type="button"
            role="tab"
            className={mode === 'signin' ? 'app-tab active' : 'app-tab'}
            aria-selected={mode === 'signin'}
            onClick={() => {
              setMode('signin')
              setError(null)
            }}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            className={mode === 'signup' ? 'app-tab active' : 'app-tab'}
            aria-selected={mode === 'signup'}
            onClick={() => {
              setMode('signup')
              setError(null)
            }}
          >
            Sign up
          </button>
        </div>

        <form className="login-form" onSubmit={(e) => void handleSubmit(e)}>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
            />
          </label>
          {mode === 'signup' && (
            <label className="field">
              <span>Confirm password</span>
              <input
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                minLength={8}
              />
            </label>
          )}
          {error && (
            <p className="install-setup-hint" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="btn" disabled={busy}>
            {busy
              ? mode === 'signup'
                ? 'Creating account…'
                : 'Signing in…'
              : mode === 'signup'
                ? 'Create account'
                : 'Sign in'}
          </button>
          {onBack && (
            <button type="button" className="btn-ghost" onClick={onBack} disabled={busy}>
              Back
            </button>
          )}
        </form>
      </div>
    </section>
  )
}
