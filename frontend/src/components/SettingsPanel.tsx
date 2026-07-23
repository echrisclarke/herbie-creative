import { useState } from 'react'
import { createInvitedUser, type AuthUser } from '../lib/api'
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

  return (
    <div className="panel settings-panel">
      <h2 style={{ marginTop: 0 }}>API keys</h2>
      <p style={{ color: 'var(--muted)', marginTop: 0 }}>
        {hosted
          ? 'Enter your own OpenAI, Grok, and Google Fonts keys. They are encrypted for your account only.'
          : 'Enter your own OpenAI, Grok, and Google Fonts keys. They are stored locally and never shipped with a public build.'}
      </p>
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
                  const raw = err instanceof Error ? err.message : String(err)
                  try {
                    const parsed = JSON.parse(raw) as { detail?: string }
                    setInviteErr(parsed.detail || raw)
                  } catch {
                    setInviteErr(raw)
                  }
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
              <p className="install-setup-hint" role="alert">
                {inviteErr}
              </p>
            )}
            <button type="submit" className="btn" disabled={inviteBusy}>
              {inviteBusy ? 'Creating…' : 'Create account'}
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
