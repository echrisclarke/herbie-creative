import { useEffect, useMemo, useState } from 'react'
import type { CreativeResult, Report } from '../lib/api'
import { deleteCreatives, fetchReport, outputThumbUrl, outputUrl } from '../lib/api'
import { cssAspectRatio } from '../lib/aspectExamples'
import type { CreativePlan } from '../lib/creativeCounts'
import type { MotionJob } from '../lib/motionJobs'
import { DetailModal } from './DetailModal'
import { PipelineCountBanner } from './PipelineCountBanner'

type ResultTile = {
  id: string
  kind: 'still' | 'motion'
  product: string
  ratio: string
  locale: string
  source: string
  compliance: Record<string, boolean>
  mediaPath: string
  creative: CreativeResult
}

const BASE_RATIOS = ['1:1', '9:16', '16:9'] as const

/** Frame path for this row (locale finals keep their own final.*.png, not the shared creative). */
function stillSource(c: CreativeResult) {
  const path = String(c.path || '').replace(/\\/g, '/')
  if (path && !path.toLowerCase().endsWith('.mp4')) return path
  return String(c.creative_path || c.path || '').replace(/\\/g, '/')
}

function baseRatio(raw: string): string {
  const text = (raw || '').toLowerCase().replace('x', ':')
  if (text.startsWith('9:16')) return '9:16'
  if (text.startsWith('16:9')) return '16:9'
  if (text.startsWith('1:1')) return '1:1'
  return raw
}

function isFinalStillPath(path: string) {
  const p = path.toLowerCase()
  return p.includes('/final.') || /(^|\/)final\./.test(p) || /(^|\/)final\.tight\./.test(p)
}

function isMotionEligibleStill(c: CreativeResult) {
  const path = stillSource(c).toLowerCase()
  if (!path || path.endsWith('.mp4')) return false
  if ((c.locale || '') === 'motion') return false
  // No-text creatives and finalized (with-text) stills are both valid motion sources.
  if (isFinalStillPath(path)) return true
  return (c.locale || '') === 'creative' || path.includes('creative')
}

function preferStill(a: CreativeResult, b: CreativeResult) {
  const ap = String(a.path || '').toLowerCase()
  const bp = String(b.path || '').toLowerCase()
  const aScore =
    (ap.endsWith('creative.png') ? 3 : 0) +
    (ap.includes('creative.tight') ? 1 : 0) +
    (ap.includes('creative') ? 1 : 0) +
    (isFinalStillPath(ap) ? 2 : 0)
  const bScore =
    (bp.endsWith('creative.png') ? 3 : 0) +
    (bp.includes('creative.tight') ? 1 : 0) +
    (bp.includes('creative') ? 1 : 0) +
    (isFinalStillPath(bp) ? 2 : 0)
  return bScore - aScore
}

function expandTiles(creatives: CreativeResult[]): ResultTile[] {
  const tiles: ResultTile[] = []
  for (const c of creatives) {
    const path = String(c.path || '')
    const motionPath = c.motion_path ? String(c.motion_path) : null
    const pathIsVideo = path.toLowerCase().endsWith('.mp4')

    if (!pathIsVideo) {
      tiles.push({
        id: `still:${path}:${c.locale || ''}`,
        kind: 'still',
        product: c.product,
        ratio: c.ratio,
        locale: c.locale || 'creative',
        source: c.source,
        compliance: c.compliance || {},
        mediaPath: path,
        creative: { ...c, motion_path: null },
      })
    }

    const videoPath = motionPath || (pathIsVideo ? path : null)
    if (videoPath) {
      tiles.push({
        id: `motion:${videoPath}`,
        kind: 'motion',
        product: c.product,
        ratio: c.ratio,
        locale: 'motion',
        source: c.source,
        compliance: c.compliance || {},
        mediaPath: videoPath,
        creative: {
          ...c,
          path: videoPath,
          locale: 'motion',
          motion_path: videoPath,
        },
      })
    }
  }
  const seen = new Set<string>()
  return tiles.filter((t) => {
    if (t.kind !== 'motion') return true
    const key = t.mediaPath.replace(/\\/g, '/').toLowerCase()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function PlayOverlayThumb({ src }: { src: string }) {
  return (
    <div className="playable-video-thumb">
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
            /* ignore */
          }
        }}
      />
      <span className="play-button" aria-hidden>
        ▶
      </span>
    </div>
  )
}

