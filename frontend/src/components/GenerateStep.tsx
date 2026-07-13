import type { CreativeResult } from '../lib/api'
import { outputUrl } from '../lib/api'
import type { CreativePlan } from '../lib/creativeCounts'
import { PipelineCountBanner } from './PipelineCountBanner'

export function GenerateStep({
  done,
  total,
  pipelineTotal,
  finalizeCount = 0,
  plan = null,
  elapsedSec,
  tiles,
  currentStage,
  sourcePreviewPaths = [],
}: {
  done: number
  total: number
  pipelineTotal?: number
  finalizeCount?: number
  plan?: CreativePlan | null
  elapsedSec: number
  tiles: CreativeResult[]
  currentStage?: string | null
  sourcePreviewPaths?: string[]
}) {
  const count = total || 6
  const activeIndex = Math.min(done, Math.max(0, count - 1))
  const fallbackPlan: CreativePlan | null =
    plan ||
    (count > 0
      ? {
          productCount: 0,
          ratioCount: 0,
          framingExtra: 0,
          perProductStills: 0,
          generateCount: count,
          localeCount: finalizeCount > 0 && count > 0 ? Math.round(finalizeCount / count) : 0,
          finalizeCount,
          pipelineTotal: pipelineTotal ?? count + finalizeCount,
        }
      : null)

  return (
    <section className="panel step-panel generate-step" style={{ padding: '1.5rem' }}>
      <h2 style={{ marginTop: 0 }}>Generate</h2>
      <PipelineCountBanner
        plan={fallbackPlan}
        readyStills={done}
        emphasis={`Working now: ${done}/${count} stills · ${elapsedSec}s${
          currentStage ? ` · ${currentStage}` : ''
        }`}
      />
      <p className="generate-leave-note">
        You can leave this page. Generation keeps running. We will notify you when it is done.
      </p>
      <p className="generate-progress-line">
        {done}/{count} stills · {elapsedSec}s
        {currentStage ? ` · working on ${currentStage}` : ''}
      </p>

      {sourcePreviewPaths.length > 0 && (
        <div className="generate-source-row">
          <span className="generate-source-label">Source look</span>
          <div className="generate-source-thumbs">
            {sourcePreviewPaths.slice(0, 4).map((path) => (
              <img key={path} src={outputUrl(path)} alt="" />
            ))}
          </div>
        </div>
      )}

      <div className="tile-grid">
        {Array.from({ length: count }).map((_, i) => {
          const tile = tiles[i]
          const aspect = tile?.ratio
            ? tile.ratio.split('-')[0].replace(':', '/')
            : '1/1'
          const isActive = !tile && i === activeIndex
          const isQueued = !tile && i > activeIndex
          return (
            <div
              key={i}
              className={[
                'panel',
                'generate-tile',
                tile ? 'is-done' : '',
                isActive ? 'is-active' : '',
                isQueued ? 'is-queued' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              style={{
                padding: 0,
                overflow: 'hidden',
                background: tile ? '#1a1a1a' : undefined,
              }}
            >
              <div
                className="generate-tile-media"
                style={{
                  aspectRatio: aspect,
                  background: tile
                    ? '#111'
                    : 'linear-gradient(90deg,#2a2a2a,#333,#2a2a2a)',
                  backgroundSize: tile ? undefined : '200% 100%',
                  animation: tile ? undefined : 'shimmer 1.2s infinite',
                  display: 'grid',
                  placeItems: 'center',
                }}
              >
                {tile?.path ? (
                  <img
                    src={outputUrl(tile.path)}
                    alt=""
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                ) : (
                  <span className="generate-tile-status">
                    {isActive
                      ? currentStage
                        ? `Working on ${currentStage}…`
                        : 'Working…'
                      : 'Queued'}
                  </span>
                )}
              </div>
              {tile && (
                <div style={{ padding: '0.55rem 0.65rem' }}>
                  <div style={{ fontSize: '0.85rem' }}>
                    {tile.product} · {tile.ratio}
                  </div>
                  <div style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>
                    {tile.source}
                    {/* Christian: deprecated UI path. Generate is stills-only; badge never shows here. */}
                    {tile.motion_path ? ' · motion' : ''}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
      <style>{`@keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`}</style>
    </section>
  )
}
