import { publicUrl } from '../lib/api'

const LANDING_KEY = 'herbie-creative-landing-seen'

export function hasSeenLanding(): boolean {
  try {
    return localStorage.getItem(LANDING_KEY) === '1'
  } catch {
    return false
  }
}

export function markLandingSeen(): void {
  try {
    localStorage.setItem(LANDING_KEY, '1')
  } catch {
    /* ignore */
  }
}

export function clearLandingSeen(): void {
  try {
    localStorage.removeItem(LANDING_KEY)
  } catch {
    /* ignore */
  }
}

export function LandingHero({
  onEnter,
  onViewExamples,
}: {
  onEnter: () => void
  onViewExamples?: () => void
}) {
  const heroMp4 = publicUrl('/brand/hero.mp4')
  const heroPng = publicUrl('/brand/hero.png')
  return (
    <section className="landing-hero" aria-label="Herbie Creative Campaign Pipeline intro">
      <video
        className="landing-hero-media"
        src={heroMp4}
        poster={heroPng}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
      />
      <img
        className="landing-hero-fallback"
        src={heroPng}
        alt=""
        aria-hidden
      />
      <div className="landing-hero-scrim" />
      <div className="landing-hero-content">
        <h1 className="name-header page-title header-text-style landing-hero-brand">
          HERBIE CREATIVE
        </h1>
        <p className="landing-hero-line">Campaign Pipeline</p>
        <div className="landing-hero-cta-row">
          <button
            type="button"
            className="btn landing-hero-cta"
            onClick={() => {
              markLandingSeen()
              onEnter()
            }}
          >
            Get started
          </button>
          {onViewExamples && (
            <button
              type="button"
              className="btn-ghost landing-hero-cta"
              onClick={onViewExamples}
            >
              View example creatives
            </button>
          )}
        </div>
      </div>
    </section>
  )
}
