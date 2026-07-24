import type { BrandNotes } from '../lib/api'
import { outputThumbUrl } from '../lib/api'

export function logoCandidates(notes: BrandNotes): string[] {
  const listed = (notes.logo_paths || []).filter(Boolean)
  if (listed.length) return listed
  return notes.logo_path ? [notes.logo_path] : []
}

function sameLogo(a: string, b: string) {
  if (a === b) return true
  const an = a.replace(/\\/g, '/').split('/').pop() || a
  const bn = b.replace(/\\/g, '/').split('/').pop() || b
  return an === bn
}

export function LogoPicker({
  value,
  onChange,
}: {
  value: BrandNotes
  onChange: (next: BrandNotes) => void
}) {
  const candidates = logoCandidates(value)
  if (!candidates.length) return null

  const active = value.logo_path || candidates[0]

  return (
    <div className="logo-picker">
      <div className="logo-picker-label">
        {candidates.length > 1 ? 'Choose logo for this campaign' : 'Campaign logo'}
      </div>
      <div className="logo-picker-grid">
        {candidates.map((path) => {
          const on = sameLogo(path, active)
          return (
            <button
              key={path}
              type="button"
              className={on ? 'logo-picker-thumb is-on' : 'logo-picker-thumb'}
              onClick={() =>
                onChange({
                  ...value,
                  logo_path: path,
                  logo_paths: candidates,
                })
              }
              title={path.replace(/\\/g, '/').split('/').pop() || path}
            >
              <img src={outputThumbUrl(path, 160)} alt="" loading="lazy" decoding="async" />
            </button>
          )
        })}
      </div>
      <p className="logo-picker-hint">
        Active: {active.replace(/\\/g, '/').split('/').pop() || active}
      </p>
    </div>
  )
}
