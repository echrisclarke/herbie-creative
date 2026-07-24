import { outputThumbUrl } from '../lib/api'

export type UploadRole =
  | 'logo'
  | 'product'
  | 'style'
  | 'likeness'
  | 'background'

export type RoleFiles = Record<UploadRole, File[]>

export const EMPTY_ROLE_FILES: RoleFiles = {
  logo: [],
  product: [],
  style: [],
  likeness: [],
  background: [],
}

export const UPLOAD_SECTIONS: Array<{
  role: UploadRole
  title: string
  hint: string
  accept: string
  multiple: boolean
}> = [
  {
    role: 'logo',
    title: 'Logos',
    hint: 'Upload one or more brand marks, then pick which logo this campaign uses on Review / Finalize.',
    accept: '.png,.jpg,.jpeg,.webp,.svg',
    multiple: true,
  },
  {
    role: 'product',
    title: 'Product references',
    hint: 'Upload as many product photos as you want. They are references for fidelity, not separate ads. Creative sets come from products named in the brief (or Add product on Review). On Review, assign which photos belong to which product if auto-assignment is wrong. The model does not invent new products from photos alone.',
    accept: '.png,.jpg,.jpeg,.webp',
    multiple: true,
  },
  {
    role: 'style',
    title: 'Style references',
    hint: 'Look, mood, lighting, art direction (optional)',
    accept: '.png,.jpg,.jpeg,.webp',
    multiple: true,
  },
  {
    role: 'likeness',
    title: 'Character / actor likeness',
    hint: 'Face or body identity refs (optional)',
    accept: '.png,.jpg,.jpeg,.webp',
    multiple: true,
  },
  {
    role: 'background',
    title: 'Background',
    hint: 'Environment / plate refs (optional)',
    accept: '.png,.jpg,.jpeg,.webp',
    multiple: true,
  },
]

export function flattenRoleFiles(roles: RoleFiles): { files: File[]; roleTags: string[] } {
  const files: File[] = []
  const roleTags: string[] = []
  for (const section of UPLOAD_SECTIONS) {
    for (const f of roles[section.role] || []) {
      files.push(f)
      roleTags.push(section.role)
    }
  }
  return { files, roleTags }
}

export function RoleUploadSections({
  value,
  onChange,
  disabled,
  existingByRole,
}: {
  value: RoleFiles
  onChange: (next: RoleFiles) => void
  disabled?: boolean
  /** Paths already on the campaign (from Intake or earlier uploads). */
  existingByRole?: Partial<Record<UploadRole, string[]>>
}) {
  return (
    <div style={{ display: 'grid', gap: '0.85rem' }}>
      {UPLOAD_SECTIONS.map((section) => {
        const existing = (existingByRole?.[section.role] || []).filter(Boolean)
        return (
          <div
            key={section.role}
            className="panel"
            style={{ padding: '0.85rem 1rem', background: 'var(--panel)' }}
          >
            <div style={{ fontWeight: 600, marginBottom: '0.2rem' }}>{section.title}</div>
            <div style={{ color: 'var(--muted)', fontSize: '0.82rem', marginBottom: '0.45rem' }}>
              {section.hint}
            </div>
            {existing.length > 0 && (
              <div className="kept-uploads" style={{ marginBottom: '0.65rem' }}>
                <div className="kept-uploads-label">
                  On this campaign ({existing.length})
                </div>
                <div className="kept-uploads-grid">
                  {existing.map((path) => {
                    const name = path.replace(/\\/g, '/').split('/').pop() || path
                    return (
                      <div key={path} className="kept-uploads-thumb" title={name}>
                        <img
                          src={outputThumbUrl(path, 240)}
                          alt={name}
                          loading="lazy"
                          decoding="async"
                        />
                        <span>{name}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
            <label className={disabled ? 'file-pick is-disabled' : 'file-pick'}>
              <input
                className="file-pick-input"
                type="file"
                multiple={section.multiple}
                accept={section.accept}
                disabled={disabled}
                onChange={(e) => {
                  const picked = Array.from(e.target.files || [])
                  if (!picked.length) return
                  onChange({
                    ...value,
                    [section.role]: section.multiple
                      ? [...(value[section.role] || []), ...picked]
                      : picked.slice(0, 1),
                  })
                  e.target.value = ''
                }}
              />
              <span className="file-pick-btn">
                {existing.length > 0
                  ? section.multiple
                    ? 'Add more files'
                    : 'Replace file'
                  : section.multiple
                    ? 'Choose files'
                    : 'Choose file'}
              </span>
            </label>
            {(value[section.role] || []).length > 0 && (
              <ul style={{ color: 'var(--muted)', fontSize: '0.85rem', margin: '0.45rem 0 0' }}>
                {(value[section.role] || []).map((f, i) => (
                  <li
                    key={`${f.name}-${i}`}
                    style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}
                  >
                    <span>{f.name}</span>
                    <button
                      type="button"
                      className="btn-ghost"
                      style={{ padding: '0 0.35rem', border: 'none' }}
                      disabled={disabled}
                      onClick={() =>
                        onChange({
                          ...value,
                          [section.role]: (value[section.role] || []).filter((_, j) => j !== i),
                        })
                      }
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
    </div>
  )
}
