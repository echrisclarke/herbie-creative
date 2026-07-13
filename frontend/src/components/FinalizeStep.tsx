import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import {
  adaptLocalizeCopy,
  applyFinalize,
  outputUrl,
  saveCampaign,
  suggestFinalize,
  type Brief,
  type CreativeResult,
  type FinalizeChoices,
  type FinalizeSuggest,
  type TextPlacement,
  type SlotTextMode,
} from '../lib/api'
import {
  LANGUAGE_OPTIONS,
  OTHER_LANGUAGE_VALUE,
  languageLabel,
  normalizeLanguageId,
} from '../lib/languages'
import { planCreativeCounts } from '../lib/creativeCounts'
import { ColorSwatchPicker } from './ColorSwatchPicker'
import { LogoPicker, logoCandidates } from './LogoPicker'
import { matchBriefProduct, productSlug } from '../lib/products'

type CampaignTextMode = 'none' | 'composer' | 'ai' | 'hybrid'

const CAMPAIGN_TEXT_MODES: Array<{ id: CampaignTextMode; label: string; hint: string }> = [
  { id: 'none', label: 'No campaign text', hint: 'Keep stills as-is (logo optional)' },
  { id: 'composer', label: 'Composer', hint: 'Pillow fixed regions; character-accurate' },
  { id: 'ai', label: 'AI typography', hint: 'Styled into the scene; may vary' },
  { id: 'hybrid', label: 'Hybrid', hint: 'Per-slot AI or Pillow below' },
]

function initialCampaignTextMode(brief: Brief): CampaignTextMode {
  const m = brief.text_render_mode
  if (m === 'none') return 'none'
  if (m === 'ai' || m === 'hybrid') return m
  if (m === 'composer' || m === 'pillow') return 'composer'
  return 'composer'
}

function resolvedProductCopy(
  brief: Brief,
  productKey: string | undefined,
): { message: string; cta: string; supporting: string; productName: string } {
  const product = matchBriefProduct(brief, productKey)
  return {
    message: (product?.message || brief.message || '').trim(),
    cta: (product?.cta || brief.cta || '').trim(),
    supporting: (product?.supporting_copy || brief.supporting_copy || '').trim(),
    productName: product?.name || productKey || '',
  }
}

function buildInitialProductCopy(brief: Brief) {
  const out: Record<string, { message: string; cta: string; supporting?: string }> = {}
  for (const p of brief.products) {
    out[p.name] = {
      message: (p.message || brief.message || '').trim(),
      cta: (p.cta || brief.cta || '').trim(),
      supporting: (p.supporting_copy || brief.supporting_copy || '').trim(),
    }
  }
  return out
}

/** Only no-text creative stills. Never finals (avoids double text when re-finalizing). */
function cleanCreativePath(t: CreativeResult): string | null {
  for (const raw of [t.creative_path, t.path]) {
    if (!raw) continue
    const norm = raw.replace(/\\/g, '/')
    const file = (norm.split('/').pop() || '').toLowerCase()
    if (file === 'creative.png' || file === 'creative.tight.png') return raw
  }
  return null
}

function initialLocales(brief: Brief): string[] {
  const locs = [
    ...new Set((brief.localize_to || []).map(normalizeLanguageId).filter(Boolean)),
  ]
  if (locs.length) {
    // English first when present so it stays the source language.
    const eng = locs.find((l) => normalizeLanguageId(l) === 'English')
    if (eng) return [eng, ...locs.filter((l) => l !== eng)]
    return locs
  }
  if (brief.text_render_mode === 'none') return []
  return ['English']
}

function ratioPlacementLabel(ratio: string): string {
  if (ratio.endsWith('-tight')) {
    return `${ratio.replace(/-tight$/, '')} close-up`
  }
  return ratio
}

const TEXT_PLACEMENTS: Array<{ id: TextPlacement; label: string }> = [
  { id: 'auto', label: 'AI decides' },
  { id: 'top-left', label: 'Top left' },
  { id: 'top-center', label: 'Top center' },
  { id: 'top-right', label: 'Top right' },
  { id: 'middle-left', label: 'Middle left' },
  { id: 'middle-center', label: 'Middle center' },
  { id: 'middle-right', label: 'Middle right' },
  { id: 'bottom-left', label: 'Bottom left' },
  { id: 'bottom-center', label: 'Bottom center' },
  { id: 'bottom-right', label: 'Bottom right' },
  { id: 'none', label: 'No caption' },
]

/** Keep in sync with backend text_placement.DEFAULT_TEXT_PLACEMENT_BY_RATIO. */
const DEFAULT_TEXT_PLACEMENT_BY_RATIO: Record<string, TextPlacement> = {
  '1:1': 'bottom-center',
  '9:16': 'bottom-center',
  '16:9': 'top-right',
}

function baseOutputRatio(ratio: string): string {
  const raw = (ratio || '').trim()
  for (const known of ['16:9', '9:16', '1:1'] as const) {
    if (raw === known || raw.startsWith(`${known}-`)) return known
  }
  return raw.split('-')[0] || '1:1'
}

function defaultPlacementForRatio(ratio: string): TextPlacement {
  return DEFAULT_TEXT_PLACEMENT_BY_RATIO[baseOutputRatio(ratio)] || 'bottom-center'
}

function previewFrameAspect(ratio: string): { aspectRatio: string; arW: number; arH: number } {
  const base = baseOutputRatio(ratio)
  if (base === '16:9') return { aspectRatio: '16 / 9', arW: 16, arH: 9 }
  if (base === '9:16') return { aspectRatio: '9 / 16', arW: 9, arH: 16 }
  return { aspectRatio: '1 / 1', arW: 1, arH: 1 }
}

const LOGO_PLACEMENTS = [
  { id: 'top-left' as const, label: 'Top left' },
  { id: 'top-right' as const, label: 'Top right' },
  { id: 'bottom-left' as const, label: 'Bottom left' },
  { id: 'bottom-right' as const, label: 'Bottom right' },
]

const SLOT_MODES: Array<{ id: SlotTextMode; label: string }> = [
  { id: 'composer', label: 'Composer' },
  { id: 'ai', label: 'AI in image' },
  { id: 'skip', label: 'Off' },
]

function placementStyle(placement: TextPlacement): CSSProperties {
  if (placement === 'none' || placement === 'auto') return { display: 'none' }
  const [v, h] = placement.split('-') as [string, string]
  const style: CSSProperties = {
    position: 'absolute',
    left: h === 'left' ? '6%' : h === 'right' ? 'auto' : '8%',
    right: h === 'right' ? '6%' : h === 'left' ? 'auto' : '8%',
    width: h === 'center' ? '84%' : '55%',
    textAlign: h === 'left' ? 'left' : h === 'right' ? 'right' : 'center',
    pointerEvents: 'none',
    zIndex: 2,
  }
  if (v === 'top') style.top = '12%'
  else if (v === 'middle') style.top = '40%'
  // Leave room under the caption stack for the legal strip (always bottom).
  else style.bottom = '16%'
  return style
}

