import { useEffect, useState } from 'react'
import { getHealth, publicUrl } from '../lib/api'
import { ApiKeysForm } from './ApiKeysForm'

export function InstallSetup({
  openaiConfigured,
  motionAvailable,
  onContinue,
  onKeysChanged,
}: {
  openaiConfigured: boolean
  motionAvailable: boolean
  onContinue: () => void
  onKeysChanged: () => void
}) {
  const [apiUp, setApiUp] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false
    async function ping() {
      try {
        const h = await getHealth()
        if (!cancelled) setApiUp(Boolean(h?.ok))
      } catch {
        if (!cancelled) setApiUp(false)
      }
    }
    void ping()
    const id = window.setInterval(() => void ping(), 4000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  return (
    <section className="install-setup" aria-label="Setup">
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
          Add your API keys to run the campaign pipeline. On the live site, new accounts get 3
          free generate runs on the demo key before your own OpenAI key is required.
        </p>

        <ul className="install-checklist">
          <li className={apiUp === null ? 'is-muted' : apiUp ? 'is-ok' : 'is-warn'}>
            {apiUp === null
              ? 'Checking server…'
              : apiUp
                ? 'App running'
                : 'Server not reachable. Keep the terminal with run_app.py open'}
          </li>
          <li className={openaiConfigured ? 'is-ok' : 'is-warn'}>
            OpenAI key {openaiConfigured ? 'ready' : 'needed for Generate'}
          </li>
          <li className={motionAvailable ? 'is-ok' : 'is-muted'}>
            Grok motion {motionAvailable ? 'ready' : 'optional'}
          </li>
        </ul>

        {apiUp === false && (
          <p className="install-setup-hint" role="alert">
            The browser cannot reach the local API. In the project folder run{' '}
            <code>py -3 run_app.py</code> (or <code>python3 run_app.py</code>), wait until it
            says the server is running, then refresh this page.
          </p>
        )}

        <ApiKeysForm
          compact
          saveLabel="Save and continue"
          onKeysChanged={() => {
            onKeysChanged()
            void getHealth()
              .then((h) => {
                setApiUp(Boolean(h?.ok))
                if (h.openai_configured !== false) onContinue()
              })
              .catch(() => {
                setApiUp(false)
              })
          }}
        />

        <div className="install-setup-actions">
          {openaiConfigured ? (
            <button type="button" className="btn" onClick={onContinue}>
              Continue to pipeline
            </button>
          ) : (
            <p className="install-setup-hint">
              Save an OpenAI key above to generate creatives. You can still browse the Library
              without a key.
            </p>
          )}
          <button type="button" className="btn-ghost" onClick={onContinue}>
            Skip for now
          </button>
        </div>
      </div>
    </section>
  )
}
