export function AboutPage({
  onBrowseLibrary,
  onSignUp,
}: {
  onBrowseLibrary?: () => void
  onSignUp?: () => void
}) {
  return (
    <section className="about-page-panel" aria-label="About Campaign Pipeline">
      <header className="about-panel-header">
        <div>
          <p className="app-subtitle">Campaign Pipeline</p>
          <h1 className="public-examples-title">About</h1>
        </div>
        <div className="public-examples-actions">
          {onBrowseLibrary && (
            <button type="button" className="btn-ghost" onClick={onBrowseLibrary}>
              Open Library
            </button>
          )}
          {onSignUp && (
            <button type="button" className="btn" onClick={onSignUp}>
              Sign up for free trial
            </button>
          )}
        </div>
      </header>

      <div className="about-page-body">
        <p>
          Campaign Pipeline turns a campaign brief and product assets into multi-ratio social
          creatives. You set brand, products, framing, and copy, then generate stills, stamp finals
          with message and logo, and optionally add short motion clips.
        </p>
        <p>
          The flow is Intake → Review → Generate → Finalize → Results. Open Library to browse demo
          examples before you create an account. When you sign up, your runs and library stay private
          to you. New accounts get a short free trial on the demo key, then you add your own OpenAI
          key in Settings to keep generating.
        </p>
        <p>
          Built for scalable social campaign production: consistent ratios, localization-ready
          finals, and a library you can reopen later.
        </p>
      </div>
    </section>
  )
}
