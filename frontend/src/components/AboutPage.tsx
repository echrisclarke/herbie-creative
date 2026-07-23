export function AboutPage({
  onBack,
  onGetStarted,
}: {
  onBack?: () => void
  onGetStarted?: () => void
}) {
  return (
    <section className="about-page" aria-label="About Campaign Pipeline">
      <header className="public-examples-header">
        <div>
          <p className="app-subtitle">Campaign Pipeline</p>
          <h1 className="public-examples-title">About</h1>
        </div>
        <div className="public-examples-actions">
          {onBack && (
            <button type="button" className="btn-ghost" onClick={onBack}>
              Back
            </button>
          )}
          {onGetStarted && (
            <button type="button" className="btn" onClick={onGetStarted}>
              Sign up to run
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
          The flow is Intake → Review → Generate → Finalize → Results. Sample campaigns show the
          kind of output you can expect. When you create an account, your runs and library stay
          private to you. New accounts get a short free trial on the demo key, then you add your own
          OpenAI key to keep generating.
        </p>
        <p>
          Built for scalable social campaign production: consistent ratios, localization-ready
          finals, and a library you can reopen later.
        </p>
      </div>
    </section>
  )
}
