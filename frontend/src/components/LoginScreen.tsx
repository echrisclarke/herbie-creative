import { useEffect, useState, type FormEvent } from 'react'
import {
  forgotPassword,
  login,
  publicUrl,
  resetPassword,
  signup,
} from '../lib/api'
import { formatApiError } from '../lib/errors'

type Mode = 'signin' | 'signup' | 'forgot' | 'reset'

export function LoginScreen({
  onSignedIn,
  initialMode = 'signin',
  trialMessage,
  onBack,
  resetToken = null,
}: {
  onSignedIn: () => void
  initialMode?: Mode
  trialMessage?: string
  onBack?: () => void
  resetToken?: string | null
}) {
  const [mode, setMode] = useState<Mode>(resetToken ? 'reset' : initialMode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  useEffect(() => {
    if (resetToken) {
      setMode('reset')
      setError(null)
      setInfo(null)
    }
  }, [resetToken])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      if (mode === 'forgot') {
        const res = await forgotPassword(email.trim())
        setInfo(res.message)
        return
      }
      if (mode === 'reset') {
        if (!resetToken) throw new Error('Reset link is missing or expired.')
        if (password !== confirm) throw new Error('Passwords do not match')
        await resetPassword(resetToken, password)
        onSignedIn()
        return
      }
      if (mode === 'signup') {
        if (password !== confirm) throw new Error('Passwords do not match')
        await signup(email.trim(), password)
      } else {
        await login(email.trim(), password)
      }
      onSignedIn()
    } catch (err) {
      setError(
        formatApiError(
          err,
          mode === 'signup'
            ? 'Could not create account.'
            : mode === 'forgot'
              ? 'Could not start password reset.'
              : mode === 'reset'
                ? 'Could not reset password.'
                : 'Could not sign in.',
        ),
      )
    } finally {
      setBusy(false)
    }
  }

  const lead =
    mode === 'forgot'
      ? 'Enter your email and we will send a reset link if that account exists.'
      : mode === 'reset'
        ? 'Choose a new password.'
        : trialMessage ||
          (mode === 'signup' ? 'Create an account to run campaigns.' : 'Sign in to continue.')

  return (
    <section
      className="install-setup gate-enter"
      aria-label={
        mode === 'signup'
          ? 'Sign up'
          : mode === 'forgot'
            ? 'Forgot password'
            : mode === 'reset'
              ? 'Reset password'
              : 'Sign in'
      }
    >
      <div
        className="install-setup-media"
        style={{ backgroundImage: `url(${publicUrl('/brand/hero.png')})` }}
      />
      <div className="install-setup-scrim" />
      <div className="install-setup-panel gate-panel">
        <h1 className="name-header page-title header-text-style install-setup-brand">
          HERBIE CREATIVE
        </h1>
        <p className="install-setup-product">Campaign Pipeline</p>
        <p className="install-setup-lead">{lead}</p>

        {(mode === 'signin' || mode === 'signup') && (
          <div className="auth-mode-toggle" role="tablist" aria-label="Account">
            <button
              type="button"
              role="tab"
              className={mode === 'signin' ? 'app-tab active' : 'app-tab'}
              aria-selected={mode === 'signin'}
              onClick={() => {
                setMode('signin')
                setError(null)
                setInfo(null)
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
                setInfo(null)
              }}
            >
              Sign up
            </button>
          </div>
        )}

        <form className="login-form" onSubmit={(e) => void handleSubmit(e)}>
          {mode !== 'reset' && (
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
          )}
          {(mode === 'signin' || mode === 'signup' || mode === 'reset') && (
            <label className="field">
              <span>{mode === 'reset' ? 'New password' : 'Password'}</span>
              <input
                type="password"
                autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
              />
            </label>
          )}
          {(mode === 'signup' || mode === 'reset') && (
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
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {info && (
            <p className="form-info" role="status">
              {info}
            </p>
          )}
          <button type="submit" className="btn" disabled={busy}>
            {busy
              ? mode === 'signup'
                ? 'Creating account…'
                : mode === 'forgot'
                  ? 'Sending…'
                  : mode === 'reset'
                    ? 'Saving…'
                    : 'Signing in…'
              : mode === 'signup'
                ? 'Create account'
                : mode === 'forgot'
                  ? 'Send reset link'
                  : mode === 'reset'
                    ? 'Set new password'
                    : 'Sign in'}
          </button>
          {mode === 'signin' && (
            <button
              type="button"
              className="text-link"
              style={{ justifySelf: 'start' }}
              onClick={() => {
                setMode('forgot')
                setError(null)
                setInfo(null)
                setPassword('')
              }}
            >
              Forgot password?
            </button>
          )}
          {(mode === 'forgot' || mode === 'reset') && (
            <button
              type="button"
              className="btn-ghost"
              onClick={() => {
                setMode('signin')
                setError(null)
                setInfo(null)
              }}
              disabled={busy}
            >
              Back to sign in
            </button>
          )}
          {onBack && mode !== 'forgot' && mode !== 'reset' && (
            <button type="button" className="btn-ghost" onClick={onBack} disabled={busy}>
              Back
            </button>
          )}
        </form>
      </div>
    </section>
  )
}
