import { useEffect, useRef, useState } from 'react'
import {
  getProductSeeds,
  outputUrl,
  retryProductSeeds,
  saveCampaign,
  saveDraft,
  subscribeEvents,
  suggestCopy,
  type AssetManifest,
  type Brief,
  type ImageQuality,
  type ProductSeedsStatus,
} from '../lib/api'
import { ASPECT_RATIO_EXAMPLES } from '../lib/aspectExamples'
import {
  LANGUAGE_OPTIONS,
  OTHER_LANGUAGE_VALUE,
  languageLabel,
  normalizeLanguageId,
} from '../lib/languages'
import { AspectRatioExamples } from './AspectRatioExamples'
import { BrandNotesEditor } from './BrandNotesEditor'
import { LogoPicker } from './LogoPicker'
import {
  EMPTY_ROLE_FILES,
  RoleUploadSections,
  flattenRoleFiles,
  type RoleFiles,
} from './RoleUploadSections'
import {
  assignProductHero,
  collectProductImagePaths,
  duplicateProduct,
  emptyProduct,
  toggleProductRef,
} from '../lib/products'
import { perProductStills, planCreativeCounts } from '../lib/creativeCounts'
import { PipelineCountBanner } from './PipelineCountBanner'

export function ReviewStep({
  campaignId,
  brief,
  setBrief,
  manifest: _manifest,
  missingFields,
  imageQuality,
  setImageQuality,
  onBack,
  onApprove,
  onUploadAssets,
  busy,
  error,
  initialProductSeeds = null,
}: {
  campaignId: string
  brief: Brief
  setBrief: (b: Brief) => void
  manifest: AssetManifest | null
  missingFields: string[]
  imageQuality: ImageQuality
  setImageQuality: (v: ImageQuality) => void
  onBack: () => void
  onApprove: () => Promise<void>
  onUploadAssets: (files: File[], roles?: string[]) => Promise<void>
  busy: boolean
  error: string | null
  initialProductSeeds?: ProductSeedsStatus | null
}) {
  const [showJson, setShowJson] = useState(false)
  const [jsonText, setJsonText] = useState('')
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [suggestBusy, setSuggestBusy] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const [langPick, setLangPick] = useState('')
  const [customLang, setCustomLang] = useState('')
  const [roleFiles, setRoleFiles] = useState<RoleFiles>({ ...EMPTY_ROLE_FILES })
  const [draftBusy, setDraftBusy] = useState(false)
  const [draftMsg, setDraftMsg] = useState<string | null>(null)
  const [productSeeds, setProductSeeds] = useState<ProductSeedsStatus | null>(
    initialProductSeeds,
  )
  const [seedRetryBusy, setSeedRetryBusy] = useState(false)
  const seedsEsRef = useRef<EventSource | null>(null)
  const briefRef = useRef(brief)
  briefRef.current = brief

  useEffect(() => {
    let cancelled = false

    function mergeSeedPaths(status: ProductSeedsStatus) {
      const pathByName = new Map<string, string>()
      for (const item of status.items || []) {
        if (item.status === 'ready' && item.path) {
          pathByName.set(item.product_name, item.path)
        }
      }
      for (const p of status.brief?.products || []) {
        if (p.input_asset_path) pathByName.set(p.name, p.input_asset_path)
      }
      if (!pathByName.size) return

      const current = briefRef.current
      let changed = false
      const products = current.products.map((p) => {
        const path = pathByName.get(p.name)
        if (!path || p.input_asset_path === path) return p
        changed = true
        return {
          ...p,
          input_asset_path: path,
          product_mode:
            p.product_mode === 'generate-concept' ? 'use-provided' : p.product_mode,
        }
      })
      if (changed) setBrief({ ...current, products })
    }

    async function refreshSeeds() {
      try {
        const status = await getProductSeeds(campaignId)
        if (cancelled) return
        setProductSeeds(status)
        // Never replace the whole brief (would wipe Review edits like outputs/framing).
        mergeSeedPaths(status)
        return status
      } catch {
        return null
      }
    }

    void refreshSeeds()

    const es = subscribeEvents(campaignId, (event) => {
      if (
        event === 'product_seed.completed' ||
        event === 'product_seeds.ready' ||
        event === 'product_seeds.failed' ||
        event === 'product_seed.failed'
      ) {
        void refreshSeeds()
      }
    })
    seedsEsRef.current = es

    const poll = window.setInterval(() => {
      void refreshSeeds().then((status) => {
        if (!status) return
        if (status.status === 'ready' || (status.status === 'failed' && !status.needed)) {
          window.clearInterval(poll)
        }
      })
    }, 2500)

    return () => {
      cancelled = true
      window.clearInterval(poll)
      es.close()
      seedsEsRef.current = null
    }
  }, [campaignId, setBrief])

  function addCustomLanguage() {
    const name = customLang.trim()
    if (!name) return
    const current = (brief.localize_to || []).map(normalizeLanguageId)
    const id = normalizeLanguageId(name)
    if (current.some((x) => normalizeLanguageId(x) === id)) {
      setCustomLang('')
      setLangPick('')
      return
    }
    if (current.length >= 5) return
    setBrief({ ...brief, localize_to: [...current, id] })
    setCustomLang('')
    setLangPick('')
  }

  const seedsPending =
    Boolean(productSeeds?.needed) && productSeeds?.status === 'pending'
  const seedsFailed =
    Boolean(productSeeds?.needed) && productSeeds?.status === 'failed'
  const missingHeroes = brief.products.filter((p) => !p.input_asset_path)

  const productBlockers = brief.products
    .filter((p) => p.product_mode === 'use-provided' && !p.input_asset_path)
    .map((p) =>
      seedsPending
        ? `${p.name}: product photo is generating in the background.`
        : `${p.name}: needs a product photo, or switch Mode to “Generate from concept + refs”.`,
    )

  // Manifest from parse can be stale after mode/name edits; trust the live brief.
  // Also block while background product seeds are still running or failed.
  const blocked =
    missingFields.length > 0 ||
    productBlockers.length > 0 ||
    seedsPending ||
    seedsFailed ||
    (Boolean(productSeeds?.needed) && missingHeroes.length > 0)

  const creativePlan = planCreativeCounts(brief)

  return (
    <section className="panel step-panel" style={{ padding: '1.5rem' }}>
      <h2 style={{ marginTop: 0 }}>Review</h2>
      <PipelineCountBanner
        plan={creativePlan}
        emphasis={
          creativePlan.generateCount > 0
            ? `Approve will start Generate for ${creativePlan.generateCount} no-text still${creativePlan.generateCount === 1 ? '' : 's'}.`
            : undefined
        }
      />
      {seedsPending && (
        <div className="banner" style={{ marginBottom: '1rem' }}>
          Generating product photos in the background
          {productSeeds?.items?.length
            ? ` (${productSeeds.items.filter((i) => i.status === 'ready').length}/${productSeeds.items.length} ready)`
            : ''}
          . Approve stays locked until they appear on each product card.
        </div>
      )}
      {seedsFailed && (
        <div className="banner banner-danger" style={{ marginBottom: '1rem' }}>
          <div>
            Product photo generation failed
            {productSeeds?.error ? `: ${productSeeds.error}` : '.'} Upload photos or retry.
          </div>
          <button
            type="button"
            className="btn-ghost"
            style={{ marginTop: '0.65rem' }}
            disabled={seedRetryBusy}
            onClick={() => {
              void (async () => {
                setSeedRetryBusy(true)
                setLocalError(null)
                try {
                  const status = await retryProductSeeds(campaignId)
                  setProductSeeds(status)
                } catch (err) {
                  setLocalError(err instanceof Error ? err.message : String(err))
                } finally {
                  setSeedRetryBusy(false)
                }
              })()
            }}
          >
            {seedRetryBusy ? 'Retrying…' : 'Retry product photos'}
          </button>
        </div>
      )}
      {(missingFields.length > 0 || productBlockers.length > 0) && (
        <div className="banner">
          {missingFields.length > 0 && (
            <div>
              Some required fields are missing: {missingFields.join(', ')}. Please complete them
              before generating.
            </div>
          )}
          {productBlockers.map((m, i) => (
            <div key={`pb-${i}`}>{m}</div>
          ))}
          {productBlockers.length > 0 && !seedsPending && (
            <button
              type="button"
              className="btn-ghost"
              style={{ marginTop: '0.65rem' }}
              onClick={() => {
                setBrief({
                  ...brief,
                  products: brief.products.map((p) =>
                    p.product_mode === 'use-provided' && !p.input_asset_path
                      ? { ...p, product_mode: 'generate-concept' as const }
                      : p,
                  ),
                })
              }}
            >
              Generate all missing products from the brief instead
            </button>
          )}
        </div>
      )}

      <div style={{ marginBottom: '1rem' }}>
        <button
          type="button"
          className="btn-ghost"
          onClick={() => {
            if (!showJson) setJsonText(JSON.stringify(brief, null, 2))
            setShowJson((v) => !v)
            setJsonError(null)
          }}
        >
          {showJson ? 'Form view' : 'Raw JSON'}
        </button>
      </div>

      {showJson ? (
        <>
          <textarea
            className="field"
            rows={18}
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            style={{ fontFamily: 'ui-monospace, monospace', fontSize: '0.85rem' }}
          />
          {jsonError && <div className="banner banner-danger">{jsonError}</div>}
          <button
            type="button"
            className="btn"
            style={{ marginTop: '0.75rem' }}
            onClick={() => {
              try {
                setBrief(JSON.parse(jsonText) as Brief)
                setJsonError(null)
                setShowJson(false)
              } catch (err) {
                setJsonError(err instanceof Error ? err.message : String(err))
              }
            }}
          >
            Apply JSON
          </button>
        </>
      ) : (
        <>
          <div className="review-fields">
            <Field
              label="Campaign"
              value={brief.campaign_name}
              onChange={(v) => setBrief({ ...brief, campaign_name: v })}
            />
            <Field label="Brand" value={brief.brand} onChange={(v) => setBrief({ ...brief, brand: v })} />
            <Field
              label="Market"
              value={brief.market}
              onChange={(v) => setBrief({ ...brief, market: v })}
            />
            <Field
              label="Audience"
              value={brief.audience}
              onChange={(v) => setBrief({ ...brief, audience: v })}
            />
          </div>
          <Field
            label="Default message"
            value={brief.message}
            onChange={(v) => setBrief({ ...brief, message: v })}
          />
          <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '-0.35rem' }}>
            Used when a product has no message of its own. Set per-product copy below when shoes
            or stories differ.
          </p>
          <Field label="Default CTA" value={brief.cta} onChange={(v) => setBrief({ ...brief, cta: v })} />
          <Field
            label="Supporting copy"
            value={brief.supporting_copy || ''}
            onChange={(v) => setBrief({ ...brief, supporting_copy: v })}
          />
          <Field
            label="Legal disclaimer"
            value={brief.legal_disclaimer || ''}
            onChange={(v) => setBrief({ ...brief, legal_disclaimer: v })}
          />
          <div style={{ marginBottom: '0.75rem' }}>
            <button
              type="button"
              className="btn-ghost"
              disabled={suggestBusy || busy}
              onClick={async () => {
                setSuggestBusy(true)
                setLocalError(null)
                try {
                  const res = await suggestCopy(campaignId)
                  setBrief(res.brief)
                } catch (err) {
                  setLocalError(err instanceof Error ? err.message : String(err))
                } finally {
                  setSuggestBusy(false)
                }
              }}
            >
              {suggestBusy ? 'Suggesting copy…' : 'Suggest copy from brief'}
            </button>
          </div>
          <Field
            label="Default creative direction"
            value={brief.creative_direction}
            onChange={(v) => setBrief({ ...brief, creative_direction: v })}
          />
          <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '-0.35rem' }}>
            Campaign-wide scene notes. Override per product when backgrounds should differ.
          </p>
          <Field
            label="Motion notes"
            value={brief.motion_notes}
            onChange={(v) => setBrief({ ...brief, motion_notes: v })}
          />
          <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '-0.35rem' }}>
            Optional direction for video later. Stills generate first; on Results you pick
            which creatives to animate and can edit this prompt before generating motion.
          </p>

          <div className="review-formats-layout">
            <div className="review-formats-side">
              <h3 className="your-brief-col-heading">Output formats</h3>
              <p className="your-brief-col-hint">
                Choose one, some, or all ratios. The first selected ratio uses your framing
                choice; extra ratios reframe from the previous creative. Close-up is optional
                framing.
              </p>
              <AspectRatioExamples
                compact
                showCloseup
                selected={brief.outputs?.length ? brief.outputs : ['1:1', '9:16', '16:9']}
                onToggle={(ratio) => {
                  const current = brief.outputs?.length
                    ? [...brief.outputs]
                    : ASPECT_RATIO_EXAMPLES.map((r) => r.ratio)
                  if (current.includes(ratio)) {
                    const next = current.filter((r) => r !== ratio)
                    setBrief({
                      ...brief,
                      outputs: next.length ? next : ['1:1'],
                    })
                    return
                  }
                  const order = ASPECT_RATIO_EXAMPLES.map((r) => r.ratio)
                  setBrief({
                    ...brief,
                    outputs: order.filter((r) => current.includes(r) || r === ratio),
                  })
                }}
              />
              <div className="review-framing-block">
                <h3 className="your-brief-col-heading">Framing (first ratio)</h3>
                <p className="your-brief-col-hint">
                  Presets for the first ratio. Steer further in creative direction or asset
                  hints.
                </p>
                <div className="review-framing-chips">
                  {(
                    [
                      {
                        id: 'close-up' as const,
                        label: 'Close-up',
                        hint: 'Tight product fill',
                      },
                      {
                        id: 'zoomed' as const,
                        label: 'Zoomed out',
                        hint: 'Wider scene',
                      },
                      {
                        id: 'both' as const,
                        label: 'Both',
                        hint: 'Close-up then zoomed',
                      },
                    ] as const
                  ).map((opt) => {
                    const selected = (brief.framing || 'both') === opt.id
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        className="btn-ghost review-option-chip"
                        style={{
                          borderColor: selected ? 'var(--accent)' : 'var(--border)',
                          background: selected ? 'var(--accent-soft)' : 'transparent',
                          textAlign: 'left',
                        }}
                        onClick={() => setBrief({ ...brief, framing: opt.id })}
                      >
                        <div>{opt.label}</div>
                        <div className="review-option-hint">{opt.hint}</div>
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>

            <div className="review-formats-main">
              <h3 className="your-brief-col-heading">Image quality</h3>
              <p className="your-brief-col-hint">
                GPT Image cost and detail. Medium is the default for drafting. High for
                finals.
              </p>
              <div className="review-option-stack">
                {(
                  [
                    {
                      id: 'low' as const,
                      label: 'Low',
                      hint: 'Fastest, cheapest drafts',
                    },
                    {
                      id: 'medium' as const,
                      label: 'Medium',
                      hint: 'Balanced quality and cost',
                    },
                    {
                      id: 'high' as const,
                      label: 'High',
                      hint: 'Best detail, slower and pricier',
                    },
                  ] as const
                ).map((opt) => {
                  const selected = imageQuality === opt.id
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      className="btn-ghost review-option-chip"
                      style={{
                        borderColor: selected ? 'var(--accent)' : 'var(--border)',
                        background: selected ? 'var(--accent-soft)' : 'transparent',
                        textAlign: 'left',
                      }}
                      onClick={() => setImageQuality(opt.id)}
                    >
                      <div>{opt.label}</div>
                      <div className="review-option-hint">{opt.hint}</div>
                    </button>
                  )
                })}
              </div>

              <div className="review-text-mode-block">
                <h3 className="your-brief-col-heading">Campaign text rendering</h3>
                <p className="your-brief-col-hint">
                  Optional. Set now or choose in Finalize.
                </p>
                <div className="review-option-stack">
                  {(
                    [
                      {
                        id: 'later' as const,
                        label: 'Decide later',
                        hint: 'Choose text style in Finalize',
                      },
                      {
                        id: 'none' as const,
                        label: 'No campaign text',
                        hint: 'Stills only; no message or CTA',
                      },
                      {
                        id: 'composer' as const,
                        label: 'Composer',
                        hint: 'Pillow fixed regions; character-accurate',
                      },
                      {
                        id: 'ai' as const,
                        label: 'AI typography',
                        hint: 'Styled into the scene; may vary',
                      },
                      {
                        id: 'hybrid' as const,
                        label: 'Hybrid',
                        hint: 'Per-slot AI or Pillow',
                      },
                    ] as const
                  ).map((opt) => {
                    const current =
                      brief.text_render_mode === 'pillow'
                        ? 'composer'
                        : brief.text_render_mode || 'later'
                    const selected = current === opt.id
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        className="btn-ghost review-option-chip"
                        style={{
                          borderColor: selected ? 'var(--accent)' : 'var(--border)',
                          background: selected ? 'var(--accent-soft)' : 'transparent',
                          textAlign: 'left',
                        }}
                        onClick={() => setBrief({ ...brief, text_render_mode: opt.id })}
                      >
                        <div>{opt.label}</div>
                        <div className="review-option-hint">{opt.hint}</div>
                      </button>
                    )
                  })}
                </div>
                {brief.text_render_mode === 'hybrid' && (
                  <div className="review-hybrid-slots">
                    Hybrid slots (headline / supporting: pillow, ai, or skip)
                    <div className="review-hybrid-slot-row">
                      {(['headline', 'supporting'] as const).map((slot) => {
                        const slots = brief.slot_render || {
                          logo: 'pillow' as const,
                          headline: 'pillow' as const,
                          supporting: 'skip' as const,
                          cta: 'pillow' as const,
                          legal: 'skip' as const,
                        }
                        return (
                          <label
                            key={slot}
                            style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}
                          >
                            {slot}
                            <select
                              className="field"
                              style={{ width: 'auto' }}
                              value={slots[slot]}
                              onChange={(e) =>
                                setBrief({
                                  ...brief,
                                  slot_render: {
                                    ...slots,
                                    [slot]: e.target.value as 'pillow' | 'ai' | 'skip',
                                  },
                                })
                              }
                            >
                              <option value="pillow">pillow</option>
                              <option value="ai">ai</option>
                              <option value="skip">skip</option>
                            </select>
                          </label>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div style={{ marginTop: '1rem' }}>
            <div style={{ color: 'var(--muted)', marginBottom: '0.5rem' }}>
              Output languages (optional, up to 5). Leave empty to choose in Finalize. Same
              creative; AI writes message/CTA in each language you pick.
            </div>
            {(brief.localize_to || []).length === 0 ? (
              <p style={{ color: 'var(--muted)', fontSize: '0.85rem', margin: '0 0 0.65rem' }}>
                No languages selected yet.
              </p>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.65rem' }}>
                {(brief.localize_to || []).map((loc) => (
                  <span
                    key={loc}
                    className="btn-ghost"
                    style={{
                      display: 'inline-flex',
                      gap: '0.45rem',
                      alignItems: 'center',
                      padding: '0.35rem 0.65rem',
                      borderColor: 'var(--accent)',
                      background: 'var(--accent-soft)',
                    }}
                  >
                    {languageLabel(loc)}
                    <button
                      type="button"
                      className="btn-ghost"
                      style={{ padding: '0 0.25rem', border: 'none', minWidth: 0 }}
                      aria-label={`Remove ${languageLabel(loc)}`}
                      onClick={() => {
                        const current = (brief.localize_to || []).map(normalizeLanguageId)
                        const next = current.filter(
                          (x) => normalizeLanguageId(x) !== normalizeLanguageId(loc),
                        )
                        setBrief({ ...brief, localize_to: next })
                      }}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
              <select
                className="field"
                style={{ width: '100%', maxWidth: 320, minWidth: 0 }}
                value={langPick}
                disabled={
                  brief.text_render_mode === 'none' || (brief.localize_to || []).length >= 5
                }
                onChange={(e) => {
                  const v = e.target.value
                  setLangPick(v)
                  if (!v || v === OTHER_LANGUAGE_VALUE) return
                  const current = (brief.localize_to || []).map(normalizeLanguageId)
                  if (current.some((x) => normalizeLanguageId(x) === v)) {
                    setLangPick('')
                    return
                  }
                  if (current.length >= 5) return
                  setBrief({ ...brief, localize_to: [...current, v] })
                  setLangPick('')
                }}
              >
                <option value="">
                  {brief.text_render_mode === 'none'
                    ? 'Not needed (no campaign text)'
                    : (brief.localize_to || []).length >= 5
                      ? 'Limit reached (5)'
                      : 'Add a language…'}
                </option>
                {LANGUAGE_OPTIONS.filter((opt) => {
                  const selected = (brief.localize_to || []).map(normalizeLanguageId)
                  return !selected.includes(opt.value)
                }).map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
                <option value={OTHER_LANGUAGE_VALUE}>Other (type a language)…</option>
              </select>
              {langPick === OTHER_LANGUAGE_VALUE && (
                <>
                  <input
                    className="field"
                    style={{ width: 200 }}
                    placeholder="e.g. Basque, Navajo…"
                    value={customLang}
                    onChange={(e) => setCustomLang(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addCustomLanguage()
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={!customLang.trim() || (brief.localize_to || []).length >= 5}
                    onClick={addCustomLanguage}
                  >
                    Add
                  </button>
                </>
              )}
            </div>
          </div>

          <h3>Products</h3>
          <p style={{ color: 'var(--muted)', fontSize: '0.9rem', marginTop: 0 }}>
            Each product below gets its own creatives (one set of aspect ratios per product).
            If parsing picked up the wrong hero or refs, reassign the images here. Extra images on
            a product are references for that look, not separate ads.
          </p>
          {brief.products.map((p, i) => {
            const perProduct = perProductStills(brief)
            const pool = collectProductImagePaths(brief.products)
            const fileLabel = (path: string) =>
              path.replace(/\\/g, '/').split('/').pop() || path
            return (
            <div key={i} className="panel" style={{ padding: '1rem', marginBottom: '0.75rem' }}>
              <div className="product-card-meta">
                <span className="product-card-badge">
                  Product {i + 1} of {brief.products.length}
                </span>
                <span className="product-card-meta-hint">
                  This product → its own creative set (~{perProduct} still
                  {perProduct === 1 ? '' : 's'})
                </span>
                <div className="product-card-actions">
                  <button
                    type="button"
                    className="btn-ghost"
                    style={{ padding: '0.35rem 0.65rem', fontSize: '0.8rem' }}
                    onClick={() => {
                      const products = [...brief.products]
                      products.splice(i + 1, 0, duplicateProduct(p))
                      setBrief({ ...brief, products })
                    }}
                  >
                    Duplicate
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    style={{ padding: '0.35rem 0.65rem', fontSize: '0.8rem' }}
                    disabled={brief.products.length <= 1}
                    title={
                      brief.products.length <= 1
                        ? 'Keep at least one product'
                        : 'Remove this product'
                    }
                    onClick={() => {
                      if (brief.products.length <= 1) return
                      setBrief({
                        ...brief,
                        products: brief.products.filter((_, j) => j !== i),
                      })
                    }}
                  >
                    Remove
                  </button>
                </div>
              </div>
              <Field
                label="Name"
                value={p.name}
                onChange={(v) => {
                  const products = [...brief.products]
                  products[i] = { ...p, name: v }
                  setBrief({ ...brief, products })
                }}
              />
              <Field
                label="Message (this product)"
                value={p.message || ''}
                onChange={(v) => {
                  const products = [...brief.products]
                  products[i] = { ...p, message: v }
                  setBrief({ ...brief, products })
                }}
              />
              <Field
                label="CTA (this product)"
                value={p.cta || ''}
                onChange={(v) => {
                  const products = [...brief.products]
                  products[i] = { ...p, cta: v }
                  setBrief({ ...brief, products })
                }}
              />
              <Field
                label="Scene / creative direction (this product)"
                value={p.creative_direction || ''}
                onChange={(v) => {
                  const products = [...brief.products]
                  products[i] = { ...p, creative_direction: v }
                  setBrief({ ...brief, products })
                }}
              />
              <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '-0.25rem' }}>
                Leave message/CTA/scene blank to use the campaign defaults above. Fill them when
                this product needs different copy or a different background world.
              </p>
              <label style={{ display: 'block', marginTop: '0.5rem' }}>Mode</label>
              <select
                className="field"
                value={p.product_mode}
                onChange={(e) => {
                  const products = [...brief.products]
                  products[i] = {
                    ...p,
                    product_mode: e.target.value as 'use-provided' | 'generate-concept',
                  }
                  setBrief({ ...brief, products })
                }}
              >
                <option value="use-provided">Use uploaded product image</option>
                <option value="generate-concept">Generate from concept + refs</option>
              </select>
              {p.product_mode === 'use-provided' && !p.input_asset_path && (
                <div className="banner banner-danger" style={{ marginTop: '0.75rem' }}>
                  {seedsPending
                    ? 'Generating a product photo for this item…'
                    : 'This product needs an uploaded image before generation.'}
                </div>
              )}
              {!p.input_asset_path &&
                p.product_mode !== 'use-provided' &&
                seedsPending && (
                  <div className="banner" style={{ marginTop: '0.75rem' }}>
                    Generating a product photo for this item…
                  </div>
                )}
              {pool.length > 0 && (
                <div className="product-ref-assign">
                  <label style={{ display: 'block', marginTop: '0.75rem' }}>
                    Hero image for this product
                  </label>
                  <select
                    className="field"
                    value={p.input_asset_path || ''}
                    onChange={(e) => {
                      const next = e.target.value || null
                      setBrief({
                        ...brief,
                        products: assignProductHero(brief.products, i, next),
                      })
                    }}
                  >
                    <option value="">None</option>
                    {pool.map((path) => (
                      <option key={path} value={path}>
                        {fileLabel(path)}
                      </option>
                    ))}
                  </select>
                  <div style={{ color: 'var(--muted)', fontSize: '0.85rem', marginTop: '0.65rem' }}>
                    Extra references for this product
                  </div>
                  <div className="product-ref-check-grid">
                    {pool.map((path) => {
                      const isHero =
                        Boolean(p.input_asset_path) &&
                        p.input_asset_path!.replace(/\\/g, '/').toLowerCase() ===
                          path.replace(/\\/g, '/').toLowerCase()
                      const isRef = (p.input_asset_paths || []).some(
                        (r) =>
                          r.replace(/\\/g, '/').toLowerCase() ===
                          path.replace(/\\/g, '/').toLowerCase(),
                      )
                      return (
                        <label key={path} className="product-ref-check">
                          <input
                            type="checkbox"
                            checked={isRef}
                            disabled={isHero}
                            onChange={(e) =>
                              setBrief({
                                ...brief,
                                products: toggleProductRef(
                                  brief.products,
                                  i,
                                  path,
                                  e.target.checked,
                                ),
                              })
                            }
                          />
                          <img src={outputUrl(path)} alt="" />
                          <span>{fileLabel(path)}</span>
                        </label>
                      )
                    })}
                  </div>
                </div>
              )}
              {!pool.length && p.input_asset_path && (
                <p style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>
                  Asset: {p.input_asset_path}
                </p>
              )}
            </div>
            )
          })}
          <button
            type="button"
            className="btn-ghost"
            style={{ marginBottom: '0.85rem' }}
            onClick={() =>
              setBrief({
                ...brief,
                products: [...brief.products, emptyProduct(`New product ${brief.products.length + 1}`)],
              })
            }
          >
            Add product
          </button>
          <h3>Uploads by role</h3>
          <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>
            Files from Intake stay on this campaign and show as thumbnails below. Empty pickers are
            only for adding more. Upload many product photos freely, then assign heroes and refs on
            each product card above if the automatic split looks wrong.
          </p>
          <LogoPicker
            value={brief.brand_notes}
            onChange={(brand_notes) => setBrief({ ...brief, brand_notes })}
          />
          <RoleUploadSections
            value={roleFiles}
            onChange={setRoleFiles}
            disabled={uploading || busy}
            existingByRole={{
              logo: brief.brand_notes.logo_paths?.length
                ? brief.brand_notes.logo_paths
                : brief.brand_notes.logo_path
                  ? [brief.brand_notes.logo_path]
                  : [],
              product: brief.products.flatMap((p) =>
                [p.input_asset_path, ...(p.input_asset_paths || [])].filter(Boolean) as string[],
              ),
              style: brief.style_reference_paths || [],
              likeness: brief.likeness_reference_paths || [],
              background: brief.background_reference_paths || [],
            }}
          />
          <button
            type="button"
            className="btn-ghost"
            style={{ marginTop: '0.65rem' }}
            disabled={uploading || busy || flattenRoleFiles(roleFiles).files.length === 0}
            onClick={async () => {
              const { files, roleTags } = flattenRoleFiles(roleFiles)
              if (!files.length) return
              setUploading(true)
              try {
                await onUploadAssets(files, roleTags)
                setRoleFiles({ ...EMPTY_ROLE_FILES })
                try {
                  const status = await getProductSeeds(campaignId)
                  setProductSeeds(status)
                } catch {
                  /* ignore */
                }
              } finally {
                setUploading(false)
              }
            }}
          >
            {uploading ? 'Uploading…' : 'Upload selected files'}
          </button>

          <BrandNotesEditor
            value={brief.brand_notes}
            onChange={(brand_notes) => setBrief({ ...brief, brand_notes })}
          />

          <p
            style={{
              color: 'var(--muted)',
              fontSize: '0.9rem',
              marginTop: '1rem',
              marginBottom: 0,
            }}
          >
            Motion (optional): after Finalize, Results lets you choose specific stills to
            animate with Grok. Nothing is animated during Generate.
          </p>
        </>
      )}

      {error && <div className="banner banner-danger">{error}</div>}
      {localError && <div className="banner banner-danger">{localError}</div>}
      {draftMsg && <div className="banner">{draftMsg}</div>}
      <PipelineCountBanner
        plan={creativePlan}
        emphasis={
          creativePlan.generateCount > 0
            ? `Ready to generate ${creativePlan.generateCount} still${creativePlan.generateCount === 1 ? '' : 's'}${
                creativePlan.finalizeCount > 0
                  ? `, then up to ${creativePlan.finalizeCount} text final${creativePlan.finalizeCount === 1 ? '' : 's'} in Finalize`
                  : ''
              }.`
            : 'Add products and ratios above to see how many creatives this run will make.'
        }
      />
      <div className="action-row" style={{ marginTop: '0.85rem' }}>
        <button className="btn-ghost" type="button" onClick={onBack}>
          Back
        </button>
        <button
          className="btn-ghost"
          type="button"
          disabled={busy || draftBusy}
          onClick={async () => {
            setDraftBusy(true)
            setDraftMsg(null)
            setLocalError(null)
            try {
              await saveCampaign(campaignId, brief)
              await saveDraft(campaignId)
              setDraftMsg('Saved as draft. It will appear in Library with a Draft badge.')
            } catch (err) {
              setLocalError(err instanceof Error ? err.message : String(err))
            } finally {
              setDraftBusy(false)
            }
          }}
        >
          {draftBusy ? 'Saving…' : 'Save as draft'}
        </button>
        <button
          className="btn"
          type="button"
          disabled={busy || blocked}
          onClick={() => void onApprove()}
        >
          {busy
            ? 'Starting…'
            : creativePlan.generateCount > 0
              ? `Approve & Generate ${creativePlan.generateCount} still${creativePlan.generateCount === 1 ? '' : 's'}`
              : 'Approve & Generate creatives'}
        </button>
      </div>
    </section>
  )
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <label style={{ display: 'block', marginTop: '0.75rem' }}>
      <span style={{ display: 'block', marginBottom: '0.35rem', color: 'var(--muted)' }}>{label}</span>
      <input className="field" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}
