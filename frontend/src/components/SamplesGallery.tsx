import { useEffect, useMemo, useState } from 'react'
import {
  deleteCampaign,
  deleteCreatives,
  fetchGallery,
  generateMotion,
  getHealth,
  listPastCampaigns,
  outputUrl,
  publicUrl,
  revealCampaignFolder,
  thumbUrl,
  type GalleryCreative,
  type GalleryResponse,
  type PastCampaign,
} from '../lib/api'
import { formatApiError } from '../lib/errors'

function formatWhen(iso: string | null) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function stageLabel(stage: string, isDraft?: boolean) {
  if (isDraft || stage === 'draft') return 'Draft'
  if (stage === 'results') return 'Results'
  if (stage === 'finalize') return 'Finalize'
  if (stage === 'review') return 'Review'
  return stage
}

function isMotionItem(item: GalleryCreative) {
  return item.kind === 'motion' || item.url.toLowerCase().endsWith('.mp4')
}

function galleryItemKey(item: GalleryCreative) {
  return `${item.campaign_id}::${item.url}`
}

function galleryItemPath(item: GalleryCreative) {
  let path = item.url.replace(/\\/g, '/')
  if (path.startsWith('/pipeline/')) path = path.slice('/pipeline'.length)
  if (path.startsWith('/outputs/')) path = path.slice('/outputs/'.length)
  return path
}

function galleryMediaUrl(url: string) {
  return publicUrl(url.startsWith('/') ? url : `/${url}`)
}

function MotionThumb({ src }: { src: string }) {
  return (
    <video
      src={src}
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
          /* ignore seek errors */
        }
      }}
    />
  )
}

type LibraryView = 'campaigns' | 'gallery'

