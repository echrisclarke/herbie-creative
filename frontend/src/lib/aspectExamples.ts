export type AspectExample = {
  ratio: string
  label: string
  hint: string
  cssRatio: string
  src: string
}

/** Curated Frozen Moments stills showing close-up + ratio crops from one zoomed master. */
export const ASPECT_RATIO_EXAMPLES: AspectExample[] = [
  {
    ratio: '1:1',
    label: '1:1',
    hint: 'Square feed',
    cssRatio: '1 / 1',
    src: '/examples/jordan-ratio-crops/1x1.png',
  },
  {
    ratio: '9:16',
    label: '9:16',
    hint: 'Stories / Reels',
    cssRatio: '9 / 16',
    src: '/examples/jordan-ratio-crops/9x16.png',
  },
  {
    ratio: '16:9',
    label: '16:9',
    hint: 'Landscape / YouTube',
    cssRatio: '16 / 9',
    src: '/examples/jordan-ratio-crops/16x9.png',
  },
]

export const CLOSEUP_EXAMPLE: AspectExample = {
  ratio: '1:1-closeup',
  label: '1:1 hero close-up',
  hint: '',
  cssRatio: '1 / 1',
  src: '/examples/jordan-ratio-crops/1x1-closeup.png',
}

export function cssAspectRatio(ratio: string): string {
  const base = ratio.split('-')[0] || ratio
  if (/^\d+:\d+$/.test(base)) return base.replace(':', ' / ')
  return '1 / 1'
}
