export type Product = {
  name: string
  category: string
  product_mode: 'use-provided' | 'generate-concept'
  product_role: string
  asset_hint: string
  input_asset_path: string | null
  input_asset_paths?: string[]
  landing_url: string | null
  notes: string
  /** Optional overrides; empty falls back to campaign message/cta/direction. */
  message?: string
  cta?: string
  supporting_copy?: string
  creative_direction?: string
  style_reference_paths?: string[]
  background_reference_paths?: string[]
}

export type SlotRenderChoices = {
  logo: 'pillow' | 'skip'
  headline: 'pillow' | 'ai' | 'skip'
  supporting: 'pillow' | 'ai' | 'skip'
  cta: 'pillow' | 'skip'
  legal: 'pillow' | 'skip'
}

export type TextPlacement =
  | 'bottom-left'
  | 'bottom-center'
  | 'bottom-right'
  | 'middle-left'
  | 'middle-center'
  | 'middle-right'
  | 'top-left'
  | 'top-center'
  | 'top-right'
  | 'none'
  | 'auto'

export type SlotTextMode = 'composer' | 'ai' | 'skip'

export type BrandNotes = {
  tone: string
  colors: string[]
  font_names: string[]
  font_alternates: string[]
  logo_required: boolean
  logo_path: string | null
  logo_paths?: string[]
  logo_description?: string | null
  logo_placement?: string
  text_placement?: TextPlacement
  legal_placement?: 'left' | 'center' | 'right'
  logo_color?: string | null
  logo_shadow_opacity?: number | null
  logo_opacity?: number | null
  logo_scale?: number | null
  text_color?: string | null
  text_scrim?: boolean | null
  text_scrim_opacity?: number | null
  text_shadow_opacity?: number | null
  forbidden_words: string[]
  font_file_path?: string | null
}

export type Brief = {
  campaign_name: string
  brand: string
  market: string
  audience: string
  message: string
  cta: string
  supporting_copy?: string
  legal_disclaimer?: string
  creative_direction: string
  visual_style_tags: string[]
  motion_notes: string
  products: Product[]
  brand_notes: BrandNotes
  localize_to: string[]
  /** Cached per-language overlay copy from Review / Finalize auto-translate. */
  locales_copy?: Record<string, { message: string; cta: string; supporting?: string }>
  outputs: string[]
  framing?: 'close-up' | 'zoomed' | 'both'
  text_render_mode?: 'composer' | 'ai' | 'hybrid' | 'pillow' | 'none' | 'later'
  slot_render?: SlotRenderChoices
  style_reference_paths?: string[]
  likeness_reference_paths?: string[]
  background_reference_paths?: string[]
}

export type AssetManifest = {
  products: Array<{
    product_name: string
    product_mode: string
    has_image: boolean
    path: string | null
    missing_message: string | null
  }>
  logo_path: string | null
  ready: boolean
  blockers: string[]
}

export type CreativeResult = {
  product: string
  ratio: string
  path: string
  locale?: string
  creative_path?: string | null
  source: string
  image_provider: string
  fallback_triggered: boolean
  motion_path: string | null
  compliance: Record<string, boolean>
  message?: string
  cta?: string
}

export type Report = {
  campaign_id: string
  started_at: string
  finished_at: string
  creatives: CreativeResult[]
  totals: Record<string, number>
}

export type SampleInfo = {
  id: string
  title: string
  brief: string
  description: string
  available: boolean
}

export type FinalizeSuggest = {
  logo_color?: string
  text_color?: string
  cta_accent?: string
  logo_placement?: string
  text_placement?: TextPlacement | string
  font_names?: string[]
  text_scrim?: boolean
  text_scrim_opacity?: number
  text_shadow_opacity?: number
  styling_notes?: string
  locales?: Record<string, { message?: string; cta?: string; supporting?: string }>
}

