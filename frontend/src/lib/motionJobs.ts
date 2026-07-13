export type MotionJobStatus = 'queued' | 'running' | 'done' | 'error'

export type MotionJob = {
  id: string
  sourcePath: string
  product: string
  ratio: string
  status: MotionJobStatus
  error?: string
}

export type MotionGenerateRequest = {
  targets: { path: string; product: string; ratio: string }[]
  durationSeconds: number
  prompt: string
  promptExtra: string
}
