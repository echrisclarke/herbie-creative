import { useEffect, useState } from 'react'
import {
  fetchPublicGallery,
  publicUrl,
  type GalleryCreative,
  type GalleryResponse,
} from '../lib/api'

function mediaUrl(url: string) {
  return publicUrl(url.startsWith('/') ? url : `/${url}`)
}

function isMotion(item: GalleryCreative) {
  return item.kind === 'motion' || item.url.toLowerCase().endsWith('.mp4')
}

export function PublicExamplesGallery({
  onBack,
  onGetStarted,
}: {
  onBack?: () => void
  onGetStarted?: () => void
}) {
  const [data, setData] = useState<GalleryResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lightbox, setLightbox] = useState<GalleryCreative | null>(null)

  useEffect(() => {
    void fetchPublicGallery()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  const creatives = data?.creatives || []
  const campaigns = data?.campaigns || []

  return (
    <section className="public-examples" aria-label="Example creatives">
      <header className="public-examples-header">
        <div>
          <p className="app-subtitle">Campaign Pipeline</p>
          <h1 className="public-examples-title">Example creatives</h1>
          <p className="public-examples-lead">
            Full sample outputs from demo campaigns, including stills and motion. Sign up to run
            your own pipeline and keep a private library.
          </p>
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

      {error && <div className="banner banner-danger">{error}</div>}

      {!error && !data && <p style={{ color: 'var(--muted)' }}>Loading examples…</p>}

      {campaigns.map((camp) => {
        const items = creatives.filter((c) => c.campaign_id === camp.id)
        if (!items.length) return null
        return (
          <div key={camp.id} className="public-examples-campaign">
            <h2>{camp.name}</h2>
            <p className="public-examples-meta">
              {camp.brand ? `${camp.brand} · ` : ''}
              {items.length} asset{items.length === 1 ? '' : 's'}
            </p>
            <div className="public-examples-grid">
              {items.map((item) => (
                <button
                  key={item.url}
                  type="button"
                  className="public-examples-card"
                  onClick={() => setLightbox(item)}
                >
                  {isMotion(item) ? (
                    <video
                      src={mediaUrl(item.url)}
                      muted
                      playsInline
                      preload="metadata"
                      onLoadedMetadata={(e) => {
                        const el = e.currentTarget
                        try {
                          if (el.duration && Number.isFinite(el.duration)) {
                            el.currentTime = Math.min(0.15, el.duration * 0.05)
                          }
                        } catch {
                          /* ignore */
                        }
                      }}
                    />
                  ) : (
                    <img src={mediaUrl(item.url)} alt="" loading="lazy" />
                  )}
                  <span>
                    {item.product} · {item.ratio}
                    {isMotion(item) ? ' · motion' : ''}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )
      })}

      {lightbox && (
        <div
          className="lightbox-backdrop"
          role="presentation"
          onClick={() => setLightbox(null)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setLightbox(null)
          }}
        >
          <div
            className="lightbox-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Example creative"
            onClick={(e) => e.stopPropagation()}
          >
            {isMotion(lightbox) ? (
              <video
                src={mediaUrl(lightbox.url)}
                controls
                playsInline
                className="lightbox-media"
              />
            ) : (
              <img src={mediaUrl(lightbox.url)} alt="" className="lightbox-media" />
            )}
            <p>
              {lightbox.campaign_name} · {lightbox.product} · {lightbox.ratio}
            </p>
            <button type="button" className="btn-ghost" onClick={() => setLightbox(null)}>
              Close
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
