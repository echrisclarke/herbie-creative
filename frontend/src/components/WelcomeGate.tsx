import { publicUrl } from '../lib/api'

export function WelcomeGate({
  onSignUp,
  onSignIn,
  onAbout,
  onExamples,
}: {
  onSignUp: () => void
  onSignIn: () => void
  onAbout: () => void
  onExamples: () => void
}) {
  return (
    <section className="install-setup" aria-label="Welcome">
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
          Create an account to run campaigns, or look around first.
        </p>

        <div className="welcome-gate-actions">
          <button type="button" className="btn" onClick={onSignUp}>
            Sign up
          </button>
          <button type="button" className="btn-ghost" onClick={onSignIn}>
            Sign in
          </button>
          <button type="button" className="btn-ghost" onClick={onExamples}>
            Example creatives
          </button>
          <button type="button" className="btn-ghost" onClick={onAbout}>
            About
          </button>
        </div>
      </div>
    </section>
  )
}
