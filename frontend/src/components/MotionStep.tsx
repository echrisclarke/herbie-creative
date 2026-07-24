import { useEffect, useMemo, useState } from 'react'
import type { Brief, CreativeResult, Report } from '../lib/api'
import { outputThumbUrl, saveCampaign } from '../lib/api'
import { cssAspectRatio } from '../lib/aspectExamples'
import { planCreativeCounts } from '../lib/creativeCounts'
import type { MotionGenerateRequest } from '../lib/motionJobs'
import { PipelineCountBanner } from './PipelineCountBanner'

/** Frame to animate: use the row's own still path so each locale/final stays distinct. */
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
  if (isFinalStillPath(path)) return true
  return (c.locale || '') === 'creative' || path.includes('creative')
}

function compareStills(a: CreativeResult, b: CreativeResult) {
  const ap = stillSource(a)
  const bp = stillSource(b)
  return (
    a.product.localeCompare(b.product) ||
    baseRatio(a.ratio).localeCompare(baseRatio(b.ratio)) ||
    String(a.ratio).localeCompare(String(b.ratio)) ||
    String(a.locale || '').localeCompare(String(b.locale || '')) ||
    ap.localeCompare(bp)
  )
}

function fileLabel(path: string) {
  return path.replace(/\\/g, '/').split('/').pop() || path
}

function StillPickGrid({
  options,
  selectedPaths,
  onToggle,
  disabled,
}: {
  options: CreativeResult[]
  selectedPaths: string[]
  onToggle: (path: string) => void
  disabled?: boolean
}) {
  return (
    <div className="motion-still-grid">
      {options.map((c) => {
        const path = stillSource(c)
        const on = selectedPaths.includes(path)
        const hasMotion = Boolean(c.motion_path)
        return (
          <button
            key={path}
            type="button"
            className={`motion-still-pick${on ? ' is-on' : ''}`}
            disabled={disabled}
            aria-pressed={on}
            onClick={() => onToggle(path)}
          >
            <div
              className="motion-still-thumb"
              style={{ aspectRatio: cssAspectRatio(baseRatio(c.ratio)) }}
            >
              <img src={outputThumbUrl(path, 360)} alt="" loading="lazy" decoding="async" />
              {on && <span className="motion-still-check" aria-hidden>✓</span>}
            </div>
            <div className="motion-still-meta">
              {c.product} · {baseRatio(c.ratio)}
              {String(c.ratio).includes('tight') || path.toLowerCase().includes('tight')
                ? ' · close-up'
                : String(c.ratio).includes('zoomed')
                  ? ' · zoomed'
                  : ''}
              {c.locale && c.locale !== 'creative' ? ` · ${c.locale}` : ''}
              {isFinalStillPath(path) ? ' · with text' : ' · creative'}
              {hasMotion ? ' · has motion' : ''}
            </div>
          </button>
        )
      })}
    </div>
  )
}