function previewScrimStyle(placement: TextPlacement, opacity: number): CSSProperties {
  const v = placement === 'none' || placement === 'auto' ? 'bottom' : placement.split('-')[0]
  const strength = Math.max(0.15, Math.min(1, opacity))
  const soft = `rgba(0,0,0,${(0.55 * strength).toFixed(3)})`
  const mid = `rgba(0,0,0,${(0.28 * strength).toFixed(3)})`
  let background = `linear-gradient(to top, ${soft}, transparent)`
  let top = '55%'
  let bottom = '0'
  if (v === 'top') {
    background = `linear-gradient(to bottom, ${soft}, transparent)`
    top = '0'
    bottom = '55%'
  } else if (v === 'middle') {
    background = `linear-gradient(to bottom, transparent, ${mid}, ${soft}, ${mid}, transparent)`
    top = '28%'
    bottom = '22%'
  }
  return {
    position: 'absolute',
    left: 0,
    right: 0,
    top,
    bottom,
    background,
    pointerEvents: 'none',
    zIndex: 1,
  }
}

function logoPreviewStyle(
  placement: string,
  opts?: { scale?: number; opacity?: number; shadow?: number },
): CSSProperties {
  const scale = Math.max(0.35, Math.min(2.5, opts?.scale ?? 1))
  const opacity = Math.max(0, Math.min(1, opts?.opacity ?? 1))
  const shadow = Math.max(0, Math.min(1, opts?.shadow ?? 0))
  const base: CSSProperties = {
    position: 'absolute',
    width: `${20 * scale}%`,
    maxWidth: 140 * scale,
    height: `${9 * scale}%`,
    maxHeight: `${10 * scale}%`,
    objectFit: 'contain',
    pointerEvents: 'none',
    zIndex: 3,
    opacity,
    filter: shadow > 0.05 ? `drop-shadow(0 2px 6px rgba(0,0,0,${shadow}))` : undefined,
  }
  const edge = '4.5%'
  if (placement === 'top-right') return { ...base, top: edge, right: edge }
  if (placement === 'bottom-left') return { ...base, bottom: edge, left: edge }
  if (placement === 'bottom-right') return { ...base, bottom: edge, right: edge }
  return { ...base, top: edge, left: edge }
}

function isOriginalLogoColor(color: string) {
  return ['original', 'none', 'as-is', ''].includes((color || '').trim().toLowerCase())
}