export function ResultsStep({
  report,
  campaignId,
  briefOutputs,
  briefFraming = 'both',
  plan = null,
  imageQuality = 'medium',
  motionJobs = [],
  onRestart,
  onBrowsePast,
  onFinalize,
  onMotion,
  onReportUpdate,
  onGenerateMore,
}: {
  report: Report
  campaignId: string
  briefOutputs?: string[]
  briefFraming?: 'close-up' | 'zoomed' | 'both'
  plan?: CreativePlan | null
  imageQuality?: 'low' | 'medium' | 'high'
  motionJobs?: MotionJob[]
  onRestart: () => void
  onBrowsePast?: () => void
  onFinalize?: () => void
  onMotion?: () => void
  onReportUpdate?: (report: Report) => void
  onGenerateMore?: (opts: {
    outputs: string[]
    framing: 'close-up' | 'zoomed' | 'both'
    imageQuality: 'low' | 'medium' | 'high'
    useSourceStills: boolean
    sourcePaths: string[]
  }) => void | Promise<void>
}) {
  const [selected, setSelected] = useState<ResultTile | null>(null)
  const [moreRatios, setMoreRatios] = useState<string[]>([])
  const [moreFraming, setMoreFraming] = useState<'close-up' | 'zoomed' | 'both'>(briefFraming)
  const [moreQuality, setMoreQuality] = useState<'low' | 'medium' | 'high'>(imageQuality)
  const [moreBusy, setMoreBusy] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)
  const [useSourceStills, setUseSourceStills] = useState(true)
  const [sourcePaths, setSourcePaths] = useState<string[]>([])
  const [selectMode, setSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set())
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function refreshFromDisk() {
      try {
        const next = await fetchReport(campaignId)
        if (!cancelled) onReportUpdate?.(next)
      } catch {
        /* keep current report if refresh fails */
      }
    }
    void refreshFromDisk()
    const onFocus = () => void refreshFromDisk()
    window.addEventListener('focus', onFocus)
    return () => {
      cancelled = true
      window.removeEventListener('focus', onFocus)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId])

  const tiles = useMemo(() => expandTiles(report.creatives), [report.creatives])
  const motionTiles = useMemo(() => tiles.filter((t) => t.kind === 'motion'), [tiles])
  const stillTiles = useMemo(() => tiles.filter((t) => t.kind === 'still'), [tiles])
  const hasMotion = motionTiles.length > 0
  const activeMotionJobs = useMemo(
    () => motionJobs.filter((j) => j.status !== 'done'),
    [motionJobs],
  )
  const motionInFlight = useMemo(
    () => activeMotionJobs.filter((j) => j.status === 'queued' || j.status === 'running'),
    [activeMotionJobs],
  )
  const motionRunningIndex = useMemo(() => {
    const running = activeMotionJobs.findIndex((j) => j.status === 'running')
    if (running >= 0) return running + 1
    const queued = activeMotionJobs.findIndex((j) => j.status === 'queued')
    return queued >= 0 ? queued + 1 : 0
  }, [activeMotionJobs])
  const showMotionSection = hasMotion || activeMotionJobs.length > 0
  const finalStillCount = useMemo(
    () => stillTiles.filter((t) => isFinalStillPath(stillSource(t.creative))).length,
    [stillTiles],
  )
  const creativeStillCount = stillTiles.length - finalStillCount

  const sourceStillOptions = useMemo(() => {
    const byPath = new Map<string, ResultTile>()
    for (const tile of stillTiles) {
      const path = stillSource(tile.creative)
      if (!path || path.toLowerCase().endsWith('.mp4')) continue
      const key = path.replace(/\\/g, '/').toLowerCase()
      const prev = byPath.get(key)
      if (!prev || preferStill(tile.creative, prev.creative) < 0) {
        byPath.set(key, tile)
      }
    }
    return Array.from(byPath.values()).sort((a, b) =>
      baseRatio(a.ratio).localeCompare(baseRatio(b.ratio)),
    )
  }, [stillTiles])

  useEffect(() => {
    const available = new Set(sourceStillOptions.map((t) => stillSource(t.creative)))
    setSourcePaths((prev) => prev.filter((p) => available.has(p)))
  }, [sourceStillOptions])

  const existingStillRatios = useMemo(() => {
    const set = new Set<string>()
    for (const c of report.creatives) {
      if (!isMotionEligibleStill(c)) continue
      const ratio = baseRatio(c.ratio)
      if (BASE_RATIOS.includes(ratio as (typeof BASE_RATIOS)[number])) set.add(ratio)
    }
    return set
  }, [report.creatives])

  useEffect(() => {
    const missing = BASE_RATIOS.filter((r) => !existingStillRatios.has(r))
    const seed =
      missing.length > 0
        ? missing
        : (briefOutputs || []).filter((r) =>
            BASE_RATIOS.includes(r as (typeof BASE_RATIOS)[number]),
          )
    if (moreRatios.length === 0) {
      setMoreRatios(seed.length ? [...seed] : ['9:16', '16:9'])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [[...existingStillRatios].join('|'), (briefOutputs || []).join('|')])

  function togglePath(list: string[], path: string) {
    return list.includes(path) ? list.filter((p) => p !== path) : [...list, path]
  }

  function renderStillPickerGrid(
    options: ResultTile[],
    selectedPaths: string[],
    onChange: (next: string[]) => void,
    disabled: boolean,
  ) {
    return (
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))',
          gap: '0.55rem',
        }}
      >
        {options.map((tile) => {
          const path = stillSource(tile.creative)
          const on = selectedPaths.includes(path)
          const hasMotion = Boolean(tile.creative.motion_path)
          return (
            <button
              key={tile.id}
              type="button"
              className="btn-ghost"
              disabled={disabled}
              onClick={() => onChange(togglePath(selectedPaths, path))}
              style={{
                padding: 0,
                overflow: 'hidden',
                textAlign: 'left',
                borderColor: on ? 'var(--accent)' : 'var(--border)',
                background: on ? 'var(--accent-soft)' : 'var(--panel)',
                opacity: on ? 1 : 0.55,
              }}
            >
              <div
                style={{
                  aspectRatio: cssAspectRatio(baseRatio(tile.ratio)),
                  background: '#151515',
                }}
              >
                <img
                  src={outputThumbUrl(path, 360)}
                  alt={`${tile.product} ${tile.ratio}`}
                  loading="lazy"
                  decoding="async"
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              </div>
              <div style={{ padding: '0.35rem 0.45rem', fontSize: '0.78rem' }}>
                {baseRatio(tile.ratio)}
                {String(tile.ratio).includes('tight') ||
                String(path).toLowerCase().includes('tight')
                  ? ' · close-up'
                  : ''}
                {isFinalStillPath(path)
                  ? ' · with text'
                  : tile.locale && tile.locale !== 'creative'
                    ? ` · ${tile.locale}`
                    : ''}
                {hasMotion ? ' · has motion' : ''}
              </div>
            </button>
          )
        })}
      </div>
    )
  }

  async function handleGenerateMoreStills() {
    if (!onGenerateMore || moreRatios.length === 0) return
    if (useSourceStills && sourcePaths.length === 0) {
      setMoreError('Select at least one source still, or turn off “Use existing stills as source”.')
      return
    }
    setMoreBusy(true)
    setMoreError(null)
    try {
      await onGenerateMore({
        outputs: moreRatios,
        framing: moreFraming,
        imageQuality: moreQuality,
        useSourceStills,
        sourcePaths: useSourceStills ? sourcePaths : [],
      })
    } catch (err) {
      setMoreError(err instanceof Error ? err.message : String(err))
    } finally {
      setMoreBusy(false)
    }
  }

  function toggleSelected(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function selectAllVisible() {
    setSelectedIds(new Set(tiles.map((t) => t.id)))
  }

  function clearSelection() {
    setSelectedIds(new Set())
  }

  async function handleDeleteSelected() {
    const chosen = tiles.filter((t) => selectedIds.has(t.id))
    if (!chosen.length) return
    if (
      !window.confirm(
        `Delete ${chosen.length} creative${chosen.length === 1 ? '' : 's'} from disk? This cannot be undone.`,
      )
    ) {
      return
    }
    setDeleteBusy(true)
    setActionError(null)
    try {
      await deleteCreatives(
        chosen.map((t) => ({
          campaign_id: campaignId,
          path: t.mediaPath,
        })),
      )
      const refreshed = await fetchReport(campaignId)
      onReportUpdate?.(refreshed)
      clearSelection()
      setSelectMode(false)
      setSelected(null)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setDeleteBusy(false)
    }
  }

  function renderCard(tile: ResultTile) {
    const isChecked = selectedIds.has(tile.id)
    return (
      <div
        key={tile.id}
        className={`results-card${isChecked ? ' is-selected' : ''}`}
      >
        {selectMode && (
          <label className="results-select-check" onClick={(e) => e.stopPropagation()}>
            <input
              type="checkbox"
              checked={isChecked}
              onChange={() => toggleSelected(tile.id)}
              aria-label={`Select ${tile.product} ${tile.ratio}`}
            />
          </label>
        )}
        <button
          type="button"
          className="panel results-card-btn"
          style={{ padding: 0, overflow: 'hidden', textAlign: 'left', width: '100%' }}
          onClick={() => {
            if (selectMode) {
              toggleSelected(tile.id)
              return
            }
            setSelected(tile)
          }}
        >
          <div
            className="results-thumb"
            style={{
              aspectRatio: cssAspectRatio(tile.ratio),
              background: '#111',
              position: 'relative',
            }}
          >
            {tile.kind === 'motion' ? (
              <PlayOverlayThumb src={outputUrl(tile.mediaPath)} />
            ) : (
              <img
                src={outputThumbUrl(tile.mediaPath, 480)}
                alt={`${tile.product} ${tile.ratio}`}
                loading="lazy"
                decoding="async"
                style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
              />
            )}
            {tile.kind === 'motion' && <span className="motion-badge">Motion</span>}
          </div>
          <div style={{ padding: '0.65rem' }}>
            <div style={{ fontSize: '0.9rem' }}>
              {tile.product} · {tile.ratio}
              {tile.locale ? ` · ${tile.locale}` : ''}
            </div>
            <div style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>{tile.source}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--ok)' }}>
              compliance{' '}
              {Object.values(tile.compliance || {}).every(Boolean) ? 'ok' : 'check'}
            </div>
          </div>
        </button>
      </div>
    )
  }

  return (
    <section className="panel step-panel" style={{ padding: '1.5rem' }}>
      <div className="library-panel-head">
        <div>
          <h2 style={{ marginTop: 0, marginBottom: '0.25rem' }}>Results</h2>
          <PipelineCountBanner plan={plan} />
          <p style={{ color: 'var(--muted)', margin: '0.35rem 0 0' }}>
            On disk: {finalStillCount} final{finalStillCount === 1 ? '' : 's'}
            {' · '}
            {creativeStillCount} no-text
            {hasMotion ? ` · ${motionTiles.length} motion` : ''}
            {motionInFlight.length
              ? ` · ${motionInFlight.length} motion generating`
              : ''}
          </p>
        </div>
        <div className="action-row">
          <button
            type="button"
            className="btn-ghost"
            onClick={() => {
              setSelectMode((v) => !v)
              clearSelection()
            }}
          >
            {selectMode ? 'Done selecting' : 'Select'}
          </button>
          {selectMode && (
            <>
              <button type="button" className="btn-ghost" onClick={selectAllVisible}>
                Select all
              </button>
              <button
                type="button"
                className="btn-ghost"
                disabled={!selectedIds.size}
                onClick={clearSelection}
              >
                Clear
              </button>
              <button
                type="button"
                className="btn"
                disabled={deleteBusy || !selectedIds.size}
                onClick={() => void handleDeleteSelected()}
              >
                {deleteBusy ? 'Deleting…' : `Delete (${selectedIds.size})`}
              </button>
            </>
          )}
        </div>
      </div>

      {showMotionSection && (
        <div className="results-motion-section" style={{ marginBottom: '1.25rem' }}>
          <div className="results-motion-head">
            <h3 style={{ margin: 0 }}>Motion</h3>
            {motionInFlight.length > 0 && (
              <span className="results-motion-progress">
                {motionRunningIndex > 0
                  ? `Generating ${motionRunningIndex} of ${activeMotionJobs.length}`
                  : `Queued ${motionInFlight.length}`}
              </span>
            )}
          </div>
          {motionInFlight.length > 0 && (
            <div className="banner results-motion-banner">
              Motion clips are rendering in the background. Stills below stay available. You can
              generate more from the Motion step anytime.
            </div>
          )}
          <div className="results-grid">
            {activeMotionJobs.map((job, idx) => (
              <div
                key={job.id}
                className={`results-card motion-job-card is-${job.status}`}
              >
                <div
                  className="panel results-card-btn"
                  style={{ padding: 0, overflow: 'hidden', width: '100%' }}
                >
                  <div
                    className="results-thumb motion-job-thumb"
                    style={{
                      aspectRatio: cssAspectRatio(baseRatio(job.ratio)),
                      background: '#111',
                      position: 'relative',
                    }}
                  >
                    <img
                      src={outputThumbUrl(job.sourcePath, 360)}
                      alt=""
                      loading="lazy"
                      decoding="async"
                      style={{
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover',
                        display: 'block',
                        opacity: 0.32,
                      }}
                    />
                    <div className="motion-job-overlay">
                      <div className="motion-job-spinner" aria-hidden />
                      <div className="motion-job-status">
                        {job.status === 'error'
                          ? 'Failed'
                          : job.status === 'running'
                            ? `Generating ${idx + 1}/${activeMotionJobs.length}…`
                            : `Queued ${idx + 1}/${activeMotionJobs.length}`}
                      </div>
                    </div>
                  </div>
                  <div style={{ padding: '0.65rem' }}>
                    <div style={{ fontSize: '0.9rem' }}>
                      {job.product} · {baseRatio(job.ratio)}
                    </div>
                    <div style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>
                      {job.status === 'error'
                        ? job.error || 'Motion failed'
                        : 'Motion placeholder · still source above'}
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {motionTiles.map(renderCard)}
          </div>
        </div>
      )}

      {stillTiles.length > 0 && (
        <div>
          <h3 style={{ margin: '0 0 0.65rem' }}>
            {showMotionSection ? 'Stills' : 'Creatives'}
          </h3>
          <div className="results-grid">{stillTiles.map(renderCard)}</div>
        </div>
      )}

      {onGenerateMore && (
        <div className="panel" style={{ marginTop: '1.25rem', padding: '1rem' }}>
          <h3 style={{ marginTop: 0 }}>Generate more stills</h3>
          <p style={{ color: 'var(--muted)', marginTop: 0 }}>
            Add or regenerate aspect ratios for this campaign. Existing files for a selected
            ratio are replaced. Disk sync keeps other ratios you already have.
          </p>
          <label
            style={{
              display: 'flex',
              gap: '0.5rem',
              alignItems: 'flex-start',
              marginBottom: '0.75rem',
              color: 'var(--text)',
            }}
          >
            <input
              type="checkbox"
              checked={useSourceStills}
              disabled={moreBusy || sourceStillOptions.length === 0}
              onChange={(e) => setUseSourceStills(e.target.checked)}
              style={{ marginTop: '0.2rem' }}
            />
            <span>
              Use existing stills as source
              <span style={{ display: 'block', color: 'var(--muted)', fontSize: '0.85rem' }}>
                Keeps the same look by reframing the selected stills into new ratios. Turn off to
                invent new concepts from the brief and product refs.
              </span>
            </span>
          </label>
          {useSourceStills && sourceStillOptions.length > 0 && (
            <details className="intake-collapse" style={{ marginBottom: '0.95rem' }}>
              <summary>
                Source stills
                {sourcePaths.length
                  ? ` (${sourcePaths.length} selected)`
                  : ' (none selected)'}
              </summary>
              <div style={{ marginTop: '0.65rem' }}>
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '0.45rem',
                    marginBottom: '0.55rem',
                  }}
                >
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={moreBusy}
                    onClick={() =>
                      setSourcePaths(sourceStillOptions.map((t) => stillSource(t.creative)))
                    }
                  >
                    Select all
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={moreBusy || sourcePaths.length === 0}
                    onClick={() => setSourcePaths([])}
                  >
                    Deselect all
                  </button>
                </div>
                {renderStillPickerGrid(
                  sourceStillOptions,
                  sourcePaths,
                  setSourcePaths,
                  moreBusy,
                )}
              </div>
            </details>
          )}
          <div style={{ color: 'var(--muted)', marginBottom: '0.45rem' }}>Aspect ratios</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem', marginBottom: '0.85rem' }}>
            <button
              type="button"
              className="btn-ghost"
              disabled={moreBusy}
              style={{
                borderColor:
                  moreRatios.length === BASE_RATIOS.length ? 'var(--accent)' : 'var(--border)',
                background:
                  moreRatios.length === BASE_RATIOS.length ? 'var(--accent-soft)' : 'transparent',
              }}
              onClick={() => setMoreRatios([...BASE_RATIOS])}
            >
              All
            </button>
            {BASE_RATIOS.map((ratio) => {
              const on = moreRatios.includes(ratio)
              const have = existingStillRatios.has(ratio)
              return (
                <button
                  key={ratio}
                  type="button"
                  className="btn-ghost"
                  disabled={moreBusy}
                  style={{
                    borderColor: on ? 'var(--accent)' : 'var(--border)',
                    background: on ? 'var(--accent-soft)' : 'transparent',
                  }}
                  onClick={() =>
                    setMoreRatios((prev) =>
                      prev.includes(ratio)
                        ? prev.filter((r) => r !== ratio)
                        : [...prev, ratio],
                    )
                  }
                >
                  {ratio}
                  {have ? ' · have still' : ' · new'}
                </button>
              )
            })}
          </div>
          <div style={{ color: 'var(--muted)', marginBottom: '0.45rem' }}>
            Framing (first selected ratio)
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem', marginBottom: '0.85rem' }}>
            {(
              [
                { id: 'both' as const, label: 'Both' },
                { id: 'close-up' as const, label: 'Close-up' },
                { id: 'zoomed' as const, label: 'Zoomed out' },
              ] as const
            ).map((opt) => (
              <button
                key={opt.id}
                type="button"
                className="btn-ghost"
                disabled={moreBusy}
                style={{
                  borderColor: moreFraming === opt.id ? 'var(--accent)' : 'var(--border)',
                  background: moreFraming === opt.id ? 'var(--accent-soft)' : 'transparent',
                }}
                onClick={() => setMoreFraming(opt.id)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <label style={{ display: 'block', marginBottom: '0.85rem', color: 'var(--muted)' }}>
            Image quality
            <select
              className="field"
              value={moreQuality}
              disabled={moreBusy}
              onChange={(e) =>
                setMoreQuality(e.target.value as 'low' | 'medium' | 'high')
              }
              style={{ marginTop: '0.35rem', maxWidth: 220 }}
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </label>
          {moreError && <div className="banner banner-danger">{moreError}</div>}
          <button
            className="btn"
            type="button"
            disabled={
              moreBusy ||
              moreRatios.length === 0 ||
              (useSourceStills && sourcePaths.length === 0)
            }
            onClick={() => void handleGenerateMoreStills()}
          >
            {moreBusy
              ? 'Starting…'
              : `Generate stills (${moreRatios.join(', ') || 'none'})`}
          </button>
        </div>
      )}

      {actionError && <div className="banner banner-danger">{actionError}</div>}

      <footer className="action-row" style={{ marginTop: '1.5rem' }}>
        {onBrowsePast && (
          <button className="btn-ghost" type="button" onClick={onBrowsePast}>
            Browse past campaigns
          </button>
        )}
        {onMotion && (
          <button
            className={motionInFlight.length ? 'btn-ghost' : 'btn'}
            type="button"
            onClick={onMotion}
          >
            {hasMotion || activeMotionJobs.length
              ? 'Generate more motion'
              : 'Generate motion'}
          </button>
        )}
        {onFinalize && (
          <button className="btn-ghost" type="button" onClick={onFinalize}>
            Re-finalize
          </button>
        )}
        <a className="btn-ghost" href={`/campaigns/${campaignId}/report.json`} download>
          Download JSON
        </a>
        <a className="btn-ghost" href={`/campaigns/${campaignId}/report.md`} download>
          Download MD
        </a>
        <button className="btn" type="button" onClick={onRestart}>
          Start new campaign
        </button>
      </footer>

      {selected && (
        <DetailModal
          creative={selected.creative}
          kind={selected.kind}
          onClose={() => setSelected(null)}
          onAnimate={onMotion}
        />
      )}
    </section>
  )
}
