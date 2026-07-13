import { useEffect, useState } from 'react'
import type { BrandNotes } from '../lib/api'
import { searchFonts } from '../lib/api'

export function BrandNotesEditor({
  value,
  onChange,
}: {
  value: BrandNotes
  onChange: (v: BrandNotes) => void
}) {
  const [query, setQuery] = useState(value.font_names[0] || '')
  const [fonts, setFonts] = useState<string[]>([])

  useEffect(() => {
    const t = setTimeout(() => {
      searchFonts(query).then((r) => setFonts(r.fonts || []))
    }, 250)
    return () => clearTimeout(t)
  }, [query])

  return (
    <div className="panel" style={{ padding: '1rem', marginTop: '1rem' }}>
      <h3 style={{ marginTop: 0 }}>Brand notes</h3>
      <label>Tone</label>
      <input
        className="field"
        value={value.tone}
        onChange={(e) => onChange({ ...value, tone: e.target.value })}
      />
      <label style={{ display: 'block', marginTop: '0.75rem' }}>Colors (comma-separated hex)</label>
      <input
        className="field"
        value={value.colors.join(', ')}
        onChange={(e) =>
          onChange({
            ...value,
            colors: e.target.value
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean),
          })
        }
      />
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: '0.75rem',
          alignItems: 'baseline',
          marginTop: '0.75rem',
          flexWrap: 'wrap',
        }}
      >
        <label style={{ margin: 0 }}>Google Font</label>
        <a
          href="https://fonts.google.com"
          target="_blank"
          rel="noreferrer"
          style={{ color: 'var(--accent)', fontSize: '0.85rem' }}
        >
          Browse fonts.google.com
        </a>
      </div>
      <input
        className="field"
        value={query}
        onChange={(e) => {
          const next = e.target.value
          setQuery(next)
          onChange({ ...value, font_names: next.trim() ? [next.trim()] : [] })
        }}
        placeholder="Search Google Fonts or type a family name"
        style={{ marginTop: '0.35rem' }}
      />
      {fonts.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.5rem' }}>
          {fonts.slice(0, 12).map((f) => (
            <button
              key={f}
              type="button"
              className="btn-ghost"
              style={{ padding: '0.35rem 0.6rem', fontSize: '0.85rem' }}
              onClick={() => {
                setQuery(f)
                onChange({ ...value, font_names: [f] })
              }}
            >
              {f}
            </button>
          ))}
        </div>
      )}
      {value.font_alternates?.length > 0 && (
        <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>
          Alternates: {value.font_alternates.join(', ')}
        </p>
      )}
      <label style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', alignItems: 'center' }}>
        <input
          type="checkbox"
          checked={value.logo_required}
          onChange={(e) => onChange({ ...value, logo_required: e.target.checked })}
        />
        Logo required
      </label>
      <label style={{ display: 'block', marginTop: '0.75rem' }}>Forbidden words (comma-separated)</label>
      <input
        className="field"
        value={value.forbidden_words.join(', ')}
        onChange={(e) =>
          onChange({
            ...value,
            forbidden_words: e.target.value
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean),
          })
        }
      />
    </div>
  )
}
