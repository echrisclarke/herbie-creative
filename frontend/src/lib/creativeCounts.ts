import type { Brief } from './api'

export type CreativePlan = {
  productCount: number
  ratioCount: number
  framingExtra: number
  perProductStills: number
  generateCount: number
  localeCount: number
  finalizeCount: number
  pipelineTotal: number
}

type CountOpts = {
  outputs?: string[]
  framing?: Brief['framing']
  /** Override locales (Finalize UI). When omitted, use brief.localize_to. */
  locales?: string[]
  /** When true, Apply will not create text finals. */
  noCampaignText?: boolean
}

export function ratioCount(brief: Pick<Brief, 'outputs'>, outputs?: string[]): number {
  const list = outputs?.length ? outputs : brief.outputs
  return Math.max(1, list?.length || 3)
}

export function framingExtra(
  framing: Brief['framing'] | undefined,
): number {
  return framing === 'both' || framing === 'close-up' ? 1 : 0
}

export function perProductStills(
  brief: Pick<Brief, 'outputs' | 'framing'>,
  opts?: Pick<CountOpts, 'outputs' | 'framing'>,
): number {
  const framing = opts?.framing ?? brief.framing
  return ratioCount(brief, opts?.outputs) + framingExtra(framing)
}

export function localeCountForPlan(
  brief: Pick<Brief, 'localize_to' | 'text_render_mode'>,
  opts?: Pick<CountOpts, 'locales' | 'noCampaignText'>,
): number {
  if (opts?.noCampaignText) return 0
  if (opts?.locales) return Math.max(0, opts.locales.length)
  if (brief.text_render_mode === 'none') return 0
  const locs = [...new Set((brief.localize_to || []).map((l) => String(l || '').trim()).filter(Boolean))]
  return Math.max(1, locs.length)
}

export function countNoTextCreatives(
  brief: Pick<Brief, 'products' | 'outputs' | 'framing'>,
  opts?: Pick<CountOpts, 'outputs' | 'framing'>,
): number {
  const products = Math.max(0, brief.products?.length || 0)
  return products * perProductStills(brief, opts)
}

export function planCreativeCounts(
  brief: Pick<
    Brief,
    'products' | 'outputs' | 'framing' | 'localize_to' | 'text_render_mode'
  >,
  opts?: CountOpts,
): CreativePlan {
  const productCount = Math.max(0, brief.products?.length || 0)
  const ratios = ratioCount(brief, opts?.outputs)
  const extra = framingExtra(opts?.framing ?? brief.framing)
  const perProduct = ratios + extra
  const generateCount = productCount * perProduct
  const localeCount = localeCountForPlan(brief, opts)
  const finalizeCount = generateCount * localeCount
  return {
    productCount,
    ratioCount: ratios,
    framingExtra: extra,
    perProductStills: perProduct,
    generateCount,
    localeCount,
    finalizeCount,
    pipelineTotal: generateCount + finalizeCount,
  }
}

export function formatPipelineSummary(plan: CreativePlan): string {
  if (plan.finalizeCount > 0) {
    return `Pipeline: ${plan.pipelineTotal} creatives (${plan.generateCount} stills + ${plan.finalizeCount} finals)`
  }
  return `Pipeline: ${plan.generateCount} stills`
}
