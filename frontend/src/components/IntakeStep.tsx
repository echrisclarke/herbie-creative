import { useEffect, useState } from 'react'
import { listSamples, runAssignmentCli, type SampleInfo } from '../lib/api'
import { AspectRatioExamples } from './AspectRatioExamples'
import {
  EMPTY_ROLE_FILES,
  RoleUploadSections,
  flattenRoleFiles,
  type RoleFiles,
} from './RoleUploadSections'

type BriefInputMode = 'paste' | 'upload'

export function IntakeStep({
  onNext,
  onLoadSample,
}: {
  onNext: (briefText: string, files: File[], roles: string[]) => Promise<void>
  onLoadSample: (sampleId: string) => Promise<void>
}) {
  const [text, setText] = useState('')
  const [extraNotes, setExtraNotes] = useState('')
  const [briefMode, setBriefMode] = useState<BriefInputMode>('paste')
  const [briefFiles, setBriefFiles] = useState<File[]>([])
  const [roleFiles, setRoleFiles] = useState<RoleFiles>({ ...EMPTY_ROLE_FILES })
  const [busy, setBusy] = useState(false)
  const [loadingSampleId, setLoadingSampleId] = useState<string | null>(null)
  const [assignmentBusy, setAssignmentBusy] = useState(false)
  const [assignmentMsg, setAssignmentMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [samples, setSamples] = useState<SampleInfo[]>([])

  useEffect(() => {
    listSamples()
      .then((r) => setSamples(r.samples.filter((s) => s.available)))
      .catch(() => setSamples([]))
  }, [])

  const { files: assetFiles, roleTags: assetRoles } = flattenRoleFiles(roleFiles)
  const files =
    briefMode === 'upload' && briefFiles.length > 0
      ? [...briefFiles, ...assetFiles]
      : assetFiles
  const roleTags =
    briefMode === 'upload' && briefFiles.length > 0
      ? [...briefFiles.map(() => 'brief'), ...assetRoles]
      : assetRoles

  const hasPaste = Boolean(text.trim())
  const hasBriefUpload = briefFiles.length > 0
  const canContinue =
    (briefMode === 'paste' && hasPaste) || (briefMode === 'upload' && hasBriefUpload)

  const anyBusy = busy || Boolean(loadingSampleId) || assignmentBusy

  return (
    <section className="panel step-panel" style={{ padding: '1.5rem' }}>
      <h2 style={{ marginTop: 0 }}>Intake</h2>

      <div className="cli-sample-banner">
        <div className="cli-sample-banner-copy">
          <strong>Local CLI</strong>
          <p>
            Same brief as <em>Jordan hero zoom</em> below · Frozen Moments +
            Shattered Backboard · 1:1 / 9:16 / 16:9 · en / es / zh · legal
          </p>
          <p className="cli-sample-disclaimer">
            Unofficial test sample. Not a real Jordan / Nike advertisement.
          </p>
        </div>
        <button
          type="button"
          className="btn cli-sample-btn"
          disabled={anyBusy}
          onClick={async () => {
            setAssignmentBusy(true)
            setError(null)
            setAssignmentMsg(null)
            try {
              const result = await runAssignmentCli()
              setAssignmentMsg(result.message || 'Opened a terminal for the local CLI run.')
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err))
            } finally {
              setAssignmentBusy(false)
            }
          }}
        >
          {assignmentBusy ? 'Opening…' : 'Run local CLI'}
        </button>
      </div>
      {assignmentMsg && <div className="banner">{assignmentMsg}</div>}

      {samples.length > 0 && (
        <details className="intake-collapse sample-briefs-panel">
          <summary>Sample briefs</summary>
          <div className="sample-card-grid">
            {samples.map((s) => (
              <div
                key={s.id}
                className={
                  s.id === 'jordan-hero-zoom'
                    ? 'sample-card sample-card-featured'
                    : 'sample-card'
                }
              >
                <strong>{s.title}</strong>
                {s.description ? <p className="sample-card-desc">{s.description}</p> : null}
                <button
                  type="button"
                  className="btn"
                  disabled={anyBusy}
                  onClick={async () => {
                    setLoadingSampleId(s.id)
                    setError(null)
                    try {
                      await onLoadSample(s.id)
                    } catch (err) {
                      setError(err instanceof Error ? err.message : String(err))
                    } finally {
                      setLoadingSampleId(null)
                    }
                  }}
                >
                  {loadingSampleId === s.id ? 'Loading…' : 'Run this sample'}
                </button>
              </div>
            ))}
          </div>
        </details>
      )}

      <details className="intake-collapse your-brief-panel" open>
        <summary>Your brief</summary>
        <div className="your-brief-layout">
          <div className="your-brief-col your-brief-examples">
            <h3 className="your-brief-col-heading">Aspect ratio examples</h3>
            <p className="your-brief-col-hint">
              Stills use these formats now. Optional motion is chosen later on Results for
              the specific creatives you want to animate.
            </p>
            <AspectRatioExamples compact showCloseup />
          </div>

          <div className="your-brief-col your-brief-input">
            <h3 className="your-brief-col-heading">Campaign brief</h3>
            <p className="your-brief-col-hint">
              Choose one: paste the brief, or upload a file.
            </p>
            <div className="brief-mode-tabs" role="tablist" aria-label="Brief input">
              <button
                type="button"
                role="tab"
                aria-selected={briefMode === 'paste'}
                className={briefMode === 'paste' ? 'brief-mode-tab is-on' : 'brief-mode-tab'}
                onClick={() => setBriefMode('paste')}
                disabled={anyBusy}
              >
                Paste brief
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={briefMode === 'upload'}
                className={briefMode === 'upload' ? 'brief-mode-tab is-on' : 'brief-mode-tab'}
                onClick={() => setBriefMode('upload')}
                disabled={anyBusy}
              >
                Upload brief
              </button>
            </div>

            {briefMode === 'paste' ? (
              <textarea
                className="field your-brief-textarea"
                rows={12}
                placeholder="Paste a campaign brief…"
                value={text}
                onChange={(e) => setText(e.target.value)}
                disabled={anyBusy}
              />
            ) : (
              <div className="brief-upload-block">
                <div className="brief-template-row">
                  <span className="your-brief-col-hint">Templates:</span>
                  <a
                    className="brief-template-link"
                    href="/templates/campaign-brief.template.json"
                    download="campaign-brief.template.json"
                  >
                    JSON
                  </a>
                  <a
                    className="brief-template-link"
                    href="/templates/campaign-brief.template.yaml"
                    download="campaign-brief.template.yaml"
                  >
                    YAML
                  </a>
                  <a
                    className="brief-template-link"
                    href="/templates/campaign-brief.template.txt"
                    download="campaign-brief.template.txt"
                  >
                    Text
                  </a>
                </div>
                <label className={anyBusy ? 'file-pick is-disabled' : 'file-pick'}>
                  <input
                    className="file-pick-input"
                    type="file"
                    accept=".txt,.md,.json,.yaml,.yml,.pdf,application/pdf,text/plain"
                    disabled={anyBusy}
                    onChange={(e) => {
                      const picked = Array.from(e.target.files || [])
                      if (!picked.length) return
                      setBriefFiles(picked.slice(0, 1))
                      e.target.value = ''
                    }}
                  />
                  <span className="file-pick-btn">Choose file</span>
                </label>
                {briefFiles.length > 0 && (
                  <ul className="brief-file-list">
                    {briefFiles.map((f, i) => (
                      <li key={`${f.name}-${i}`}>
                        <span>{f.name}</span>
                        <button
                          type="button"
                          className="btn-ghost"
                          style={{ padding: '0 0.35rem', border: 'none' }}
                          disabled={anyBusy}
                          onClick={() => setBriefFiles([])}
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <label className="your-brief-col-heading" htmlFor="brief-extra-notes">
                  Additional instructions
                </label>
                <p className="your-brief-col-hint">
                  Optional notes to add on top of the uploaded brief (tone, must-haves, exclusions).
                </p>
                <textarea
                  id="brief-extra-notes"
                  className="field your-brief-textarea your-brief-extra"
                  rows={6}
                  placeholder="Optional: extra direction for this campaign…"
                  value={extraNotes}
                  onChange={(e) => setExtraNotes(e.target.value)}
                  disabled={anyBusy}
                />
              </div>
            )}
          </div>
        </div>

        <h3 style={{ marginTop: '1.5rem', marginBottom: '0.65rem' }}>Asset uploads</h3>
        <p className="your-brief-col-hint" style={{ marginTop: 0 }}>
          Logos (pick one later), product photos, style, likeness, and background. Dump all product
          shots here. Products (creative sets) come from the brief; on Review you can move photos
          onto the right product.
        </p>
        <RoleUploadSections value={roleFiles} onChange={setRoleFiles} disabled={anyBusy} />
      </details>

      {error && <div className="banner banner-danger">{error}</div>}
      <div className="action-row" style={{ marginTop: '1.25rem' }}>
        <button
          className="btn"
          disabled={anyBusy || !canContinue}
          onClick={async () => {
            setBusy(true)
            setError(null)
            try {
              const briefText =
                briefMode === 'paste' ? text : extraNotes.trim() ? extraNotes.trim() : ''
              await onNext(briefText, files, roleTags)
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err))
            } finally {
              setBusy(false)
            }
          }}
        >
          {busy ? 'Analyzing brief...' : 'Next'}
        </button>
      </div>
    </section>
  )
}
