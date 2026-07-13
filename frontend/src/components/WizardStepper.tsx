const STEPS = ['Intake', 'Review', 'Generate', 'Finalize', 'Motion', 'Results'] as const

export function WizardStepper({
  step,
  onStep,
  unlockedThrough = 0,
  isStepEnabled,
}: {
  step: number
  onStep?: (n: number) => void
  /** Highest step reached this run (or unlocked when reopening a campaign). */
  unlockedThrough?: number
  /** Extra gate per step (e.g. Motion needs a report). */
  isStepEnabled?: (n: number) => boolean
}) {
  return (
    <nav className="stepper" aria-label="Campaign steps">
      {STEPS.map((label, i) => {
        const active = i === step
        const reachable =
          i <= unlockedThrough && (isStepEnabled ? isStepEnabled(i) : true)
        const done = reachable && !active
        return (
          <button
            key={label}
            type="button"
            className={`btn-ghost stepper-btn${active ? ' is-active' : ''}${done ? ' is-done' : ''}`}
            style={{
              borderColor: active ? 'var(--accent)' : 'var(--border)',
              color: active || done ? 'var(--text)' : 'var(--muted)',
              background: active ? 'var(--accent-soft)' : 'transparent',
            }}
            onClick={() => {
              if (onStep && reachable && i !== step) onStep(i)
            }}
            disabled={!reachable}
            aria-current={active ? 'step' : undefined}
            title={label}
          >
            <span className="stepper-num">{i + 1}.</span>{' '}
            <span className="stepper-label">{label}</span>
          </button>
        )
      })}
    </nav>
  )
}
