import type { CreativePlan } from '../lib/creativeCounts'
import { formatPipelineSummary } from '../lib/creativeCounts'

/** Friendly plan totals for the top of a wizard step (not inside stepper tabs). */
export function PipelineCountBanner({
  plan,
  readyStills,
  emphasis,
}: {
  plan: CreativePlan | null | undefined
  /** How many no-text stills are already on disk (Finalize / Generate progress). */
  readyStills?: number
  /** Extra line under the summary, e.g. near a Generate button. */
  emphasis?: string
}) {
  if (!plan || plan.generateCount <= 0) return null
  return (
    <div className="generate-count-summary pipeline-count-banner" aria-live="polite">
      <p className="count-line">{formatPipelineSummary(plan)}</p>
      <p className="count-line">
        Generate makes {plan.generateCount} no-text still
        {plan.generateCount === 1 ? '' : 's'}
        {typeof readyStills === 'number'
          ? ` · ${Math.min(readyStills, plan.generateCount)}/${plan.generateCount} ready`
          : ''}
        {plan.finalizeCount > 0
          ? ` · Finalize stamps ~${plan.finalizeCount} final${plan.finalizeCount === 1 ? '' : 's'} (${plan.localeCount} language${plan.localeCount === 1 ? '' : 's'})`
          : ' · Finalize can skip text (no finals planned)'}
      </p>
      {emphasis ? <p className="count-line count-emphasis">{emphasis}</p> : null}
    </div>
  )
}