export function FinalizeStep({
  campaignId,
  brief,
  setBrief,
  creatives,
  stillGenerating,
  applyHighlight,
  onBack,
  onDone,
}: {
  campaignId: string
  brief: Brief
  setBrief: (b: Brief) => void
  creatives: CreativeResult[]
  stillGenerating?: boolean
  applyHighlight?: boolean
  onBack: () => void
  onDone: (reportPath?: string) => void
}) {
  const [suggest, setSuggest] = useState<FinalizeSuggest | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [useLogo, setUseLogo] = useState(
    Boolean(brief.brand_notes.logo_path || brief.brand_notes.logo_description),
  )
  const [logoDescription, setLogoDescription] = useState(
    brief.brand_notes.logo_description || '',
  )
  const [logoColor, setLogoColor] = useState(brief.brand_notes.logo_color || '#FFFFFF')
  const [logoShadowOp, setLogoShadowOp] = useState(
    typeof brief.brand_notes.logo_shadow_opacity === 'number'
      ? brief.brand_notes.logo_shadow_opacity
      : 0.35,
  )
  const [logoOpacity, setLogoOpacity] = useState(
    typeof brief.brand_notes.logo_opacity === 'number' ? brief.brand_notes.logo_opacity : 1,
  )
  const [logoScale, setLogoScale] = useState(
    typeof brief.brand_notes.logo_scale === 'number' ? brief.brand_notes.logo_scale : 1,
  )
  const [textColor, setTextColor] = useState(brief.brand_notes.text_color || '#FFFFFF')
  const [ctaAccent, setCtaAccent] = useState(
    brief.brand_notes.colors?.[0] || '#E8E4DC',
  )
  const [scrim, setScrim] = useState(false)
  const [scrimOp, setScrimOp] = useState(0.4)
  const [shadowOp, setShadowOp] = useState(0.55)
  const [locales, setLocales] = useState<string[]>(() => initialLocales(brief))
  const [previewLocale, setPreviewLocale] = useState<string>(() => initialLocales(brief)[0] || 'English')
  const [localeCopy, setLocaleCopy] = useState<
    Record<string, { message: string; cta: string; supporting?: string }>
  >({})
  const [campaignTextMode, setCampaignTextMode] = useState<CampaignTextMode>(() =>
    initialCampaignTextMode(brief),
  )
  const [captionMode, setCaptionMode] = useState<SlotTextMode>(() =>
    initialCampaignTextMode(brief) === 'none'
      ? 'skip'
      : initialCampaignTextMode(brief) === 'ai'
        ? 'ai'
        : 'composer',
  )
  const [subcaptionMode, setSubcaptionMode] = useState<SlotTextMode>('skip')
  const [captionText, setCaptionText] = useState(() => {
    const first = brief.products[0]?.name
    return resolvedProductCopy(brief, first).message
  })
  const [captionStyle, setCaptionStyle] = useState('')
  const [captionFit, setCaptionFit] = useState('')
  const [subcaptionText, setSubcaptionText] = useState(() => {
    const first = brief.products[0]?.name
    return resolvedProductCopy(brief, first).supporting
  })
  const [subcaptionStyle, setSubcaptionStyle] = useState('')
  const [subcaptionFit, setSubcaptionFit] = useState('')
  const [productCopy, setProductCopy] = useState(() => buildInitialProductCopy(brief))
  const activeProductNameRef = useRef(brief.products[0]?.name || '')
  const [textPlacement, setTextPlacement] = useState<TextPlacement>(() =>
    initialCampaignTextMode(brief) === 'none'
      ? 'none'
      : (brief.brand_notes.text_placement as TextPlacement) || 'bottom-center',
  )
  const [textPlacementByRatio, setTextPlacementByRatio] = useState<
    Record<string, TextPlacement>
  >(() => ({ ...DEFAULT_TEXT_PLACEMENT_BY_RATIO }))
  const [manualLocales, setManualLocales] = useState<Record<string, boolean>>({})
  const [localeSyncBusy, setLocaleSyncBusy] = useState(false)
  const [logoPlacement, setLogoPlacement] = useState(
    brief.brand_notes.logo_placement || 'top-left',
  )
  const [legalPlacement, setLegalPlacement] = useState<'left' | 'center' | 'right'>(
    brief.brand_notes.legal_placement === 'center' ||
      brief.brand_notes.legal_placement === 'right'
      ? brief.brand_notes.legal_placement
      : 'left',
  )
  const [heroIndex, setHeroIndex] = useState(0)
  const [langPick, setLangPick] = useState('')
  const [customLang, setCustomLang] = useState('')
  const previewFrameRef = useRef<HTMLDivElement | null>(null)
  const previewImgRef = useRef<HTMLImageElement | null>(null)
  const [overlayBox, setOverlayBox] = useState({ top: 0, left: 0, width: 0, height: 0 })
  const autoSuggestStarted = useRef(false)
  const logoPlacementTouched = useRef(false)
  const localeAdaptTimer = useRef<number | null>(null)
  const localeAdaptSeq = useRef(0)
  const hasLogoFile = logoCandidates(brief.brand_notes).length > 0
  const previewLogoPath =
    brief.brand_notes.logo_path || logoCandidates(brief.brand_notes)[0] || null
  const noCampaignText = campaignTextMode === 'none'

  const creativePlan = useMemo(
    () =>
      planCreativeCounts(brief, {
        locales,
        noCampaignText: noCampaignText || textPlacement === 'none',
      }),
    [brief, locales, noCampaignText, textPlacement],
  )

  const previewTiles = useMemo(() => {
    const byKey = new Map<string, CreativeResult>()
    for (const t of creatives) {
      const src = cleanCreativePath(t)
      if (!src) continue
      const file = (src.replace(/\\/g, '/').split('/').pop() || '').toLowerCase()
      const tight = file.includes('tight')
      const ratio = tight
        ? `${baseOutputRatio(t.ratio)}-tight`
        : baseOutputRatio(t.ratio)
      const key = `${productSlug(t.product)}|${ratio}`
      const prev = byKey.get(key)
      // Prefer an explicit creative-locale row when duplicates exist after re-finalize.
      if (!prev || (t.locale === 'creative' && prev.locale !== 'creative')) {
        byKey.set(key, { ...t, path: src, creative_path: src, ratio })
      }
    }
    return Array.from(byKey.values())
  }, [creatives])

  const hero = previewTiles[Math.min(heroIndex, Math.max(0, previewTiles.length - 1))]
  const activeRatio = hero?.ratio || '1:1'
  const matchedProduct = matchBriefProduct(brief, hero?.product)
  const activeProductName = matchedProduct?.name || hero?.product || brief.products[0]?.name || ''
  const activeProductResolved =
    (activeProductName && productCopy[activeProductName]) ||
    resolvedProductCopy(brief, hero?.product || activeProductName)
  const activePlacement: TextPlacement =
    textPlacement === 'none'
      ? 'none'
      : textPlacementByRatio[activeRatio] ||
        textPlacementByRatio[baseOutputRatio(activeRatio)] ||
        defaultPlacementForRatio(activeRatio) ||
        textPlacement ||
        'bottom-center'
  const frameAspect = previewFrameAspect(activeRatio)
  const previewFrameStyle = {
    aspectRatio: frameAspect.aspectRatio,
    '--ar-w': String(frameAspect.arW),
    '--ar-h': String(frameAspect.arH),
  } as CSSProperties
  const primaryLoc = locales[0] || 'English'
  const previewLocNorm = normalizeLanguageId(previewLocale || primaryLoc)
  const primaryLocNorm = normalizeLanguageId(primaryLoc)
  const previewingPrimary = previewLocNorm === primaryLocNorm
  // Overlay copy follows the selected preview language; editors stay on the source language.
  const previewCopy = previewingPrimary
    ? {
        message: activeProductResolved.message || '',
        cta: activeProductResolved.cta || '',
        supporting: activeProductResolved.supporting || '',
      }
    : (() => {
        const pair =
          localeCopy[previewLocale] ||
          Object.entries(localeCopy).find(
            ([k]) => normalizeLanguageId(k) === previewLocNorm,
          )?.[1]
        return {
          message: pair?.message || '',
          cta: pair?.cta || '',
          supporting: pair?.supporting || '',
        }
      })()

  useEffect(() => {
    if (!locales.length) {
      setPreviewLocale(primaryLoc)
      return
    }
    const stillThere = locales.some(
      (loc) => normalizeLanguageId(loc) === normalizeLanguageId(previewLocale),
    )
    if (!stillThere) setPreviewLocale(locales[0])
  }, [locales, previewLocale, primaryLoc])

  function measureOverlayBox() {
    const frame = previewFrameRef.current
    const img = previewImgRef.current
    if (!frame || !img) return
    const fr = frame.getBoundingClientRect()
    const ir = img.getBoundingClientRect()
    if (ir.width < 2 || ir.height < 2) return
    setOverlayBox({
      top: Math.max(0, ir.top - fr.top),
      left: Math.max(0, ir.left - fr.left),
      width: ir.width,
      height: ir.height,
    })
  }

  useEffect(() => {
    measureOverlayBox()
    const frame = previewFrameRef.current
    const img = previewImgRef.current
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => measureOverlayBox()) : null
    if (frame && ro) ro.observe(frame)
    if (img && ro) ro.observe(img)
    window.addEventListener('resize', measureOverlayBox)
    return () => {
      ro?.disconnect()
      window.removeEventListener('resize', measureOverlayBox)
    }
  }, [hero?.path, activeRatio])

  useEffect(() => {
    if (!activeProductName || activeProductName === activeProductNameRef.current) return
    activeProductNameRef.current = activeProductName
    const next =
      productCopy[activeProductName] || resolvedProductCopy(brief, activeProductName)
    setCaptionText(next.message || '')
    setSubcaptionText(next.supporting || '')
    const source = locales[0] || 'English'
    setLocaleCopy((prev) => ({
      ...prev,
      [source]: {
        message: next.message || '',
        cta: next.cta || '',
        supporting: next.supporting || '',
      },
    }))
  }, [activeProductName, brief, locales, productCopy])

  function setPlacementForActiveRatio(next: TextPlacement) {
    setTextPlacement(next)
    if (next === 'none') return
    const key = baseOutputRatio(activeRatio)
    setTextPlacementByRatio((prev) => ({ ...prev, [activeRatio]: next, [key]: next }))
  }

  function applyPlacementToAllRatios() {
    const next = activePlacement === 'none' ? 'bottom-center' : activePlacement
    const ratios = Array.from(new Set(previewTiles.map((t) => t.ratio).filter(Boolean)))
    const map: Record<string, TextPlacement> = {}
    for (const r of ratios.length ? ratios : ['1:1', '9:16', '16:9']) {
      map[r] = next
    }
    setTextPlacement(next)
    setTextPlacementByRatio(map)
  }

  function applyCampaignTextMode(mode: CampaignTextMode) {
    setCampaignTextMode(mode)
    if (mode === 'none') {
      setCaptionMode('skip')
      setSubcaptionMode('skip')
      setTextPlacement('none')
      setError(null)
      return
    }
    if (textPlacement === 'none') setTextPlacement('bottom-center')
    if (mode === 'ai') {
      setCaptionMode('ai')
      return
    }
    if (mode === 'composer') {
      setCaptionMode('composer')
      return
    }
    // hybrid: leave per-slot modes as-is, but ensure caption is on
    if (captionMode === 'skip') setCaptionMode('composer')
  }

  function addCustomLanguage() {
    const name = customLang.trim()
    if (!name) return
    const current = locales.map(normalizeLanguageId)
    const id = normalizeLanguageId(name)
    if (current.some((x) => normalizeLanguageId(x) === id)) {
      setCustomLang('')
      setLangPick('')
      return
    }
    if (current.length >= 5) return
    setLocales([...current, id])
    setCustomLang('')
    setLangPick('')
  }

  useEffect(() => {
    if (noCampaignText) {
      setError(null)
      return
    }
    if (autoSuggestStarted.current) return
    if (!previewTiles.length) return
    autoSuggestStarted.current = true
    // Style only: never wipe Review / Finalize copy with sample-brief AI text.
    void handleSuggest({ soft: stillGenerating, mode: 'style' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewTiles.length, noCampaignText, stillGenerating])

  useEffect(() => {
    return () => {
      if (localeAdaptTimer.current) window.clearTimeout(localeAdaptTimer.current)
    }
  }, [])

  async function handleSuggest(opts?: {
    soft?: boolean
    /** style = colors/placement only; copy = replace overlay text (Suggest text). */
    mode?: 'style' | 'copy' | 'all'
  }) {
    const mode = opts?.mode || 'all'
    setBusy(true)
    setError(null)
    try {
      // Persist Review/Finalize edits so suggest uses the approved brief, not a stale sample.
      try {
        await saveCampaign(campaignId, brief)
      } catch {
        /* suggest can still run from in-memory brief on server if save fails */
      }
      const res = await suggestFinalize(campaignId)
      const s = res.suggest
      setSuggest(s)
      if (mode === 'style' || mode === 'all') {
        if (s.logo_color) setLogoColor(s.logo_color)
        if (s.text_color) setTextColor(s.text_color)
        if (s.cta_accent) setCtaAccent(s.cta_accent)
        if (typeof s.text_scrim === 'boolean') setScrim(s.text_scrim)
        if (typeof s.text_scrim_opacity === 'number') setScrimOp(s.text_scrim_opacity)
        if (typeof s.text_shadow_opacity === 'number') setShadowOp(s.text_shadow_opacity)
        if (s.text_placement && TEXT_PLACEMENTS.some((p) => p.id === s.text_placement)) {
          if (textPlacement === 'auto') {
            // keep auto; apply will use suggested placement
          } else {
            const next = s.text_placement as TextPlacement
            setTextPlacement(next)
            setTextPlacementByRatio((prev) => {
              const ratios = Array.from(
                new Set(previewTiles.map((t) => t.ratio).filter(Boolean)),
              )
              const map = { ...prev }
              for (const r of ratios.length ? ratios : ['1:1', '9:16', '16:9']) {
                if (!map[r]) map[r] = next
              }
              return map
            })
          }
        }
        if (s.logo_placement && LOGO_PLACEMENTS.some((p) => p.id === s.logo_placement)) {
          if (!logoPlacementTouched.current) {
            setLogoPlacement(s.logo_placement)
          }
        }
        if (s.styling_notes && !captionStyle) {
          setCaptionStyle(s.styling_notes)
        }
        if (s.font_names?.length) {
          setBrief({
            ...brief,
            brand_notes: { ...brief.brand_notes, font_names: s.font_names },
          })
        }
      }

      if (mode === 'copy' || mode === 'all') {
        const locs = [
          ...new Set(Object.keys(s.locales || {}).map(normalizeLanguageId).filter(Boolean)),
        ]
        if (locs.length) {
          const eng = locs.find((l) => l === 'English')
          setLocales(eng ? [eng, ...locs.filter((l) => l !== eng)] : locs)
        }
        const copy: Record<string, { message: string; cta: string; supporting?: string }> = {}
        for (const [loc, pair] of Object.entries(s.locales || {})) {
          const id = normalizeLanguageId(loc)
          copy[id] = {
            message: pair.message || brief.message,
            cta: pair.cta || brief.cta,
            supporting: pair.supporting || brief.supporting_copy || '',
          }
        }
        const primary = locs[0] || primaryLoc
        setLocaleCopy((prev) => {
          const next = { ...copy }
          // Manual locale edits always win over a fresh suggest.
          for (const loc of Object.keys(prev)) {
            if (manualLocales[loc] && prev[loc]) next[loc] = prev[loc]
          }
          return next
        })
        if (copy[primary]?.message) setCaptionText(copy[primary].message)
        if (copy[primary]?.supporting !== undefined) {
          setSubcaptionText(copy[primary].supporting || '')
        }
        if (activeProductName && copy[primary]) {
          const pair = copy[primary]
          setProductCopy((pc) => ({
            ...pc,
            [activeProductName]: {
              message: pair.message || '',
              cta: pair.cta || '',
              supporting: pair.supporting || '',
            },
          }))
          setBrief({
            ...brief,
            products: brief.products.map((p) =>
              p.name === activeProductName
                ? {
                    ...p,
                    message: pair.message || p.message,
                    cta: pair.cta || p.cta,
                    supporting_copy: pair.supporting || p.supporting_copy,
                  }
                : p,
            ),
          })
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      const missingCreative = /no creative\.png found/i.test(msg)
      if (opts?.soft || (stillGenerating && missingCreative)) {
        // First tiles can land before creative.png is on disk; retry when more arrive.
        autoSuggestStarted.current = false
      } else {
        setError(msg)
      }
    } finally {
      setBusy(false)
    }
  }

  async function handleSuggestText() {
    const sourceMsg = (captionText || activeProductResolved.message || '').trim()
    const sourceCta = (activeProductResolved.cta || '').trim()
    const sourceSup = (subcaptionText || activeProductResolved.supporting || '').trim()
    // If the user already wrote copy (Review or Finalize), adapt that into other
    // languages. Do not replace it with sample-brief AI lines.
    if (sourceMsg && locales.length > 1) {
      setBusy(true)
      setError(null)
      try {
        try {
          await saveCampaign(campaignId, brief)
        } catch {
          /* continue with in-memory brief */
        }
        const source = locales[0] || 'English'
        const existing = {
          ...localeCopy,
          [source]: {
            message: sourceMsg,
            cta: sourceCta,
            supporting: sourceSup,
          },
        }
        const locked = locales.filter((loc) => loc !== source && manualLocales[loc])
        const res = await adaptLocalizeCopy(campaignId, {
          message: sourceMsg,
          cta: sourceCta,
          supporting: sourceSup,
          locales,
          locked_locales: locked,
          existing,
        })
        setLocaleCopy((prev) => {
          const merged = { ...prev, ...res.locales }
          merged[source] = {
            message: sourceMsg,
            cta: sourceCta,
            supporting: sourceSup,
          }
          for (const loc of locked) {
            if (prev[loc]) merged[loc] = prev[loc]
          }
          return merged
        })
        setCaptionText(sourceMsg)
        setSubcaptionText(sourceSup)
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy(false)
      }
      return
    }
    await handleSuggest({ mode: 'copy' })
  }

  function scheduleLocaleAdapt(nextCopy: Record<string, { message: string; cta: string; supporting?: string }>) {
    if (noCampaignText || locales.length < 2) return
    if (localeAdaptTimer.current) window.clearTimeout(localeAdaptTimer.current)
    const source = locales[0] || 'English'
    const sourcePair = nextCopy[source] || {
      message: captionText || brief.message,
      cta: brief.cta,
      supporting: subcaptionText,
    }
    localeAdaptTimer.current = window.setTimeout(() => {
      void (async () => {
        const seq = ++localeAdaptSeq.current
        setLocaleSyncBusy(true)
        try {
          const locked = locales.filter((loc) => loc !== source && manualLocales[loc])
          const res = await adaptLocalizeCopy(campaignId, {
            message: sourcePair.message || '',
            cta: sourcePair.cta || '',
            supporting: sourcePair.supporting || '',
            locales,
            locked_locales: locked,
            existing: nextCopy,
          })
          if (seq !== localeAdaptSeq.current) return
          setLocaleCopy((prev) => {
            const merged = { ...prev, ...res.locales }
            merged[source] = {
              message: sourcePair.message || '',
              cta: sourcePair.cta || '',
              supporting: sourcePair.supporting || '',
            }
            for (const loc of locked) {
              if (prev[loc]) merged[loc] = prev[loc]
            }
            return merged
          })
        } catch (err) {
          if (seq === localeAdaptSeq.current) {
            setError(err instanceof Error ? err.message : String(err))
          }
        } finally {
          if (seq === localeAdaptSeq.current) setLocaleSyncBusy(false)
        }
      })()
    }, 600)
  }

  function updateSourceCopy(patch: Partial<{ message: string; cta: string; supporting: string }>) {
    const source = locales[0] || 'English'
    const productName = activeProductNameRef.current || activeProductName
    const prev = {
      message: captionText || activeProductResolved.message,
      cta: activeProductResolved.cta,
      supporting: subcaptionText,
    }
    const nextPair = { ...prev, ...patch }
    if (patch.message !== undefined) setCaptionText(patch.message)
    if (patch.supporting !== undefined) setSubcaptionText(patch.supporting)
    const nextCopy = {
      ...localeCopy,
      [source]: {
        message: nextPair.message || '',
        cta: nextPair.cta || '',
        supporting: nextPair.supporting || '',
      },
    }
    setLocaleCopy(nextCopy)
    if (productName) {
      const nextProductPair = {
        message: nextPair.message || '',
        cta: nextPair.cta || '',
        supporting: nextPair.supporting || '',
      }
      setProductCopy((pc) => ({ ...pc, [productName]: nextProductPair }))
      setBrief({
        ...brief,
        products: brief.products.map((p) =>
          p.name === productName
            ? {
                ...p,
                message: nextProductPair.message,
                cta: nextProductPair.cta,
                supporting_copy: nextProductPair.supporting,
              }
            : p,
        ),
      })
    }
    scheduleLocaleAdapt(nextCopy)
  }

  async function handleApply() {
    setBusy(true)
    setError(null)
    try {
      const applyLocales =
        campaignTextMode === 'none'
          ? locales.length
            ? locales.slice(0, 1)
            : ['English']
          : locales.length
            ? locales
            : ['English']
      const source = applyLocales[0] || 'English'
      // Persist the editor into the active product before apply.
      const activePair = {
        message: (captionText || activeProductResolved.message || '').trim(),
        cta: (activeProductResolved.cta || '').trim(),
        supporting: (subcaptionText || activeProductResolved.supporting || '').trim(),
      }
      const productsForApply = brief.products.map((p) =>
        p.name === activeProductName
          ? {
              ...p,
              message: activePair.message || p.message || '',
              cta: activePair.cta || p.cta || '',
              supporting_copy: activePair.supporting || p.supporting_copy || '',
            }
          : p,
      )
      const mergedProductCopy: Record<
        string,
        { message: string; cta: string; supporting?: string }
      > = {}
      for (const p of productsForApply) {
        mergedProductCopy[p.name] = {
          message: (p.message || brief.message || '').trim(),
          cta: (p.cta || brief.cta || '').trim(),
          supporting: (p.supporting_copy || brief.supporting_copy || '').trim(),
        }
      }
      setBrief({ ...brief, products: productsForApply })
      setProductCopy(mergedProductCopy)
      // Campaign locales_copy is only a fallback for products without their own message.
      const locales_copy: Record<string, { message: string; cta: string; supporting?: string }> = {
        [source]: {
          message: activePair.message,
          cta: activePair.cta,
          supporting: activePair.supporting,
        },
      }
      for (const loc of applyLocales) {
        if (loc === source || !manualLocales[loc]) continue
        const pair = localeCopy[loc]
        if (!pair) continue
        locales_copy[loc] = {
          message: pair.message || '',
          cta: pair.cta || '',
          supporting: pair.supporting || '',
        }
      }
      const defaultPlacement =
        campaignTextMode === 'none' ? 'none' : textPlacement === 'none' ? 'none' : textPlacement
      const choices: FinalizeChoices = {
        locales: applyLocales,
        locales_copy,
        product_copy: mergedProductCopy,
        logo_color: logoColor,
        logo_shadow_opacity: logoShadowOp,
        logo_opacity: logoOpacity,
        logo_scale: logoScale,
        text_color: textColor,
        cta_accent: ctaAccent,
        logo_placement: logoPlacement,
        text_placement: defaultPlacement,
        legal_placement: legalPlacement,
        text_placement_by_ratio:
          campaignTextMode === 'none' || textPlacement === 'none'
            ? undefined
            : {
                ...DEFAULT_TEXT_PLACEMENT_BY_RATIO,
                ...textPlacementByRatio,
              },
        ai_decide_placement: textPlacement === 'auto' && campaignTextMode !== 'none',
        font_names: brief.brand_notes.font_names,
        text_scrim: scrim,
        text_scrim_opacity: scrimOp,
        text_shadow_opacity: shadowOp,
        use_logo: useLogo,
        logo_description: useLogo && !hasLogoFile ? logoDescription : null,
        caption_mode: campaignTextMode === 'none' ? 'skip' : captionMode,
        subcaption_mode: campaignTextMode === 'none' ? 'skip' : subcaptionMode,
        caption_text: null,
        caption_style: captionStyle,
        caption_fit: captionFit,
        subcaption_text: null,
        subcaption_style: subcaptionStyle,
        subcaption_fit: subcaptionFit,
        text_render_mode: campaignTextMode,
        skip_suggest: true,
        run_suggest: false,
      }
      await applyFinalize(campaignId, choices)
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const activeHeroIndex = Math.min(heroIndex, Math.max(0, previewTiles.length - 1))

  return (
    <section className="panel step-panel finalize-step">
      <header className="finalize-head">
        <div className="finalize-head-copy">
          <h2>Finalize</h2>
          <p>
            {activeProductName || 'Creative'}
            {hero ? ` · ${ratioPlacementLabel(hero.ratio)}` : ''}
            {creativePlan.finalizeCount > 0
              ? ` · ~${creativePlan.finalizeCount} finals`
              : ' · no text finals'}
            {` · ${previewTiles.length}/${creativePlan.generateCount || previewTiles.length} stills`}
          </p>
        </div>
        <div className="finalize-head-tools">
          <button
            type="button"
            className="btn-ghost"
            disabled={busy || !previewTiles.length || noCampaignText}
            onClick={() => void handleSuggest({ mode: 'style' })}
          >
            {busy && !suggest ? 'Suggesting…' : 'Re-suggest'}
          </button>
          <button
            type="button"
            className="btn-ghost"
            disabled={busy || !previewTiles.length || noCampaignText}
            onClick={() => void handleSuggestText()}
          >
            Suggest text
          </button>
          <button type="button" className="btn-ghost" disabled={busy} onClick={onBack}>
            Back
          </button>
        </div>
      </header>

      {stillGenerating && (
        <div className="banner finalize-banner">
          More creatives still generating. Style now; Apply unlocks when the run finishes.
        </div>
      )}

      <div className="finalize-workspace">
        <div className="finalize-stage">
          {hero ? (
            <div className="finalize-preview-shell">
              {locales.length > 0 && !noCampaignText && (
                <div className="finalize-preview-langs" role="tablist" aria-label="Preview language">
                  {locales.map((loc) => {
                    const on = normalizeLanguageId(loc) === previewLocNorm
                    return (
                      <button
                        key={loc}
                        type="button"
                        role="tab"
                        aria-selected={on}
                        className="btn-ghost"
                        style={{
                          borderColor: on ? 'var(--accent)' : 'var(--border)',
                          background: on ? 'var(--accent-soft)' : 'transparent',
                          color: on ? 'var(--text)' : 'var(--muted)',
                        }}
                        onClick={() => setPreviewLocale(loc)}
                      >
                        {languageLabel(loc)}
                      </button>
                    )
                  })}
                </div>
              )}
              <div
                className="finalize-preview-frame"
                ref={previewFrameRef}
                style={previewFrameStyle}
              >
                <img
                  ref={previewImgRef}
                  className="finalize-hero-img"
                  src={outputUrl(hero.path)}
                  alt={`${hero.product} ${hero.ratio}`}
                  onLoad={measureOverlayBox}
                />
                <div
                  className="finalize-overlay-layer"
                  style={{
                    top: overlayBox.top,
                    left: overlayBox.left,
                    width: overlayBox.width,
                    height: overlayBox.height,
                  }}
                >
                  {useLogo && previewLogoPath && (
                    isOriginalLogoColor(logoColor) ? (
                      <img
                        src={outputUrl(previewLogoPath)}
                        alt=""
                        style={logoPreviewStyle(logoPlacement, {
                          scale: logoScale,
                          opacity: logoOpacity,
                          shadow: logoShadowOp,
                        })}
                      />
                    ) : (
                      <div
                        aria-hidden
                        style={{
                          ...logoPreviewStyle(logoPlacement, {
                            scale: logoScale,
                            opacity: logoOpacity,
                            shadow: logoShadowOp,
                          }),
                          backgroundColor: logoColor,
                          WebkitMaskImage: `url(${outputUrl(previewLogoPath)})`,
                          maskImage: `url(${outputUrl(previewLogoPath)})`,
                          WebkitMaskSize: 'contain',
                          maskSize: 'contain',
                          WebkitMaskRepeat: 'no-repeat',
                          maskRepeat: 'no-repeat',
                          WebkitMaskPosition: 'center',
                          maskPosition: 'center',
                        }}
                      />
                    )
                  )}
                  {scrim &&
                    activePlacement !== 'none' &&
                    activePlacement !== 'auto' &&
                    campaignTextMode !== 'none' && (
                      <div style={previewScrimStyle(activePlacement, scrimOp)} aria-hidden />
                    )}
                  {activePlacement !== 'none' && campaignTextMode !== 'none' && (
                    <div style={placementStyle(activePlacement)}>
                      <div style={{ position: 'relative', zIndex: 1 }}>
                        {captionMode !== 'skip' && (
                          <div
                            className="finalize-preview-caption"
                            style={{
                              color: textColor,
                              textShadow:
                                shadowOp > 0.05
                                  ? `0 2px 8px rgba(0,0,0,${shadowOp})`
                                  : 'none',
                            }}
                          >
                            {previewCopy.message || 'Headline'}
                          </div>
                        )}
                        {subcaptionMode !== 'skip' && (
                          <div
                            className="finalize-preview-sub"
                            style={{
                              color: textColor,
                              textShadow:
                                shadowOp > 0.05
                                  ? `0 1px 6px rgba(0,0,0,${shadowOp})`
                                  : 'none',
                            }}
                          >
                            {previewCopy.supporting || 'Sub-caption'}
                          </div>
                        )}
                        {captionMode !== 'skip' && (
                          <div
                            className="finalize-preview-cta"
                            style={{
                              color: ctaAccent,
                              textShadow:
                                shadowOp > 0.05
                                  ? `0 1px 6px rgba(0,0,0,${shadowOp})`
                                  : 'none',
                            }}
                          >
                            {previewCopy.cta || 'CTA'}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  {Boolean(brief.legal_disclaimer?.trim()) && campaignTextMode !== 'none' && (
                    <div
                      aria-hidden
                      className="finalize-preview-legal"
                      style={{
                        left: legalPlacement === 'right' ? 'auto' : '6%',
                        right: legalPlacement === 'left' ? 'auto' : '6%',
                        width: legalPlacement === 'center' ? '88%' : '55%',
                        textAlign: legalPlacement,
                        color: textColor,
                        textShadow:
                          shadowOp > 0.05 ? `0 1px 4px rgba(0,0,0,${shadowOp})` : 'none',
                      }}
                    >
                      {brief.legal_disclaimer}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="banner finalize-banner">Waiting for the first creative…</div>
          )}

          <div className="finalize-filmstrip" role="listbox" aria-label="Creatives to finalize">
            {previewTiles.map((t, i) => (
              <button
                key={t.path}
                type="button"
                role="option"
                aria-selected={i === activeHeroIndex}
                className={`finalize-film-thumb${i === activeHeroIndex ? ' is-on' : ''}`}
                onClick={() => setHeroIndex(i)}
              >
                <img src={outputUrl(t.path)} alt="" />
                <span>{ratioPlacementLabel(t.ratio)}</span>
              </button>
            ))}
            {stillGenerating && <div className="finalize-film-thumb is-waiting">Waiting…</div>}
          </div>
        </div>

        <aside className="finalize-sidebar">
          <div className="finalize-sidebar-body">
      <div className="finalize-block">
        <div style={{ color: 'var(--muted)', marginBottom: '0.5rem' }}>
          Campaign text rendering
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
          {CAMPAIGN_TEXT_MODES.map((opt) => {
            const selected = campaignTextMode === opt.id
            return (
              <button
                key={opt.id}
                type="button"
                className="btn-ghost"
                style={{
                  borderColor: selected ? 'var(--accent)' : 'var(--border)',
                  background: selected ? 'var(--accent-soft)' : 'transparent',
                  textAlign: 'left',
                }}
                onClick={() => applyCampaignTextMode(opt.id)}
                title={opt.hint}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="finalize-block">
        <div style={{ color: 'var(--muted)', marginBottom: '0.5rem' }}>
          Output languages (up to 5)
          {noCampaignText ? ' · not needed when text is off' : ''}
        </div>
        {locales.length === 0 ? (
          <p style={{ color: 'var(--muted)', fontSize: '0.85rem', margin: '0 0 0.65rem' }}>
            No languages selected.
          </p>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.65rem' }}>
            {locales.map((loc) => {
              const selected = normalizeLanguageId(loc) === previewLocNorm
              return (
              <span
                key={loc}
                className="btn-ghost"
                style={{
                  display: 'inline-flex',
                  gap: '0.45rem',
                  alignItems: 'center',
                  padding: '0.35rem 0.65rem',
                  borderColor: selected ? 'var(--accent)' : 'var(--border)',
                  background: selected ? 'var(--accent-soft)' : 'transparent',
                  cursor: noCampaignText ? 'default' : 'pointer',
                }}
                onClick={() => {
                  if (!noCampaignText) setPreviewLocale(loc)
                }}
                onKeyDown={(e) => {
                  if (noCampaignText) return
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setPreviewLocale(loc)
                  }
                }}
                role={noCampaignText ? undefined : 'button'}
                tabIndex={noCampaignText ? undefined : 0}
                title={noCampaignText ? undefined : `Preview ${languageLabel(loc)}`}
              >
                {languageLabel(loc)}
                <button
                  type="button"
                  className="btn-ghost"
                  style={{ padding: '0 0.25rem', border: 'none', minWidth: 0 }}
                  aria-label={`Remove ${languageLabel(loc)}`}
                  disabled={noCampaignText}
                  onClick={(e) => {
                    e.stopPropagation()
                    setLocales(
                      locales.filter(
                        (x) => normalizeLanguageId(x) !== normalizeLanguageId(loc),
                      ),
                    )
                  }}
                >
                  ×
                </button>
              </span>
              )
            })}
          </div>
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
          <select
            className="field"
            style={{ width: '100%', maxWidth: 320, minWidth: 0 }}
            value={langPick}
            disabled={noCampaignText || locales.length >= 5}
            onChange={(e) => {
              const v = e.target.value
              setLangPick(v)
              if (!v || v === OTHER_LANGUAGE_VALUE) return
              const current = locales.map(normalizeLanguageId)
              if (current.some((x) => normalizeLanguageId(x) === v)) {
                setLangPick('')
                return
              }
              if (current.length >= 5) return
              setLocales([...current, v])
              setLangPick('')
            }}
          >
            <option value="">
              {noCampaignText
                ? 'Not needed (no campaign text)'
                : locales.length >= 5
                  ? 'Limit reached (5)'
                  : 'Add a language…'}
            </option>
            {LANGUAGE_OPTIONS.filter((opt) => !locales.map(normalizeLanguageId).includes(opt.value)).map(
              (opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ),
            )}
            <option value={OTHER_LANGUAGE_VALUE}>Other (type a language)…</option>
          </select>
          {langPick === OTHER_LANGUAGE_VALUE && !noCampaignText && (
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
                disabled={!customLang.trim() || locales.length >= 5}
                onClick={addCustomLanguage}
              >
                Add
              </button>
            </>
          )}
        </div>
      </div>

      <div className="finalize-block">
        <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.65rem' }}>
          <input type="checkbox" checked={useLogo} onChange={(e) => setUseLogo(e.target.checked)} />
          Use logo
        </label>
        {useLogo && (
          <>
            {hasLogoFile ? (
              <LogoPicker
                value={brief.brand_notes}
                onChange={(brand_notes) => setBrief({ ...brief, brand_notes })}
              />
            ) : (
              <label style={{ display: 'block', marginBottom: '0.75rem', color: 'var(--muted)' }}>
                Describe the logo to generate
                <textarea
                  className="field"
                  rows={3}
                  value={logoDescription}
                  onChange={(e) => setLogoDescription(e.target.value)}
                  placeholder="e.g. Minimal wordmark 'ACME' in geometric sans, cyan accent bar under the A"
                  style={{ marginTop: '0.35rem' }}
                />
              </label>
            )}
            <div style={{ color: 'var(--muted)', marginBottom: '0.4rem' }}>Logo placement</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '0.75rem' }}>
              {LOGO_PLACEMENTS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className="btn-ghost placement-chip"
                  style={{
                    borderColor: logoPlacement === opt.id ? 'var(--accent)' : 'var(--border)',
                    background: logoPlacement === opt.id ? 'var(--accent-soft)' : 'transparent',
                    fontSize: '0.85rem',
                  }}
                  onClick={() => {
                    logoPlacementTouched.current = true
                    setLogoPlacement(opt.id)
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <ColorSwatchPicker
              label="Logo color"
              value={logoColor}
              brandColors={brief.brand_notes.colors || []}
              onChange={setLogoColor}
              allowOriginal
            />
            <label style={{ display: 'block', marginBottom: '0.75rem', color: 'var(--muted)' }}>
              Logo shadow {logoShadowOp.toFixed(2)}
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={logoShadowOp}
                onChange={(e) => setLogoShadowOp(Number(e.target.value))}
                style={{ width: '100%' }}
              />
            </label>
            <label style={{ display: 'block', marginBottom: '0.75rem', color: 'var(--muted)' }}>
              Logo opacity {logoOpacity.toFixed(2)}
              <input
                type="range"
                min={0.15}
                max={1}
                step={0.05}
                value={logoOpacity}
                onChange={(e) => setLogoOpacity(Number(e.target.value))}
                style={{ width: '100%' }}
              />
            </label>
            <label style={{ display: 'block', marginBottom: '0.75rem', color: 'var(--muted)' }}>
              Logo size {logoScale.toFixed(2)}×
              <input
                type="range"
                min={0.5}
                max={2}
                step={0.05}
                value={logoScale}
                onChange={(e) => setLogoScale(Number(e.target.value))}
                style={{ width: '100%' }}
              />
            </label>
          </>
        )}
      </div>

      {!noCampaignText && (
        <>
          <div className="finalize-block">
            <div style={{ color: 'var(--muted)', marginBottom: '0.4rem' }}>
              Caption placement for {ratioPlacementLabel(activeRatio)}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
              {TEXT_PLACEMENTS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className="btn-ghost placement-chip"
                  style={{
                    borderColor: activePlacement === opt.id ? 'var(--accent)' : 'var(--border)',
                    background: activePlacement === opt.id ? 'var(--accent-soft)' : 'transparent',
                    fontSize: '0.85rem',
                  }}
                  onClick={() => setPlacementForActiveRatio(opt.id)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="btn-ghost"
              style={{ marginTop: '0.45rem', fontSize: '0.82rem' }}
              onClick={applyPlacementToAllRatios}
              disabled={activePlacement === 'none'}
            >
              Apply this placement to all ratios
            </button>
            {Boolean(brief.legal_disclaimer?.trim()) && (
              <div style={{ marginTop: '0.85rem' }}>
                <div style={{ color: 'var(--muted)', marginBottom: '0.4rem' }}>
                  Legal footer (always bottom)
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                  {(
                    [
                      { id: 'left' as const, label: 'Bottom left' },
                      { id: 'center' as const, label: 'Bottom center' },
                      { id: 'right' as const, label: 'Bottom right' },
                    ] as const
                  ).map((opt) => (
                    <button
                      key={opt.id}
                      type="button"
                      className="btn-ghost placement-chip"
                      style={{
                        borderColor:
                          legalPlacement === opt.id ? 'var(--accent)' : 'var(--border)',
                        background:
                          legalPlacement === opt.id ? 'var(--accent-soft)' : 'transparent',
                        fontSize: '0.85rem',
                      }}
                      onClick={() => setLegalPlacement(opt.id)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {activePlacement === 'auto' && (
              <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '0.35rem' }}>
                Placement comes from styling suggest when you apply.
              </p>
            )}
          </div>

          <SlotEditor
            title={`Caption for ${activeProductName || 'product'} (headline · ${languageLabel(primaryLoc)})`}
            mode={captionMode}
            onMode={(m) => {
              setCaptionMode(m)
              if (m === 'ai' && campaignTextMode === 'composer') setCampaignTextMode('hybrid')
              if (m === 'ai' && campaignTextMode !== 'hybrid' && campaignTextMode !== 'ai') {
                setCampaignTextMode('ai')
              }
            }}
            text={captionText}
            onText={(v) => updateSourceCopy({ message: v })}
            styleNotes={captionStyle}
            onStyle={setCaptionStyle}
            fitNotes={captionFit}
            onFit={setCaptionFit}
            textPlaceholder="Exact caption, or leave blank and use Suggest text"
            disabled={activePlacement === 'none'}
          />

          <SlotEditor
            title="Sub-caption"
            mode={subcaptionMode}
            onMode={(m) => {
              setSubcaptionMode(m)
              if (m === 'ai' && campaignTextMode !== 'ai') setCampaignTextMode('hybrid')
            }}
            text={subcaptionText}
            onText={(v) => updateSourceCopy({ supporting: v })}
            styleNotes={subcaptionStyle}
            onStyle={setSubcaptionStyle}
            fitNotes={subcaptionFit}
            onFit={setSubcaptionFit}
            textPlaceholder="Supporting line under the caption"
            disabled={activePlacement === 'none'}
          />

          <label style={{ display: 'block', marginBottom: '0.85rem', color: 'var(--muted)' }}>
            CTA ({languageLabel(primaryLoc)})
            <input
              className="field"
              value={activeProductResolved.cta || ''}
              onChange={(e) => updateSourceCopy({ cta: e.target.value })}
              placeholder="Call to action"
              style={{ marginTop: '0.35rem' }}
              disabled={activePlacement === 'none' || captionMode === 'skip'}
            />
          </label>

          <ColorSwatchPicker
            label="Text color"
            value={textColor}
            brandColors={brief.brand_notes.colors || []}
            onChange={setTextColor}
          />
          <ColorSwatchPicker
            label="CTA accent"
            value={ctaAccent}
            brandColors={brief.brand_notes.colors || []}
            onChange={setCtaAccent}
          />

          <label
            style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}
          >
            <input type="checkbox" checked={scrim} onChange={(e) => setScrim(e.target.checked)} />
            Text scrim
          </label>
          {scrim && (
            <label style={{ display: 'block', marginBottom: '0.75rem', color: 'var(--muted)' }}>
              Scrim opacity {scrimOp.toFixed(2)}
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={scrimOp}
                onChange={(e) => setScrimOp(Number(e.target.value))}
                style={{ width: '100%' }}
              />
            </label>
          )}
          <label style={{ display: 'block', marginBottom: '1rem', color: 'var(--muted)' }}>
            Text shadow {shadowOp.toFixed(2)}
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={shadowOp}
              onChange={(e) => setShadowOp(Number(e.target.value))}
              style={{ width: '100%' }}
            />
          </label>

          {localeSyncBusy && (
            <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '0.65rem' }}>
              Updating other languages from {languageLabel(primaryLoc)}…
            </p>
          )}
          {locales.filter((loc) => normalizeLanguageId(loc) !== primaryLoc).length > 0 && (
            <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '0.65rem' }}>
              Other languages follow {languageLabel(primaryLoc)} unless you check Edit manually.
            </p>
          )}
          {locales
            .filter((loc) => normalizeLanguageId(loc) !== primaryLoc)
            .map((loc) => {
            const isManual = Boolean(manualLocales[loc])
            const pair = localeCopy[loc] || {
              message: captionText || brief.message,
              cta: brief.cta,
              supporting: subcaptionText,
            }
            return (
              <div key={loc} style={{ marginBottom: '0.85rem' }}>
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '0.65rem',
                    alignItems: 'center',
                    marginBottom: '0.25rem',
                  }}
                >
                  <div
                    style={{ color: 'var(--muted)', cursor: 'pointer' }}
                    onClick={() => setPreviewLocale(loc)}
                    title={`Preview ${languageLabel(loc)}`}
                  >
                    {languageLabel(loc)}
                    {normalizeLanguageId(loc) === previewLocNorm ? ' · previewing' : ''}
                  </div>
                  <label
                    style={{
                      display: 'flex',
                      gap: '0.35rem',
                      alignItems: 'center',
                      fontSize: '0.82rem',
                      color: 'var(--muted)',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={isManual}
                      onChange={(e) =>
                        setManualLocales((prev) => ({
                          ...prev,
                          [loc]: e.target.checked,
                        }))
                      }
                    />
                    Edit manually
                  </label>
                </div>
                <input
                  className="field"
                  value={pair.message}
                  onChange={(e) =>
                    setLocaleCopy({
                      ...localeCopy,
                      [loc]: { ...pair, message: e.target.value },
                    })
                  }
                  placeholder="Headline"
                  style={{ marginBottom: '0.35rem' }}
                  disabled={
                    activePlacement === 'none' || captionMode === 'skip' || !isManual
                  }
                />
                <input
                  className="field"
                  value={pair.supporting || ''}
                  onChange={(e) =>
                    setLocaleCopy({
                      ...localeCopy,
                      [loc]: { ...pair, supporting: e.target.value },
                    })
                  }
                  placeholder="Sub-caption"
                  style={{ marginBottom: '0.35rem' }}
                  disabled={
                    activePlacement === 'none' || subcaptionMode === 'skip' || !isManual
                  }
                />
                <input
                  className="field"
                  value={pair.cta}
                  onChange={(e) =>
                    setLocaleCopy({
                      ...localeCopy,
                      [loc]: { ...pair, cta: e.target.value },
                    })
                  }
                  placeholder="CTA"
                  disabled={
                    activePlacement === 'none' || captionMode === 'skip' || !isManual
                  }
                />
              </div>
            )
          })}
        </>
      )}


            {error && <div className="banner banner-danger">{error}</div>}
          </div>
          <div className="finalize-sidebar-foot">
            <p className="finalize-apply-summary">
              {creativePlan.finalizeCount > 0
                ? `About to create ~${creativePlan.finalizeCount} stamped final${creativePlan.finalizeCount === 1 ? '' : 's'}.`
                : 'About to finish without language text finals.'}
            </p>
            <button
              type="button"
              className={applyHighlight && !stillGenerating ? 'btn apply-ready' : 'btn'}
              disabled={
                busy ||
                stillGenerating ||
                !previewTiles.length ||
                (useLogo && !hasLogoFile && !logoDescription.trim())
              }
              onClick={handleApply}
            >
              {stillGenerating
                ? 'Waiting for creatives…'
                : busy
                  ? 'Applying…'
                  : creativePlan.finalizeCount > 0
                    ? `Apply · ~${creativePlan.finalizeCount} final${creativePlan.finalizeCount === 1 ? '' : 's'}`
                    : 'Apply overlays'}
            </button>
          </div>
        </aside>
      </div>
    </section>
  )
}

function SlotEditor({
  title,
  mode,
  onMode,
  text,
  onText,
  styleNotes,
  onStyle,
  fitNotes,
  onFit,
  textPlaceholder,
  disabled,
}: {
  title: string
  mode: SlotTextMode
  onMode: (m: SlotTextMode) => void
  text: string
  onText: (v: string) => void
  styleNotes: string
  onStyle: (v: string) => void
  fitNotes: string
  onFit: (v: string) => void
  textPlaceholder: string
  disabled?: boolean
}) {
  return (
    <div className="finalize-slot">
      <div className="finalize-slot-title">{title}</div>
      <div className="finalize-chip-row">
        {SLOT_MODES.map((opt) => (
          <button
            key={opt.id}
            type="button"
            className="btn-ghost placement-chip"
            disabled={disabled}
            style={{
              borderColor: mode === opt.id ? 'var(--accent)' : 'var(--border)',
              background: mode === opt.id ? 'var(--accent-soft)' : 'transparent',
              fontSize: '0.8rem',
            }}
            onClick={() => onMode(opt.id)}
          >
            {opt.label}
          </button>
        ))}
      </div>
      {mode !== 'skip' && !disabled && (
        <>
          <label className="finalize-field">
            Text
            <textarea
              className="field"
              rows={2}
              value={text}
              onChange={(e) => onText(e.target.value)}
              placeholder={textPlaceholder}
            />
          </label>
          <label className="finalize-field">
            Text style
            <input
              className="field"
              value={styleNotes}
              onChange={(e) => onStyle(e.target.value)}
              placeholder="e.g. Bold condensed sans, high contrast"
            />
          </label>
          <label className="finalize-field">
            How it should fit
            <input
              className="field"
              value={fitNotes}
              onChange={(e) => onFit(e.target.value)}
              placeholder="e.g. Sit in open sky, avoid the face"
            />
          </label>
        </>
      )}
    </div>
  )
}