export type FinalizeChoices = {
  locales?: string[]
  locales_copy?: Record<string, { message: string; cta: string; supporting?: string }>
  logo_color?: string | null
  logo_shadow_opacity?: number | null
  logo_opacity?: number | null
  logo_scale?: number | null
  text_color?: string | null
  cta_accent?: string | null
  logo_placement?: string | null
  text_placement?: TextPlacement | null
  text_placement_by_ratio?: Record<string, TextPlacement | string> | null
  legal_placement?: 'left' | 'center' | 'right' | null
  font_names?: string[] | null
  text_scrim?: boolean | null
  text_scrim_opacity?: number | null
  text_shadow_opacity?: number | null
  use_logo?: boolean
  logo_description?: string | null
  caption_mode?: SlotTextMode
  subcaption_mode?: SlotTextMode
  caption_text?: string | null
  caption_style?: string | null
  caption_fit?: string | null
  subcaption_text?: string | null
  subcaption_style?: string | null
  subcaption_fit?: string | null
  ai_decide_placement?: boolean
  text_render_mode?: 'composer' | 'ai' | 'hybrid' | 'pillow' | 'none' | 'later'
  skip_suggest?: boolean
  run_suggest?: boolean
  /** English source copy keyed by product name for multi-product campaigns. */
  product_copy?: Record<string, { message: string; cta: string; supporting?: string }>
}

const API = import.meta.env.DEV ? '/api' : ''

function apiFetch(input: string, init?: RequestInit) {
  return fetch(input, { ...init, credentials: 'include' })
}

export type AuthUser = {
  id: string
  email: string
  is_admin: boolean
}

export async function fetchAuthMe() {
  const res = await apiFetch(`${API}/auth/me`)
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ hosted: boolean; user: AuthUser | null }>
}

export async function login(email: string, password: string) {
  const res = await apiFetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{
    ok: boolean
    hosted: boolean
    user: AuthUser | null
  }>
}

export async function logout() {
  const res = await apiFetch(`${API}/auth/logout`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ ok: boolean }>
}

