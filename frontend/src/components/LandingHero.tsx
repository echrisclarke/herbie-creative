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

export function LandingHero({ onEnter }: { onEnter: () => void }) {
  return (
    <section className="landing-hero" aria-label="Herbie Creative intro">
      <video
        className="landing-hero-media"
        src="/brand/hero.mp4"
        poster="/brand/hero.png"
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
      />
      <img
        className="landing-hero-fallback"
        src="/brand/hero.png"
        alt=""
        aria-hidden
      />
      <div className="landing-hero-scrim" />
      <div className="landing-hero-content">
        <h1 className="name-header page-title header-text-style landing-hero-brand">
          HERBIE CREATIVE
        </h1>
        <p className="landing-hero-line">Campaign Pipeline</p>
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
      </div>
    </section>
  )
}
