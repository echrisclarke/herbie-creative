import { useEffect, useState } from 'react'
import {
  fetchPublicGallery,
  publicUrl,
  thumbUrl,
  type GalleryCreative,
} from '../lib/api'

function isMotion(item: GalleryCreative) {
  return item.kind === 'motion' || item.url.toLowerCase().endsWith('.mp4')
}

function pickProof(creatives: GalleryCreative[], limit = 9): GalleryCreative[] {
  const stills = creatives.filter((c) => !isMotion(c))
  if (stills.length >= limit) return stills.slice(0, limit)
  const seen = new Set(stills.map((c) => c.url))
  const filled = [...stills]
  for (const item of creatives) {
    if (filled.length >= limit) break
    if (seen.has(item.url)) continue
    seen.add(item.url)
    filled.push(item)
  }
  return filled
}

export function AboutPage({
  onBrowseLibrary,
  onSignUp,
}: {
  onBrowseLibrary?: () => void
  onSignUp?: () => void
}) {
  const [proof, setProof] = useState<GalleryCreative[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    let cancelled = false
    void fetchPublicGallery()
      .then((data) => {
        if (cancelled) return
        setProof(pickProof(data.creatives || [], 9))
        setLoadError(false)
      })
      .catch(() => {
        if (cancelled) return
        setProof([])
        setLoadError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

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

      <div className="about-proof">
        <div className="about-proof-head">
          <h2>Examples</h2>
          {onBrowseLibrary && (
            <button type="button" className="text-link" onClick={onBrowseLibrary}>
              See all in Library
            </button>
          )}
        </div>

        {loading && <p className="muted-line">Loading examples…</p>}

        {!loading && loadError && (
          <p className="muted-line">
            Could not load preview images.
            {onBrowseLibrary ? (
              <>
                {' '}
                <button type="button" className="text-link" onClick={onBrowseLibrary}>
                  Open Library
                </button>
              </>
            ) : null}
          </p>
        )}

        {!loading && !loadError && proof.length === 0 && (
          <p className="muted-line">
            No preview images yet.
            {onBrowseLibrary ? (
              <>
                {' '}
                <button type="button" className="text-link" onClick={onBrowseLibrary}>
                  Open Library
                </button>
              </>
            ) : null}
          </p>
        )}

        {proof.length > 0 && (
          <div className="social-grid social-grid-proof" aria-label="Examples">
            {proof.map((item) =>
              isMotion(item) ? (
                <button
                  key={item.url}
                  type="button"
                  className="social-grid-cell"
                  onClick={onBrowseLibrary}
                  aria-label={`${item.product} ${item.ratio} motion`}
                >
                  <video
                    src={publicUrl(item.url.startsWith('/') ? item.url : `/${item.url}`)}
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
                  <span className="social-grid-badge">Motion</span>
                </button>
              ) : (
                <button
                  key={item.url}
                  type="button"
                  className="social-grid-cell"
                  onClick={onBrowseLibrary}
                  aria-label={`${item.product} ${item.ratio}`}
                >
                  <img
                    src={thumbUrl(item.url, 360)}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    onError={(e) => {
                      e.currentTarget.onerror = null
                      e.currentTarget.src = publicUrl(
                        item.url.startsWith('/') ? item.url : `/${item.url}`,
                      )
                    }}
                  />
                </button>
              ),
            )}
          </div>
        )}
      </div>
    </section>
  )
}