export async function createInvitedUser(body: {
  email: string
  password: string
  is_admin?: boolean
}) {
  const res = await apiFetch(`${API}/auth/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ ok: boolean; user: AuthUser }>
}

export type KeyStatus = {
  configured: boolean
  source: string | null
  hint: string | null
  value: string | null
  label: string
  help: string
  env_name: string
}

export type SettingsKeys = {
  openai: KeyStatus
  xai: KeyStatus
  google_fonts: KeyStatus
  stored_file: string
  has_stored_file: boolean
}

export type GalleryCreative = {
  campaign_id: string
  campaign_name: string
  brand: string
  product: string
  ratio: string
  kind: string
  url: string
  filename: string
}

export type GalleryCampaign = {
  id: string
  name: string
  brand: string
  creative_count: number
  ratios?: string[]
  products?: string[]
}

export type GalleryResponse = {
  campaigns: GalleryCampaign[]
  creatives: GalleryCreative[]
  filters: {
    ratios: string[]
    brands: string[]
    campaigns: GalleryCampaign[]
    kinds?: string[]
  }
}

export async function getHealth() {
  const res = await apiFetch(`${API}/health`)
  return res.json() as Promise<{
    ok: boolean
    service?: string
    hosted?: boolean
    desktop_tools?: boolean
    motion_available: boolean
    openai_configured?: boolean
    google_fonts_catalog?: boolean
  }>
}

export async function fetchSettingsKeys(reveal = false) {
  const res = await apiFetch(`${API}/settings/keys?reveal=${reveal ? 'true' : 'false'}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<SettingsKeys>
}

export async function saveSettingsKeys(body: {
  openai_api_key?: string
  xai_api_key?: string
  google_fonts_api_key?: string
}) {
  const res = await apiFetch(`${API}/settings/keys`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<SettingsKeys>
}

export async function clearApiKey(which: 'openai' | 'xai' | 'google_fonts') {
  const payload =
    which === 'openai'
      ? { clear_openai: true }
      : which === 'xai'
        ? { clear_xai: true }
        : { clear_google_fonts: true }
  const res = await apiFetch(`${API}/settings/keys`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<SettingsKeys>
}

export async function fetchGallery(params?: {
  campaign_id?: string
  ratio?: string
  brand?: string
  kind?: string
}) {
  const q = new URLSearchParams()
  if (params?.campaign_id) q.set('campaign_id', params.campaign_id)
  if (params?.ratio) q.set('ratio', params.ratio)
  if (params?.brand) q.set('brand', params.brand)
  if (params?.kind) q.set('kind', params.kind)
  const qs = q.toString()
  const res = await apiFetch(`${API}/gallery${qs ? `?${qs}` : ''}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<GalleryResponse>
}

export type PastCampaign = {
  id: string
  name: string
  brand: string
  stage: 'results' | 'finalize' | 'review' | 'draft' | 'empty' | string
  is_draft?: boolean
  has_brief: boolean
  has_report: boolean
  creative_count: number
  modified_at: string | null
  thumb_url: string | null
  folder_path?: string | null
}

export type OpenCampaignResult = {
  campaign_id: string
  name: string
  brand: string
  stage: string
  is_draft?: boolean
  brief: Brief | null
  asset_manifest: AssetManifest | null
  missing_fields: string[]
  report: Report | null
  tiles: CreativeResult[]
}

export async function listPastCampaigns() {
  const res = await apiFetch(`${API}/campaigns`)
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ campaigns: PastCampaign[] }>
}

export async function openPastCampaign(campaignId: string) {
  const res = await apiFetch(`${API}/campaigns/${campaignId}/open`)
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<OpenCampaignResult>
}

export async function saveDraft(campaignId: string) {
  const res = await apiFetch(`${API}/campaigns/${campaignId}/draft`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ ok: boolean; campaign_id: string; status: string }>
}

export async function deleteCampaign(campaignId: string) {
  const res = await apiFetch(`${API}/campaigns/${encodeURIComponent(campaignId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ ok: boolean; deleted: string }>
}

export async function deleteCreatives(
  items: Array<{ campaign_id: string; path: string }>,
) {
  const res = await apiFetch(`${API}/creatives/delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{
    ok: boolean
    deleted: Array<{ campaign_id: string; path: string }>
    missing: Array<{ campaign_id: string; path: string }>
    deleted_count: number
  }>
}

export async function revealCampaignFolder(campaignId?: string | null) {
  const path = campaignId
    ? `${API}/campaigns/${encodeURIComponent(campaignId)}/reveal`
    : `${API}/campaigns/reveal-root`
  const res = await apiFetch(path, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ ok: boolean; path: string }>
}

export async function cleanupEphemeral(campaignId: string | null) {
  if (!campaignId) return { ok: true, deleted: false }
  const res = await apiFetch(`${API}/campaigns/cleanup-ephemeral`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ campaign_id: campaignId }),
  })
  if (!res.ok) return { ok: false, deleted: false }
  return res.json() as Promise<{ ok: boolean; deleted: boolean }>
}

export async function listSamples() {
  const res = await apiFetch(`${API}/samples`)
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ samples: SampleInfo[] }>
}

export async function runAssignmentCli() {
  const res = await apiFetch(`${API}/tools/run-assignment-cli`, { method: 'POST' })
  const body = await res.json().catch(() => ({} as Record<string, unknown>))
  if (!res.ok) {
    const detail = body?.detail
    const nested =
      detail && typeof detail === 'object'
        ? (detail as { error?: string; command?: string })
        : null
    const message =
      (typeof detail === 'string' && detail) ||
      nested?.error ||
      (nested?.command ? `Could not open a terminal. Run manually: ${nested.command}` : null) ||
      (typeof body?.error === 'string' ? body.error : null) ||
      'Could not start local CLI'
    throw new Error(message)
  }
  return body as {
    ok: boolean
    command: string
    cwd: string
    brief: string
    message?: string
  }
}

export async function createFromSample(sampleId: string) {
  const res = await apiFetch(`${API}/campaigns/from-sample/${sampleId}`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{
    campaign_id: string
    brief: Brief
    asset_manifest: AssetManifest
    missing_fields: string[]
    sample_id: string
  }>
}

export async function createCampaign(
  briefText: string,
  files: File[],
  roles: string[] = [],
) {
  const form = new FormData()
  if (briefText) form.append('brief_text', briefText)
  for (const f of files) form.append('files', f)
  for (const role of roles) form.append('roles', role)
  const res = await apiFetch(`${API}/campaigns`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ campaign_id: string }>
}

export async function parseCampaign(id: string) {
  const res = await apiFetch(`${API}/campaigns/${id}/parse`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{
    brief: Brief
    asset_manifest: AssetManifest
    missing_fields: string[]
    product_seeds?: ProductSeedsStatus
    product_seeds_pending?: boolean
  }>
}

export type ProductSeedsStatus = {
  status: 'idle' | 'pending' | 'ready' | 'failed'
  needed: boolean
  items: Array<{
    product_name: string
    status: 'pending' | 'ready' | 'failed'
    path?: string | null
    error?: string | null
  }>
  error?: string | null
  brief?: Brief | null
}

export async function getProductSeeds(id: string) {
  const res = await apiFetch(`${API}/campaigns/${id}/product-seeds`)
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<ProductSeedsStatus>
}

export async function retryProductSeeds(id: string) {
  const res = await apiFetch(`${API}/campaigns/${id}/product-seeds/retry`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<ProductSeedsStatus>
}

export async function saveCampaign(id: string, brief: Brief) {
  const res = await apiFetch(`${API}/campaigns/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(brief),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function approveCampaign(id: string, brief: Brief) {
  const res = await apiFetch(`${API}/campaigns/${id}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(brief),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function uploadAssets(id: string, files: File[], roles: string[] = []) {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  for (const role of roles) form.append('roles', role)
  const res = await apiFetch(`${API}/campaigns/${id}/assets`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{
    saved: string[]
    brief: Brief | null
    asset_manifest: AssetManifest | null
    missing_fields: string[]
  }>
}

export type ImageQuality = 'low' | 'medium' | 'high'

export async function generateCampaign(
  id: string,
  // Christian: deprecated motion arg. Still sent for back-compat; server ignores enabled.
  // Real motion is generateMotion() on Results.
  motion: { enabled: boolean; duration_seconds: number; ratios?: string[] },
  imageQuality: ImageQuality = 'medium',
  options?: {
    outputs?: string[]
    framing?: 'close-up' | 'zoomed' | 'both'
    creatives_only?: boolean
    source_paths?: string[]
  },
) {
  const res = await apiFetch(`${API}/campaigns/${id}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      motion: {
        enabled: motion.enabled,
        duration_seconds: motion.duration_seconds,
        ratios: motion.ratios || [],
      },
      image_quality: imageQuality,
      outputs: options?.outputs,
      framing: options?.framing,
      creatives_only: options?.creatives_only ?? true,
      source_paths: options?.source_paths || [],
    }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ job_id: string }>
}

export async function generateMotion(
  id: string,
  creativePath: string,
  durationSeconds = 6,
  prompt?: string,
  promptExtra?: string,
) {
  const lower = creativePath.replace(/\\/g, '/').toLowerCase()
  const stem = (lower.split('/').pop() || 'creative').replace(/\.(png|jpg|jpeg|webp)$/i, '')
  // Unique mp4 beside the still (creative.png → creative.mp4, final.en.png → final.en.mp4).
  const outputName = `${stem || 'creative'}.mp4`
  const res = await apiFetch(`${API}/campaigns/${id}/motion`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      creative_path: creativePath,
      duration_seconds: durationSeconds,
      output_name: outputName,
      ...(prompt?.trim() ? { prompt: prompt.trim() } : {}),
      ...(promptExtra?.trim() ? { prompt_extra: promptExtra.trim() } : {}),
    }),
  })
  if (!res.ok) {
    const text = await res.text()
    let message = text || `Motion request failed (${res.status})`
    try {
      const parsed = JSON.parse(text) as { detail?: unknown }
      if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
        message = parsed.detail
      }
    } catch {
      /* keep raw response text */
    }
    throw new Error(message)
  }
  return res.json() as Promise<{ ok: boolean; motion_path: string }>
}

export async function suggestFinalize(id: string) {
  const res = await apiFetch(`${API}/campaigns/${id}/suggest-finalize`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ ok: boolean; suggest: FinalizeSuggest }>
}

export async function applyFinalize(id: string, choices: FinalizeChoices) {
  const res = await apiFetch(`${API}/campaigns/${id}/finalize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(choices),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ ok: boolean; report: Report }>
}

export async function adaptLocalizeCopy(
  id: string,
  body: {
    message: string
    cta: string
    supporting?: string
    locales: string[]
    locked_locales?: string[]
    existing?: Record<string, { message: string; cta: string; supporting?: string }>
  },
) {
  const res = await apiFetch(`${API}/campaigns/${id}/localize-copy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: body.message || '',
      cta: body.cta || '',
      supporting: body.supporting ?? '',
      locales: body.locales || [],
      locked_locales: body.locked_locales || [],
      existing: body.existing || {},
    }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{
    ok: boolean
    locales: Record<string, { message: string; cta: string; supporting?: string }>
  }>
}

export async function suggestCopy(id: string) {
  const res = await apiFetch(`${API}/campaigns/${id}/suggest-copy`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ ok: boolean; brief: Brief; draft: Record<string, string> }>
}

export async function fetchReport(id: string) {
  const res = await apiFetch(`${API}/campaigns/${id}/report.json`)
  if (!res.ok) throw new Error('Report not ready')
  return res.json() as Promise<Report>
}

export async function searchFonts(query: string) {
  const res = await apiFetch(`${API}/fonts/google?query=${encodeURIComponent(query)}`)
  if (!res.ok) return { fonts: [] as string[] }
  return res.json() as Promise<{ fonts: string[] }>
}

export function outputUrl(path: string) {
  let p = path.replace(/\\/g, '/')
  const marker = '/campaigns/'
  const idx = p.toLowerCase().lastIndexOf(marker)
  if (idx >= 0) p = p.slice(idx + marker.length)
  else if (p.toLowerCase().startsWith('campaigns/')) p = p.slice('campaigns/'.length)

  // Repo seed assets are mounted at /sample-assets (not under /outputs/campaigns).
  const sampleIdx = p.toLowerCase().lastIndexOf('sample-assets/')
  if (sampleIdx >= 0) {
    return `/${p.slice(sampleIdx)}`
  }
  if (p.toLowerCase().startsWith('sample-assets/')) {
    return `/${p}`
  }

  if (p.startsWith('/')) return p
  return `/outputs/${p}`
}

export function subscribeEvents(
  id: string,
  onEvent: (event: string, data: Record<string, unknown>) => void,
) {
  const es = new EventSource(`${API}/campaigns/${id}/events`)
  const handler = (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data)
      onEvent(event.type, data)
    } catch {
      onEvent(event.type, {})
    }
  }
  ;[
    'connected',
    'tile.started',
    'tile.completed',
    'tile.failed',
    'run.completed',
    'run.failed',
    // Christian: deprecated for UI Results (uses REST). Still emitted by CLI _maybe_motion.
    'motion.started',
    'motion.completed',
    'motion.skipped',
    'product_seeds.started',
    'product_seed.started',
    'product_seed.completed',
    'product_seed.failed',
    'product_seeds.ready',
    'product_seeds.failed',
  ].forEach((name) => es.addEventListener(name, handler as EventListener))
  es.onmessage = handler
  return es
}