export function SamplesGallery({
  onOpenCampaign,
  desktopTools = true,
  guestMode = false,
  onSignUp,
}: {
  onOpenCampaign?: (campaignId: string) => void | Promise<void>
  desktopTools?: boolean
  /** Logged-out hosted browse: public examples only, no private campaigns. */
  guestMode?: boolean
  onSignUp?: () => void
}) {
  const [view, setView] = useState<LibraryView>('gallery')
  const [data, setData] = useState<GalleryResponse | null>(null)
  const [past, setPast] = useState<PastCampaign[]>([])
  const [campaignId, setCampaignId] = useState('')
  const [ratio, setRatio] = useState('')
  const [brand, setBrand] = useState('')
  const [kind, setKind] = useState('')
  const [lightbox, setLightbox] = useState<GalleryCreative | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [selectMode, setSelectMode] = useState(false)
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set())
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [motionAvailable, setMotionAvailable] = useState(false)
  const [lightboxMotionBusy, setLightboxMotionBusy] = useState(false)
  const [lightboxMotionError, setLightboxMotionError] = useState<string | null>(null)

  useEffect(() => {
    getHealth()
      .then((h) => setMotionAvailable(Boolean(h.motion_available)))
      .catch(() => setMotionAvailable(false))
  }, [])

  useEffect(() => {
    setLightboxMotionBusy(false)
    setLightboxMotionError(null)
  }, [lightbox])

  async function refreshPast() {
    try {
      const res = await listPastCampaigns()
      setPast(res.campaigns || [])
    } catch {
      setPast([])
    }
  }

  useEffect(() => {
    if (guestMode) {
      setView('gallery')
      setPast([])
      return
    }
    void refreshPast()
    const onFocus = () => void refreshPast()
    const onVis = () => {
      if (document.visibilityState === 'visible') void refreshPast()
    }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onVis)
    const timer = window.setInterval(() => {
      if (view === 'campaigns') void refreshPast()
    }, 4000)
    return () => {
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onVis)
      window.clearInterval(timer)
    }
  }, [view, guestMode])

  useEffect(() => {
    if (view !== 'gallery') return
    let cancelled = false

    async function loadGallery(showSpinner: boolean) {
      if (showSpinner) setLoading(true)
      try {
        const res = await fetchGallery({
          campaign_id: campaignId || undefined,
          ratio: ratio || undefined,
          brand: brand || undefined,
          kind: kind || undefined,
        })
        if (!cancelled) {
          setData(res)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError(formatApiError(err, 'Could not load gallery.'))
      } finally {
        if (!cancelled && showSpinner) setLoading(false)
      }
    }

    void loadGallery(true)
    const timer = window.setInterval(() => {
      void loadGallery(false)
    }, 4000)
    const onFocus = () => void loadGallery(false)
    const onVis = () => {
      if (document.visibilityState === 'visible') void loadGallery(false)
    }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onVis)
    return () => {
      cancelled = true
      window.clearInterval(timer)
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [view, campaignId, ratio, brand, kind])

  const creatives = data?.creatives || []
  const ratios = data?.filters.ratios || ['1:1', '9:16', '16:9']
  const brands = data?.filters.brands || []
  const campaignOptions = data?.filters.campaigns || data?.campaigns || []
  const hasMotionAnywhere = (data?.filters.kinds || []).includes('motion')

  const gridItems = useMemo(
    () =>
      [...creatives].sort((a, b) => {
        const motionDelta = Number(isMotionItem(b)) - Number(isMotionItem(a))
        if (motionDelta) return motionDelta
        return (a.product || '').localeCompare(b.product || '')
      }),
    [creatives],
  )

  const motionCount = useMemo(
    () => creatives.filter((c) => isMotionItem(c)).length,
    [creatives],
  )

  function toggleGallerySelected(item: GalleryCreative) {
    const key = galleryItemKey(item)
    setSelectedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function selectAllGallery() {
    setSelectedKeys(new Set(creatives.map(galleryItemKey)))
  }

  function clearGallerySelection() {
    setSelectedKeys(new Set())
  }

  async function handleDeleteSelectedCreatives() {
    const chosen = creatives.filter((c) => selectedKeys.has(galleryItemKey(c)))
    if (!chosen.length) return
    if (
      !window.confirm(
        `Delete ${chosen.length} creative${chosen.length === 1 ? '' : 's'} from disk? This cannot be undone.`,
      )
    ) {
      return
    }
    setDeleteBusy(true)
    setError(null)
    try {
      await deleteCreatives(
        chosen.map((c) => ({
          campaign_id: c.campaign_id,
          path: galleryItemPath(c),
        })),
      )
      clearGallerySelection()
      setSelectMode(false)
      setLightbox(null)
      const res = await fetchGallery({
        campaign_id: campaignId || undefined,
        ratio: ratio || undefined,
        brand: brand || undefined,
        kind: kind || undefined,
      })
      setData(res)
      await refreshPast()
    } catch (err) {
      setError(formatApiError(err, 'Could not delete those creatives.'))
    } finally {
      setDeleteBusy(false)
    }
  }

  async function handleOpen(id: string) {
    if (!onOpenCampaign) return
    setOpeningId(id)
    setError(null)
    try {
      await onOpenCampaign(id)
    } catch (err) {
      setError(formatApiError(err, 'Could not open that campaign.'))
    } finally {
      setOpeningId(null)
    }
  }

  async function handleLightboxGenerateMotion() {
    if (!lightbox || isMotionItem(lightbox) || !motionAvailable) return
    setLightboxMotionBusy(true)
    setLightboxMotionError(null)
    try {
      const result = await generateMotion(
        lightbox.campaign_id,
        galleryItemPath(lightbox),
        6,
      )
      const res = await fetchGallery({
        campaign_id: campaignId || undefined,
        ratio: ratio || undefined,
        brand: brand || undefined,
        kind: kind || undefined,
      })
      setData(res)
      const motionUrl = outputUrl(result.motion_path)
      setLightbox({
        ...lightbox,
        kind: 'motion',
        url: motionUrl,
        filename: motionUrl.split('/').pop() || 'creative.mp4',
      })
    } catch (err) {
      setLightboxMotionError(formatApiError(err, 'Could not generate motion.'))
    } finally {
      setLightboxMotionBusy(false)
    }
  }

  async function handleDelete(id: string, name: string) {
    if (!window.confirm(`Delete campaign "${name}" from disk? This cannot be undone.`)) return
    setDeletingId(id)
    setError(null)
    try {
      await deleteCampaign(id)
      await refreshPast()
      if (campaignId === id) setCampaignId('')
      // Drop gallery cache entries for deleted campaign
      setData((prev) =>
        prev
          ? {
              ...prev,
              creatives: (prev.creatives || []).filter((c) => c.campaign_id !== id),
              campaigns: (prev.campaigns || []).filter((c) => c.id !== id),
            }
          : prev,
      )
    } catch (err) {
      setError(formatApiError(err, 'Could not delete that campaign.'))
    } finally {
      setDeletingId(null)
    }
  }

  async function handleReveal(id?: string | null) {
    setError(null)
    try {
      await revealCampaignFolder(id)
    } catch (err) {
      setError(formatApiError(err, 'Could not open that folder.'))
    }
  }

  function showGalleryFor(id: string) {
    setCampaignId(id)
    setRatio('')
    setBrand('')
    setKind('')
    setView('gallery')
  }

  return (
    <div className="samples-gallery">
      {!guestMode && (
        <nav className="library-subtabs" aria-label="Library">
          <button
            type="button"
            className={view === 'campaigns' ? 'app-tab active' : 'app-tab'}
            onClick={() => setView('campaigns')}
          >
            Campaigns
          </button>
          <button
            type="button"
            className={view === 'gallery' ? 'app-tab active' : 'app-tab'}
            onClick={() => setView('gallery')}
          >
            Gallery
          </button>
        </nav>
      )}

      {guestMode && (
        <div className="library-guest-lead panel">
          <div>
            <h2 style={{ margin: '0 0 0.35rem' }}>Examples</h2>
            <p style={{ margin: 0, color: 'var(--muted)' }}>
              Demo campaign outputs you can browse before signing up. After you create an account,
              Library shows only your private runs.
            </p>
          </div>
          {onSignUp && (
            <button type="button" className="btn" onClick={onSignUp}>
              Sign up for free trial
            </button>
          )}
        </div>
      )}

      {error && <div className="banner banner-danger">{error}</div>}

      {!guestMode && view === 'campaigns' && (
        <div className="panel">
          <div className="library-panel-head">
            <h2>Campaigns</h2>
            <div className="action-row">
              <button type="button" className="btn-ghost" onClick={() => void refreshPast()}>
                Refresh
              </button>
              {desktopTools && (
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => void handleReveal(null)}
                >
                  Open local folder
                </button>
              )}
            </div>
          </div>
          {past.length === 0 ? (
            <p style={{ color: 'var(--muted)', marginBottom: 0 }}>
              No finished runs yet.
            </p>
          ) : (
            <div className="past-campaign-list">
              {past.map((c) => (
                <div key={c.id} className="past-campaign-row">
                  <div className="past-campaign-thumb">
                    {c.thumb_url ? (
                      <img
                        src={thumbUrl(c.thumb_url, 240)}
                        alt=""
                        loading="lazy"
                        decoding="async"
                      />
                    ) : (
                      <div className="past-campaign-placeholder" />
                    )}
                  </div>
                  <div className="past-campaign-info">
                    <strong>
                      {c.name}{' '}
                      {(c.is_draft || c.stage === 'draft') && (
                        <span className="pill-draft">Draft</span>
                      )}
                    </strong>
                    <span>
                      {c.brand ? `${c.brand} · ` : ''}
                      {c.creative_count} creatives · {stageLabel(c.stage, c.is_draft)}
                    </span>
                    <span className="past-campaign-when">{formatWhen(c.modified_at)}</span>
                  </div>
                  <div className="past-campaign-actions">
                    <button
                      type="button"
                      className="btn"
                      disabled={!onOpenCampaign || openingId === c.id}
                      onClick={() => void handleOpen(c.id)}
                    >
                      {openingId === c.id ? 'Opening…' : 'Open'}
                    </button>
                    {desktopTools && (
                      <button
                        type="button"
                        className="btn-ghost"
                        onClick={() => void handleReveal(c.id)}
                      >
                        Folder
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => showGalleryFor(c.id)}
                    >
                      Gallery
                    </button>
                    <button
                      type="button"
                      className="btn-ghost"
                      disabled={deletingId === c.id}
                      onClick={() => void handleDelete(c.id, c.name)}
                    >
                      {deletingId === c.id ? 'Deleting…' : 'Delete'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {(guestMode || view === 'gallery') && (
        <>
          <div className="panel" style={{ marginBottom: '1rem' }}>
            <div className="library-panel-head">
              <h2 style={{ margin: 0 }}>{guestMode ? 'Browse' : 'Gallery'}</h2>
              {!guestMode && (
                <div className="action-row">
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => {
                      setSelectMode((v) => !v)
                      clearGallerySelection()
                    }}
                  >
                    {selectMode ? 'Done selecting' : 'Select'}
                  </button>
                  {selectMode && (
                    <>
                      <button type="button" className="btn-ghost" onClick={selectAllGallery}>
                        Select all
                      </button>
                      <button
                        type="button"
                        className="btn-ghost"
                        disabled={!selectedKeys.size}
                        onClick={clearGallerySelection}
                      >
                        Clear
                      </button>
                      <button
                        type="button"
                        className="btn"
                        disabled={deleteBusy || !selectedKeys.size}
                        onClick={() => void handleDeleteSelectedCreatives()}
                      >
                        {deleteBusy ? 'Deleting…' : `Delete (${selectedKeys.size})`}
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
            <div className="gallery-filters gallery-filters-4">
              <label>
                Campaign
                <select
                  className="field"
                  value={campaignId}
                  onChange={(e) => setCampaignId(e.target.value)}
                >
                  <option value="">All campaigns</option>
                  {campaignOptions.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.creative_count})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Aspect ratio
                <select className="field" value={ratio} onChange={(e) => setRatio(e.target.value)}>
                  <option value="">All ratios</option>
                  {ratios.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Brand
                <select className="field" value={brand} onChange={(e) => setBrand(e.target.value)}>
                  <option value="">All brands</option>
                  {brands.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Media
                <select className="field" value={kind} onChange={(e) => setKind(e.target.value)}>
                  <option value="">Still + motion</option>
                  <option value="motion">Motion only</option>
                  <option value="still">Still only</option>
                </select>
              </label>
            </div>
            {hasMotionAnywhere && kind !== 'motion' && (
              <div className="action-row" style={{ marginTop: '0.75rem' }}>
                <button type="button" className="btn-ghost" onClick={() => setKind('motion')}>
                  Show motion only
                  {motionCount > 0 ? ` (${motionCount})` : ''}
                </button>
              </div>
            )}
          </div>

          {loading && <p className="muted-line">Loading gallery…</p>}
          {!loading && creatives.length === 0 && (
            <div className="panel">
              <p style={{ margin: 0, color: 'var(--muted)' }}>
                No creatives for these filters.
              </p>
            </div>
          )}

          {!loading && gridItems.length > 0 && (
            <div className="social-grid social-grid-library" aria-label="Gallery creatives">
              {gridItems.map((item, idx) => {
                const motion = isMotionItem(item)
                const key = galleryItemKey(item)
                const checked = selectedKeys.has(key)
                return (
                  <div
                    key={`${key}-${idx}`}
                    className={`social-grid-wrap${checked ? ' is-selected' : ''}`}
                  >
                    {!guestMode && selectMode && (
                      <label
                        className="results-select-check"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleGallerySelected(item)}
                          aria-label={`Select ${item.product}`}
                        />
                      </label>
                    )}
                    <button
                      type="button"
                      className="social-grid-cell"
                      onClick={() => {
                        if (!guestMode && selectMode) {
                          toggleGallerySelected(item)
                          return
                        }
                        setLightbox(item)
                      }}
                      aria-label={`${item.product} ${item.ratio}${motion ? ' motion' : ''}`}
                    >
                      {motion ? (
                        <MotionThumb src={galleryMediaUrl(item.url)} />
                      ) : (
                        <img
                          src={thumbUrl(item.url, 480)}
                          alt={`${item.campaign_name} ${item.product}`}
                          loading="lazy"
                          decoding="async"
                        />
                      )}
                      {motion && <span className="social-grid-badge">Motion</span>}
                      <span className="social-grid-caption">
                        {item.product} · {item.ratio}
                      </span>
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {lightbox && (
        <div
          className="lightbox lightbox-enter"
          role="dialog"
          aria-modal="true"
          onClick={() => setLightbox(null)}
        >
          <div className="lightbox-inner" onClick={(e) => e.stopPropagation()}>
            <div className="lightbox-head">
              <div>
                <strong>{lightbox.product}</strong>
                <div className="lightbox-sub">
                  {lightbox.campaign_name}
                  {lightbox.brand ? ` · ${lightbox.brand}` : ''} · {lightbox.ratio}
                  {isMotionItem(lightbox) ? ' · motion' : ''}
                </div>
              </div>
              <div className="action-row">
                {!guestMode && onOpenCampaign && (
                  <button
                    type="button"
                    className="btn"
                    onClick={() => void handleOpen(lightbox.campaign_id)}
                  >
                    Open campaign
                  </button>
                )}
                <button type="button" className="btn-ghost" onClick={() => setLightbox(null)}>
                  Close
                </button>
              </div>
            </div>
            {isMotionItem(lightbox) ? (
              <video
                src={galleryMediaUrl(lightbox.url)}
                controls
                playsInline
                className="lightbox-media"
              />
            ) : (
              <img
                src={galleryMediaUrl(lightbox.url)}
                alt={lightbox.product}
                className="lightbox-media"
              />
            )}
            {lightboxMotionError && (
              <div className="banner banner-danger">{lightboxMotionError}</div>
            )}
            <div className="action-row" style={{ marginTop: '0.75rem' }}>
              <a
                className="btn-ghost"
                href={galleryMediaUrl(lightbox.url)}
                target="_blank"
                rel="noreferrer"
              >
                {isMotionItem(lightbox) ? 'Open / download video' : 'Open full size'}
              </a>
              {!guestMode && !isMotionItem(lightbox) && motionAvailable && (
                <button
                  type="button"
                  className="btn"
                  disabled={lightboxMotionBusy}
                  onClick={() => void handleLightboxGenerateMotion()}
                >
                  {lightboxMotionBusy ? 'Generating motion…' : 'Generate motion'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
