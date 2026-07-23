import { useState, type FormEvent } from 'react'
import { login } from '../lib/api'

export function LoginScreen({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
      onSignedIn()
    } catch (err) {
      const raw = err instanceof Error ? err.message : String(err)
      let message = raw
      try {
        const parsed = JSON.parse(raw) as { detail?: string }
        if (parsed.detail) message = parsed.detail
      } catch {
        /* keep raw */
      }
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="install-setup" aria-label="Sign in">
      <div className="install-setup-media" style={{ backgroundImage: 'url(/brand/hero.png)' }} />
      <div className="install-setup-scrim" />
      <div className="install-setup-panel">
        <h1 className="name-header page-title header-text-style install-setup-brand">
          HERBIE CREATIVE
        </h1>
        <p className="install-setup-lead">Sign in to run campaigns with your own API keys.</p>
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
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
            />
          </label>
          {error && (
            <p className="install-setup-hint" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="btn" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </section>
  )
}
