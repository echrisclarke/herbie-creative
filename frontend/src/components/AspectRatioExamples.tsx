import { useEffect, useState } from 'react'
import {
  ASPECT_RATIO_EXAMPLES,
  CLOSEUP_EXAMPLE,
  type AspectExample,
} from '../lib/aspectExamples'

export function AspectRatioExamples({
  selected,
  onToggle,
  showCloseup = true,
  compact = false,
}: {
  selected?: string[]
  onToggle?: (ratio: string) => void
  showCloseup?: boolean
  compact?: boolean
}) {
  const tiles: AspectExample[] = showCloseup
    ? [CLOSEUP_EXAMPLE, ...ASPECT_RATIO_EXAMPLES]
    : ASPECT_RATIO_EXAMPLES
  const [preview, setPreview] = useState<AspectExample | null>(null)

  useEffect(() => {
    if (!preview) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setPreview(null)
    }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [preview])

  return (
    <>
      <div className={compact ? 'aspect-examples-grid is-compact' : 'aspect-examples-grid'}>
        {tiles.map((ex) => {
          const selectable =
            Boolean(onToggle) &&
            ASPECT_RATIO_EXAMPLES.some((r) => r.ratio === ex.ratio)
          const isOn = selectable ? (selected || []).includes(ex.ratio) : true
          const className = [
            'panel',
            'aspect-example-card',
            selectable && isOn ? 'is-on' : '',
            selectable && !isOn ? 'is-off' : '',
          ]
            .filter(Boolean)
            .join(' ')

          return (
            <div key={ex.ratio} className={className}>
              <button
                type="button"
                className="aspect-example-preview-btn"
                onClick={() => setPreview(ex)}
                aria-label={`Preview ${ex.label} example`}
              >
                <div className="aspect-example-media">
                  <div className="aspect-example-frame" style={{ aspectRatio: ex.cssRatio }}>
                    <img src={ex.src} alt="" loading="lazy" />
                  </div>
                </div>
              </button>
              <div className="aspect-example-caption">
                {selectable ? (
                  <label className="aspect-example-select">
                    <input
                      type="checkbox"
                      checked={isOn}
                      onChange={() => onToggle?.(ex.ratio)}
                    />
                    <span className="aspect-example-label">
                      {ex.label}
                      {ex.hint ? ` ${ex.hint}` : ''}
                    </span>
                  </label>
                ) : (
                  <div className="aspect-example-label">
                    {ex.label}
                    {ex.hint ? ` ${ex.hint}` : ''}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {preview && (
        <div
          className="modal-backdrop aspect-preview-backdrop"
          onClick={() => setPreview(null)}
          role="presentation"
        >
          <div
            className="panel modal-dialog aspect-preview-dialog"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={`${preview.label} preview`}
          >
            <div className="modal-dialog-head">
              <div>
                <h3 style={{ margin: 0 }}>
                  {preview.label}
                  {preview.hint ? ` ${preview.hint}` : ''}
                </h3>
              </div>
              <button className="btn-ghost" type="button" onClick={() => setPreview(null)}>
                Close
              </button>
            </div>
            <div className="modal-media-wrap aspect-preview-media">
              <img
                src={preview.src}
                alt={`${preview.label} example`}
                style={{ aspectRatio: preview.cssRatio }}
              />
            </div>
            <p className="aspect-preview-dismiss-hint">
              Tap outside or press Esc to close
            </p>
          </div>
        </div>
      )}
    </>
  )
}
