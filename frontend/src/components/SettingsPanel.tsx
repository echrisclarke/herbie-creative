import { useEffect, useState } from 'react'
import {
  adminResetUserPassword,
  createInvitedUser,
  fetchSettingsKeys,
  type AuthUser,
  type TrialStatus,
} from '../lib/api'
import { formatApiError } from '../lib/errors'
import { ApiKeysForm } from './ApiKeysForm'

export function SettingsPanel({
  onKeysChanged,
  authUser,
  hosted,
}: {
  onKeysChanged?: () => void
  authUser?: AuthUser | null
  hosted?: boolean
}) {
  const [inviteEmail, setInviteEmail] = useState('')
  const [invitePassword, setInvitePassword] = useState('')
  const [inviteMsg, setInviteMsg] = useState<string | null>(null)
  const [inviteErr, setInviteErr] = useState<string | null>(null)
  const [inviteBusy, setInviteBusy] = useState(false)
  const [resetEmail, setResetEmail] = useState('')
  const [resetPassword, setResetPassword] = useState('')
  const [resetMsg, setResetMsg] = useState<string | null>(null)
  const [resetErr, setResetErr] = useState<string | null>(null)
  const [resetBusy, setResetBusy] = useState(false)
  const [trial, setTrial] = useState<TrialStatus | null>(null)

  useEffect(() => {
    if (!hosted) return
    void fetchSettingsKeys()
      .then((s) => setTrial(s.trial || null))
      .catch(() => setTrial(null))
  }, [hosted])

  return (
    <div className="panel settings-panel">
      <h2 style={{ marginTop: 0 }}>API keys</h2>
      <p style={{ color: 'var(--muted)', marginTop: 0 }}>
        {hosted
          ? 'Enter your own OpenAI, Grok, and Google Fonts keys. They are encrypted for your account only.'
          : 'Enter your own OpenAI, Grok, and Google Fonts keys. They are stored locally and never shipped with a public build.'}
      </p>
      {hosted && trial?.mode === 'account' && !trial.has_own_openai && (
        <p className="trial-note" style={{ marginTop: '0.75rem' }}>
          {trial.can_use_host_openai
            ? `Trial · ${trial.remaining ?? 0} of ${trial.limit ?? 3} generate runs left on the demo key. Add your own OpenAI key anytime.`
            : 'Trial finished. Add your own OpenAI key to keep generating. Existing creatives stay in your account.'}
        </p>
      )}
      {authUser && (
        <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>
          Signed in as <strong>{authUser.email}</strong>
        </p>
      )}
      <ApiKeysForm onKeysChanged={onKeysChanged} />

      {hosted && authUser?.is_admin && (
        <div style={{ marginTop: '2rem' }}>
          <h3>Invite user</h3>
          <p style={{ color: 'var(--muted)' }}>
            Create an account for someone else. They will use their own API keys.
          </p>
          <form
            className="login-form"
            onSubmit={(e) => {
              e.preventDefault()
              setInviteBusy(true)
              setInviteMsg(null)
              setInviteErr(null)
              void createInvitedUser({
                email: inviteEmail.trim(),
                password: invitePassword,
              })
                .then((r) => {
                  setInviteMsg(`Created ${r.user.email}`)
                  setInviteEmail('')
                  setInvitePassword('')
                })
                .catch((err) => {
                  setInviteErr(formatApiError(err, 'Could not create that account.'))
                })
                .finally(() => setInviteBusy(false))
            }}
          >
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>Temporary password</span>
              <input
                type="password"
                value={invitePassword}
                onChange={(e) => setInvitePassword(e.target.value)}
                required
                minLength={8}
              />
            </label>
            {inviteMsg && <p className="banner">{inviteMsg}</p>}
            {inviteErr && (
              <p className="form-error" role="alert">
                {inviteErr}
              </p>
            )}
            <button type="submit" className="btn" disabled={inviteBusy}>
              {inviteBusy ? 'Creating…' : 'Create account'}
            </button>
          </form>

          <h3 style={{ marginTop: '2rem' }}>Reset user password</h3>
          <p style={{ color: 'var(--muted)' }}>
            Set a new password for any account. Use this if email reset is not set up yet.
          </p>
          <form
            className="login-form"
            onSubmit={(e) => {
              e.preventDefault()
              setResetBusy(true)
              setResetMsg(null)
              setResetErr(null)
              void adminResetUserPassword(resetEmail.trim(), resetPassword)
                .then((r) => {
                  setResetMsg(`Updated password for ${r.user.email}`)
                  setResetEmail('')
                  setResetPassword('')
                })
                .catch((err) => {
                  setResetErr(formatApiError(err, 'Could not reset that password.'))
                })
                .finally(() => setResetBusy(false))
            }}
          >
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                value={resetEmail}
                onChange={(e) => setResetEmail(e.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>New password</span>
              <input
                type="password"
                value={resetPassword}
                onChange={(e) => setResetPassword(e.target.value)}
                required
                minLength={8}
              />
            </label>
            {resetMsg && <p className="banner">{resetMsg}</p>}
            {resetErr && (
              <p className="form-error" role="alert">
                {resetErr}
              </p>
            )}
            <button type="submit" className="btn" disabled={resetBusy}>
              {resetBusy ? 'Saving…' : 'Reset password'}
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
