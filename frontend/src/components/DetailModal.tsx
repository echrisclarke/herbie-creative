import { useEffect, useRef, useState, type MouseEvent } from 'react'
import type { CreativeResult } from '../lib/api'
import { outputUrl } from '../lib/api'

function PlayableVideo({ src }: { src: string }) {
  const ref = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)

  function startPlay(e?: MouseEvent) {
    e?.stopPropagation()
    const el = ref.current
    if (!el) return
    void el.play()
    setPlaying(true)
  }

  return (
    <div className="playable-video">
      <video
        ref={ref}
        src={src}
        playsInline
        preload="metadata"
        controls={playing}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onLoadedMetadata={() => {
          const el = ref.current
          if (!el) return
          try {
            if (el.duration && Number.isFinite(el.duration)) {
              el.currentTime = Math.min(0.15, el.duration * 0.05)
            }
          } catch {
            /* ignore */
          }
        }}
      />
      {!playing && (
        <button type="button" className="play-button" onClick={startPlay} aria-label="Play">
          ▶
        </button>
      )}
    </div>
  )
}

export function DetailModal({
  creative,
  kind = 'still',
  onClose,
  onAnimate,
}: {
  creative: CreativeResult
  kind?: 'still' | 'motion'
  onClose: () => void
  onAnimate?: () => void
}) {
  const [local, setLocal] = useState(creative)
  const [viewKind, setViewKind] = useState(kind)

  useEffect(() => {
    setLocal(creative)
    setViewKind(kind)
  }, [creative, kind])

  const isMotion =
    viewKind === 'motion' ||
    Boolean(local.motion_path && String(local.path).toLowerCase().endsWith('.mp4')) ||
    String(local.path).toLowerCase().endsWith('.mp4')

  const mediaPath = isMotion ? local.motion_path || local.path : local.path

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="panel modal-dialog"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`${local.product} ${local.ratio}`}
      >
        <div className="modal-dialog-head">
          <h3 style={{ margin: 0, wordBreak: 'break-word' }}>
            {local.product} · {local.ratio}
            {isMotion ? ' · motion' : ''}
          </h3>
          <button className="btn-ghost" type="button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="modal-media-wrap">
          {isMotion ? (
            <PlayableVideo src={outputUrl(mediaPath)} />
          ) : (
            <img src={outputUrl(mediaPath)} alt="" />
          )}
        </div>

        <div className="action-row modal-dialog-actions">
          <a className="btn" href={outputUrl(mediaPath)} download>
            {isMotion ? 'Download motion' : 'Download still'}
          </a>
          {!isMotion && onAnimate && (
            <button
              type="button"
              className="btn-ghost"
              onClick={() => {
                onClose()
                onAnimate()
              }}
            >
              Animate in Motion step
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
