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
            Sample outputs from demo campaigns. Sign up to run your own pipeline and keep a private
            library.
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
              {items.length} still{items.length === 1 ? '' : 's'}
            </p>
            <div className="public-examples-grid">
              {items.map((item) => (
                <button
                  key={item.url}
                  type="button"
                  className="public-examples-card"
                  onClick={() => setLightbox(item)}
                >
                  <img src={mediaUrl(item.url)} alt="" loading="lazy" />
                  <span>
                    {item.product} · {item.ratio}
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
            <img src={mediaUrl(lightbox.url)} alt="" className="lightbox-media" />
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