export function MotionStep({
  campaignId,
  report,
  brief,
  setBrief,
  motionAvailable = false,
  entry = 'ask',
  generating = false,
  onGenerate,
  onBack,
  onDone,
  onUploadAssets,
}: {
  campaignId: string
  report: Report
  brief: Brief
  setBrief: (b: Brief) => void
  motionAvailable?: boolean
  /** ask = yes/no gate first; settings = jump straight to motion controls (e.g. from Results). */
  entry?: 'ask' | 'settings'
  generating?: boolean
  onGenerate: (req: MotionGenerateRequest) => void | Promise<void>
  onBack: () => void
  onDone: () => void
  onUploadAssets?: (files: File[], roles?: string[]) => Promise<void>
}) {
  const [phase, setPhase] = useState<'ask' | 'settings'>(entry)
  const [motionError, setMotionError] = useState<string | null>(null)
  const [motionDuration, setMotionDuration] = useState(6)
  const [motionPrompt, setMotionPrompt] = useState(brief.motion_notes || '')
  const [promptExtra, setPromptExtra] = useState('')
  const [motionSourcePaths, setMotionSourcePaths] = useState<string[]>([])
  const [likenessPath, setLikenessPath] = useState(
    brief.likeness_reference_paths?.[0] || '',
  )
  const [styleRefPaths, setStyleRefPaths] = useState<string[]>(
    brief.style_reference_paths || [],
  )
  const motionBusy = generating

  useEffect(() => {
    setPhase(entry)
  }, [entry, campaignId])

  useEffect(() => {
    setMotionPrompt(brief.motion_notes || '')
    setLikenessPath(brief.likeness_reference_paths?.[0] || '')
    setStyleRefPaths(brief.style_reference_paths || [])
  }, [campaignId, brief.motion_notes, brief.likeness_reference_paths, brief.style_reference_paths])

  const motionStillOptions = useMemo(() => {
    // One option per unique still path: creatives, close-ups, and every locale final.
    const byPath = new Map<string, CreativeResult>()
    for (const c of report.creatives) {
      if (!isMotionEligibleStill(c)) continue
      const path = stillSource(c)
      if (!path) continue
      const key = path.toLowerCase()
      if (!byPath.has(key)) byPath.set(key, c)
    }
    return Array.from(byPath.values()).sort(compareStills)
  }, [report.creatives])

  useEffect(() => {
    const available = new Set(motionStillOptions.map((t) => stillSource(t)))
    setMotionSourcePaths((prev) => prev.filter((p) => available.has(p)))
  }, [motionStillOptions])

  const selectedTargets = useMemo(() => {
    const selected = new Set(motionSourcePaths)
    return motionStillOptions.filter((t) => selected.has(stillSource(t)))
  }, [motionStillOptions, motionSourcePaths])

  const selectedCount = selectedTargets.length

  const likenessOptions = useMemo(() => {
    const paths = [
      ...(brief.likeness_reference_paths || []),
      ...(brief.style_reference_paths || []),
    ]
    return [...new Set(paths.filter(Boolean))]
  }, [brief.likeness_reference_paths, brief.style_reference_paths])

  async function persistBrief(next: Brief) {
    setBrief(next)
    try {
      await saveCampaign(campaignId, next)
    } catch {
      /* keep local edit */
    }
  }

  function buildPromptExtra(): string {
    const bits: string[] = []
    if (promptExtra.trim()) bits.push(promptExtra.trim())
    if (likenessPath) {
      bits.push(
        `Preserve character/product likeness consistent with reference (${fileLabel(likenessPath)}).`,
      )
    }
    if (styleRefPaths.length) {
      bits.push(
        `Match energy/style cues from: ${styleRefPaths.map(fileLabel).join(', ')}.`,
      )
    }
    bits.push('Keep on-image text unchanged if present. No new text overlays.')
    return bits.join(' ')
  }

  function handleGenerateMotion() {
    if (!selectedTargets.length) return
    setMotionError(null)
    const nextBrief = {
      ...brief,
      motion_notes: motionPrompt,
      likeness_reference_paths: likenessPath
        ? [likenessPath, ...(brief.likeness_reference_paths || []).filter((p) => p !== likenessPath)]
        : brief.likeness_reference_paths || [],
      style_reference_paths: styleRefPaths,
    }
    const req: MotionGenerateRequest = {
      targets: selectedTargets.map((t) => ({
        path: stillSource(t),
        product: t.product,
        ratio: t.ratio,
      })),
      durationSeconds: motionDuration,
      prompt: motionPrompt,
      promptExtra: buildPromptExtra(),
    }
    // Navigate immediately. Do not wait on save or the motion API.
    try {
      onGenerate(req)
      onDone()
    } catch (err) {
      setMotionError(err instanceof Error ? err.message : String(err))
      return
    }
    void persistBrief(nextBrief)
  }

  async function handleUpload(role: 'likeness' | 'style', files: FileList | null) {
    if (!files?.length || !onUploadAssets) return
    const list = Array.from(files)
    const roles = list.map(() => role)
    await onUploadAssets(list, roles)
  }

  function togglePath(path: string) {
    setMotionSourcePaths((prev) =>
      prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path],
    )
  }

  function toggleStyleRef(path: string) {
    setStyleRefPaths((prev) =>
      prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path],
    )
  }

  if (phase === 'ask') {
    return (
      <section className="panel step-panel" style={{ padding: '1.5rem' }}>
        <h2 style={{ marginTop: 0 }}>Motion?</h2>
        <p style={{ color: 'var(--muted)', marginTop: 0 }}>
          Do you want to generate any motion assets from these stills? Motion is optional. Say no
          to go straight to Results.
        </p>

        {!motionAvailable && (
          <div className="banner" style={{ marginBottom: '1rem' }}>
            xAI key not set. You can still continue to Results, or add a Grok key in Settings and
            come back.
          </div>
        )}

        {motionStillOptions.length === 0 ? (
          <div className="banner" style={{ marginBottom: '1rem' }}>
            No stills ready to animate yet. Continue to Results, or go back to Finalize.
          </div>
        ) : (
          <>
            <p style={{ color: 'var(--muted)', marginBottom: '0.55rem' }}>
              Available stills
              {motionSourcePaths.length
                ? ` · ${motionSourcePaths.length} pre-selected for Yes`
                : ' · optionally tap to pre-select, then Yes'}
            </p>
            <StillPickGrid
              options={motionStillOptions}
              selectedPaths={motionSourcePaths}
              onToggle={togglePath}
            />
          </>
        )}

        <div className="action-row" style={{ marginTop: '1.35rem' }}>
          <button type="button" className="btn-ghost" onClick={onBack}>
            Back
          </button>
          <button type="button" className="btn-ghost" onClick={onDone}>
            No, skip to Results
          </button>
          <button
            type="button"
            className="btn"
            disabled={motionStillOptions.length === 0}
            onClick={() => {
              if (!motionSourcePaths.length && motionStillOptions.length) {
                setMotionSourcePaths(motionStillOptions.map((t) => stillSource(t)))
              }
              setPhase('settings')
            }}
          >
            Yes, set up motion
          </button>
        </div>
      </section>
    )
  }

  return (
    <section className="panel step-panel" style={{ padding: '1.5rem' }}>
      <h2 style={{ marginTop: 0 }}>Motion</h2>
      <PipelineCountBanner
        plan={planCreativeCounts(brief)}
        emphasis={
          selectedCount > 0
            ? `Selected ${selectedCount} still${selectedCount === 1 ? '' : 's'} for motion (opt-in, not counted in the still/final plan).`
            : 'Pick stills below, then generate. Or continue to Results to skip.'
        }
      />
      <p style={{ color: 'var(--muted)', marginTop: 0 }}>
        Animate finished stills with Grok Imagine. Pick sources, edit the motion prompt, and
        optionally add likeness or style references. Generate opens Results while clips load.
      </p>

      {!motionAvailable && (
        <div className="banner" style={{ marginBottom: '1rem' }}>
          xAI key not set. Add a Grok key in Settings to generate motion, or continue to Results.
        </div>
      )}

      {motionAvailable && motionStillOptions.length === 0 && (
        <div className="banner" style={{ marginBottom: '1rem' }}>
          No stills ready to animate yet. Go back to Finalize or Generate first.
        </div>
      )}

      {motionStillOptions.length > 0 && (
        <>
          <div style={{ marginBottom: '0.85rem' }}>
            <div style={{ color: 'var(--muted)', marginBottom: '0.4rem' }}>
              Stills to animate
              {selectedCount
                ? ` (${selectedCount} selected)`
                : ' (none selected)'}
            </div>
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
                disabled={motionBusy}
                onClick={() =>
                  setMotionSourcePaths(motionStillOptions.map((t) => stillSource(t)))
                }
              >
                Select all
              </button>
              <button
                type="button"
                className="btn-ghost"
                disabled={motionBusy || motionSourcePaths.length === 0}
                onClick={() => setMotionSourcePaths([])}
              >
                Deselect all
              </button>
            </div>
            <StillPickGrid
              options={motionStillOptions}
              selectedPaths={motionSourcePaths}
              onToggle={togglePath}
              disabled={motionBusy}
            />
          </div>

          <label style={{ display: 'block', marginBottom: '0.85rem', color: 'var(--muted)' }}>
            Motion prompt
            <textarea
              className="field"
              rows={4}
              value={motionPrompt}
              disabled={motionBusy || !motionAvailable}
              placeholder="Describe the motion: camera drift, product emphasis, energy…"
              onChange={(e) => setMotionPrompt(e.target.value)}
              style={{ marginTop: '0.35rem', width: '100%', resize: 'vertical' }}
            />
          </label>

          <label style={{ display: 'block', marginBottom: '0.85rem', color: 'var(--muted)' }}>
            Extra direction (appended)
            <textarea
              className="field"
              rows={3}
              value={promptExtra}
              disabled={motionBusy || !motionAvailable}
              placeholder="Optional: more camera notes, energy, what must stay locked…"
              onChange={(e) => setPromptExtra(e.target.value)}
              style={{ marginTop: '0.35rem', width: '100%', resize: 'vertical' }}
            />
          </label>

          <div style={{ marginBottom: '0.85rem' }}>
            <div style={{ color: 'var(--muted)', marginBottom: '0.4rem' }}>
              Likeness reference (folded into the prompt; still is the animated frame)
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem', marginBottom: '0.45rem' }}>
              <button
                type="button"
                className="btn-ghost"
                disabled={motionBusy}
                onClick={() => setLikenessPath('')}
              >
                None
              </button>
              {likenessOptions.map((path) => (
                <button
                  key={path}
                  type="button"
                  className="btn-ghost"
                  disabled={motionBusy}
                  style={{
                    borderColor: likenessPath === path ? 'var(--accent)' : 'var(--border)',
                    background: likenessPath === path ? 'var(--accent-soft)' : 'transparent',
                  }}
                  onClick={() => setLikenessPath(path)}
                >
                  {fileLabel(path)}
                </button>
              ))}
            </div>
            {onUploadAssets && (
              <label className="file-pick">
                <span className="btn-ghost">Upload likeness</span>
                <input
                  type="file"
                  accept="image/*"
                  disabled={motionBusy}
                  onChange={(e) => {
                    void handleUpload('likeness', e.target.files)
                    e.target.value = ''
                  }}
                />
              </label>
            )}
            {likenessPath && (
              <div style={{ marginTop: '0.55rem' }}>
                <img
                  src={outputThumbUrl(likenessPath, 192)}
                  alt=""
                  loading="lazy"
                  decoding="async"
                  style={{
                    width: 96,
                    height: 96,
                    objectFit: 'cover',
                    borderRadius: 6,
                    border: '1px solid var(--border)',
                  }}
                />
              </div>
            )}
          </div>

          <div style={{ marginBottom: '0.85rem' }}>
            <div style={{ color: 'var(--muted)', marginBottom: '0.4rem' }}>
              Additional style references
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.55rem', marginBottom: '0.45rem' }}>
              {(brief.style_reference_paths || []).map((path) => {
                const on = styleRefPaths.includes(path)
                return (
                  <button
                    key={path}
                    type="button"
                    className={`motion-ref-pick${on ? ' is-on' : ''}`}
                    onClick={() => toggleStyleRef(path)}
                    disabled={motionBusy}
                  >
                    <img
                      src={outputThumbUrl(path, 240)}
                      alt=""
                      loading="lazy"
                      decoding="async"
                    />
                  </button>
                )
              })}
            </div>
            {onUploadAssets && (
              <label className="file-pick">
                <span className="btn-ghost">Upload style refs</span>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  disabled={motionBusy}
                  onChange={(e) => {
                    void handleUpload('style', e.target.files)
                    e.target.value = ''
                  }}
                />
              </label>
            )}
          </div>

          <label style={{ display: 'block', marginBottom: '0.75rem', color: 'var(--muted)' }}>
            Video length
            <select
              className="field"
              value={motionDuration}
              disabled={motionBusy || !motionAvailable}
              onChange={(e) => setMotionDuration(Number(e.target.value))}
              style={{ marginTop: '0.35rem', maxWidth: 220 }}
            >
              <option value={4}>4 seconds</option>
              <option value={6}>6 seconds</option>
              <option value={8}>8 seconds</option>
            </select>
          </label>

          <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>
            Will generate {selectedCount} motion
            {selectedCount === 1 ? '' : 's'}
            {selectedCount > 0 ? ' · Results will show them loading' : ''}
          </p>

          {motionError && <div className="banner banner-danger">{motionError}</div>}
        </>
      )}

      <div className="action-row motion-actions" style={{ marginTop: '1.25rem' }}>
        <button
          type="button"
          className="btn-ghost"
          onClick={() => {
            if (entry === 'ask') setPhase('ask')
            else onBack()
          }}
          disabled={motionBusy}
        >
          Back
        </button>
        <button type="button" className="btn-ghost" onClick={onDone} disabled={motionBusy}>
          Skip to Results
        </button>
        <button
          type="button"
          className="btn motion-generate-btn"
          disabled={motionBusy || !motionAvailable || selectedCount === 0}
          onClick={() => void handleGenerateMotion()}
        >
          {motionBusy
            ? 'Starting…'
            : selectedCount > 0
              ? `Generate motion (${selectedCount})`
              : 'Generate motion'}
        </button>
      </div>
    </section>
  )
}
