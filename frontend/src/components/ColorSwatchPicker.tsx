const PRESETS = [
  { id: 'white', label: 'White', value: '#FFFFFF' },
  { id: 'black', label: 'Black', value: '#000000' },
  { id: 'original', label: 'Original', value: 'original' },
] as const

export function ColorSwatchPicker({
  label,
  value,
  brandColors,
  onChange,
  allowOriginal = false,
}: {
  label: string
  value: string | null | undefined
  brandColors: string[]
  onChange: (v: string) => void
  allowOriginal?: boolean
}) {
  const swatches = [
    ...(allowOriginal ? PRESETS : PRESETS.filter((p) => p.id !== 'original')),
    ...brandColors
      .filter((c) => c && c.startsWith('#'))
      .map((c) => ({ id: c, label: c, value: c })),
  ]
  const current = value || '#FFFFFF'

  return (
    <div style={{ marginBottom: '0.85rem' }}>
      <div style={{ color: 'var(--muted)', marginBottom: '0.35rem', fontSize: '0.9rem' }}>
        {label}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', alignItems: 'center' }}>
        {swatches.map((s) => {
          const selected = (current || '').toLowerCase() === s.value.toLowerCase()
          return (
            <button
              key={s.id}
              type="button"
              className="btn-ghost"
              title={s.label}
              onClick={() => onChange(s.value)}
              style={{
                width: 36,
                height: 36,
                padding: 0,
                borderColor: selected ? 'var(--accent)' : 'var(--border)',
                background:
                  s.value === 'original'
                    ? 'repeating-conic-gradient(#888 0% 25%, #444 0% 50%) 50% / 10px 10px'
                    : s.value,
              }}
            />
          )
        })}
        <input
          type="color"
          value={current.startsWith('#') ? current : '#FFFFFF'}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          style={{ width: 36, height: 36, border: 'none', background: 'transparent' }}
        />
        <span style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>{current}</span>
      </div>
    </div>
  )
}
