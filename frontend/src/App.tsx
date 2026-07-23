import { useEffect, useMemo, useRef, useState } from 'react'
import './styles/tokens.css'
import { WizardStepper } from './components/WizardStepper'
import { IntakeStep } from './components/IntakeStep'
import { ReviewStep } from './components/ReviewStep'
import { GenerateStep } from './components/GenerateStep'
import { FinalizeStep } from './components/FinalizeStep'
import { MotionStep } from './components/MotionStep'
import { ResultsStep } from './components/ResultsStep'
import { SettingsPanel } from './components/SettingsPanel'
import { SamplesGallery } from './components/SamplesGallery'
import {
  hasSeenLanding,
  LandingHero,
  markLandingSeen,
} from './components/LandingHero'
import { InstallSetup } from './components/InstallSetup'
import { AboutPage } from './components/AboutPage'
import { LoginScreen } from './components/LoginScreen'
import { PublicExamplesGallery } from './components/PublicExamplesGallery'
import { WelcomeGate } from './components/WelcomeGate'
import {
  approveCampaign,
  cleanupEphemeral,
  createCampaign,
  createFromSample,
  fetchAuthMe,
  fetchReport,
  generateCampaign,
  generateMotion,
  getHealth,
  logout,
  openPastCampaign,
  parseCampaign,
  saveCampaign,
  subscribeEvents,
  uploadAssets,
  type AssetManifest,
  type AuthUser,
  type Brief,
  type CreativeResult,
  type ImageQuality,
  type ProductSeedsStatus,
  type Report,
  type TrialStatus,
} from './lib/api'
import { countNoTextCreatives, planCreativeCounts } from './lib/creativeCounts'
import type { MotionGenerateRequest, MotionJob } from './lib/motionJobs'

type AppTab = 'pipeline' | 'library' | 'settings'
type ToastAction = 'finalize' | 'results' | 'generate' | null

function formatElapsed(sec: number) {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `${s}s`
}

function stillKey(c: CreativeResult): string {
  return (c.creative_path || c.path || '').replace(/\\/g, '/').toLowerCase()
}

/** Keep prior motion_path values when a report refresh drops or rewrites them. */
function mergeMotionPaths(
  previous: CreativeResult[],
  refreshed: CreativeResult[],
): CreativeResult[] {
  const prior = new Map<string, string>()
  for (const c of previous) {
    if (!c.motion_path) continue
    const key = stillKey(c)
    if (key) prior.set(key, c.motion_path)
  }
  return refreshed.map((c) => {
    if (c.motion_path) return c
    const kept = prior.get(stillKey(c))
    return kept ? { ...c, motion_path: kept } : c
  })
}

export default function App() {
  // First visit: landing once per browser, then InstallSetup until OpenAI key or skip.
  const [showLanding, setShowLanding] = useState(() => !hasSeenLanding())
  const [preAuthView, setPreAuthView] = useState<
    'welcome' | 'signup' | 'signin' | 'about' | 'examples' | null
  >(null)
  const [showInstall, setShowInstall] = useState(false)
  const [installSkipped, setInstallSkipped] = useState(false)
  const [healthReady, setHealthReady] = useState(false)
  const [hosted, setHosted] = useState(false)
  const [desktopTools, setDesktopTools] = useState(true)
  const [authReady, setAuthReady] = useState(false)
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [trial, setTrial] = useState<TrialStatus | null>(null)
  const [tab, setTab] = useState<AppTab>('pipeline')
  const [step, setStep] = useState(0)
  /** Highest step unlocked this run. Going back must not lock Finalize/Motion/Results. */
  const [furthestStep, setFurthestStep] = useState(0)
  const [campaignId, setCampaignId] = useState<string | null>(null)
  const [brief, setBrief] = useState<Brief | null>(null)
  const [manifest, setManifest] = useState<AssetManifest | null>(null)
  const [missingFields, setMissingFields] = useState<string[]>([])
  const [productSeeds, setProductSeeds] = useState<ProductSeedsStatus | null>(null)
  const [motionAvailable, setMotionAvailable] = useState(false)
  const [motionEntry, setMotionEntry] = useState<'ask' | 'settings'>('ask')
  const [motionJobs, setMotionJobs] = useState<MotionJob[]>([])
  const motionChainRef = useRef(Promise.resolve())
  const [openaiConfigured, setOpenaiConfigured] = useState(true)
  const [imageQuality, setImageQuality] = useState<ImageQuality>('medium')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tiles, setTiles] = useState<CreativeResult[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [now, setNow] = useState(Date.now())
  const [currentStage, setCurrentStage] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [toastAction, setToastAction] = useState<ToastAction>(null)
  const [applyHighlight, setApplyHighlight] = useState(false)
  const [generateSourcePaths, setGenerateSourcePaths] = useState<string[]>([])
  const [generateRunTotal, setGenerateRunTotal] = useState<number | null>(null)
  const esRef = useRef<EventSource | null>(null)
  const returnToResultsRef = useRef(false)

  function refreshHealth() {
    getHealth()
      .then((h) => {
        setMotionAvailable(Boolean(h.motion_available))
        setOpenaiConfigured(h.openai_configured !== false)
        setHosted(Boolean(h.hosted))
        setDesktopTools(h.desktop_tools !== false)
        setTrial(h.trial || null)
        setHealthReady(true)
      })
      .catch(() => {
        setMotionAvailable(false)
        setOpenaiConfigured(false)
        setHealthReady(true)
      })
  }

  function refreshAuth() {
    fetchAuthMe()
      .then((me) => {
        setHosted(Boolean(me.hosted))
        setAuthUser(me.user)
        setAuthReady(true)
      })
      .catch(() => {
        setAuthUser(null)
        setAuthReady(true)
      })
  }

  useEffect(() => {
    refreshHealth()
    refreshAuth()
  }, [])

  const accountTrialActive =
    hosted &&
    Boolean(authUser) &&
    Boolean(trial?.can_use_host_openai || ((trial?.remaining ?? 0) > 0 && !trial?.has_own_openai))

  useEffect(() => {
    // After landing: block the wizard until a key is saved, account trial covers it, or skip.
    if (!healthReady || showLanding || installSkipped || openaiConfigured) return
    if (hosted && !authUser) return
    if (accountTrialActive) return
    setShowInstall(true)
  }, [
    healthReady,
    showLanding,
    installSkipped,
    openaiConfigured,
    hosted,
    authUser,
    accountTrialActive,
  ])

  function finishInstallGate() {
    setInstallSkipped(true)
    setShowInstall(false)
  }

  function enterFromLanding() {
    markLandingSeen()
    setShowLanding(false)
    if (hosted && !authUser) {
      setPreAuthView('welcome')
      return
    }
    if (healthReady && !openaiConfigured && !installSkipped) {
      setShowInstall(true)
    }
  }

  useEffect(() => {
    if (!startedAt || !busy) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [startedAt, busy])

  useEffect(() => {
    if (!toast) return
    const id = window.setTimeout(() => {
      setToast(null)
      setToastAction(null)
    }, 8000)
    return () => window.clearTimeout(id)
  }, [toast])

  useEffect(() => {
    return () => {
      esRef.current?.close()
    }
  }, [])

  function requireOpenAI(reason: string): boolean {
    if (openaiConfigured) return true
    setError(reason)
    setShowInstall(true)
    setInstallSkipped(false)
    return false
  }

  function goToStep(n: number) {
    setStep(n)
    setFurthestStep((f) => Math.max(f, n))
  }

  function isStepEnabled(i: number) {
    if (i <= 0) return true
    if (i === 1 || i === 2) return Boolean(brief && campaignId)
    if (i === 3) return Boolean(brief && campaignId && (tiles.length > 0 || report))
    if (i === 4) return Boolean(brief && campaignId && report)
    if (i === 5) return Boolean(campaignId && (report || tiles.length > 0))
    return false
  }

  function handleStepNav(n: number) {
    if (!isStepEnabled(n) || n > furthestStep) return
    if (n === 4 && report) setMotionEntry('settings')
    goToStep(n)
  }

  function openToastTarget() {
    setTab('pipeline')
    if (toastAction === 'results') goToStep(5)
    else if (toastAction === 'generate') goToStep(2)
    else goToStep(3)
    setToast(null)
    setToastAction(null)
  }

  const elapsedSec = useMemo(() => {
    if (!startedAt) return 0
    return Math.max(0, Math.round((now - startedAt) / 1000))
  }, [now, startedAt])

  const creativePlan = useMemo(
    () => (brief ? planCreativeCounts(brief) : null),
    [brief],
  )
  const creativeTotal =
    generateRunTotal ?? creativePlan?.generateCount ?? 8

  async function discardEphemeral(prevId: string | null) {
    if (!prevId) return
    try {
      await cleanupEphemeral(prevId)
    } catch {
      /* ignore */
    }
  }

  async function handleIntake(briefText: string, files: File[], roles: string[] = []) {
    await discardEphemeral(campaignId)
    const { campaign_id } = await createCampaign(briefText, files, roles)
    setCampaignId(campaign_id)
    const parsed = await parseCampaign(campaign_id)
    setBrief(parsed.brief)
    setManifest(parsed.asset_manifest)
    setMissingFields(parsed.missing_fields || [])
    setProductSeeds(parsed.product_seeds || null)
    setFurthestStep(1)
    setStep(1)
    setTab('pipeline')
  }

  async function handleLoadSample(sampleId: string) {
    await discardEphemeral(campaignId)
    const result = await createFromSample(sampleId)
    setCampaignId(result.campaign_id)
    setBrief(result.brief)
    setManifest(result.asset_manifest)
    setMissingFields(result.missing_fields || [])
    setProductSeeds(null)
    // Match Local CLI demo defaults for the featured Jordan hero zoom sample.
    setImageQuality(sampleId === 'jordan-hero-zoom' ? 'low' : 'medium')
    setFurthestStep(1)
    setStep(1)
    setTab('pipeline')
  }

  async function handleUploadAssets(files: File[], roles: string[] = []) {
    if (!campaignId || !brief) return
    setError(null)
    await saveCampaign(campaignId, brief)
    const result = await uploadAssets(campaignId, files, roles)
    if (result.brief) setBrief(result.brief)
    if (result.asset_manifest) setManifest(result.asset_manifest)
    setMissingFields(result.missing_fields || [])
  }

  async function handleApprove() {
    if (!campaignId || !brief) return
    if (
      !requireOpenAI(
        'Add an OpenAI key before generating creatives.',
      )
    ) {
      return
    }
    setBusy(true)
    setError(null)
    setCurrentStage(null)
    setApplyHighlight(false)
    setGenerateSourcePaths([])
    setGenerateRunTotal(countNoTextCreatives(brief))
    returnToResultsRef.current = false
    try {
      await approveCampaign(campaignId, brief)
      setTiles([])
      setReport(null)
      setStartedAt(Date.now())
      goToStep(2)
      setTab('pipeline')
      esRef.current?.close()
      const es = subscribeEvents(campaignId, (event, data) => {
        if (event === 'tile.started') {
          const product = String(data.product || '')
          const ratio = String(data.ratio || '')
          setCurrentStage([ratio, product].filter(Boolean).join(' '))
        }
        if (event === 'tile.completed') {
          setTiles((prev) => {
            const next = [
              ...prev,
              {
                product: String(data.product || ''),
                ratio: String(data.ratio || ''),
                path: String(data.path || ''),
                locale: data.locale ? String(data.locale) : 'creative',
                source: String(data.source || ''),
                image_provider: String(data.image_provider || 'openai'),
                fallback_triggered: Boolean(data.fallback_triggered),
                motion_path: data.motion_path ? String(data.motion_path) : null,
                compliance: (data.compliance as Record<string, boolean>) || {},
              },
            ]
            return next
          })
          setStep((s) => {
            if (s !== 2) return s
            if (returnToResultsRef.current) return 2
            return 3
          })
          setFurthestStep((f) => Math.max(f, returnToResultsRef.current ? 2 : 3))
        }
        if (event === 'motion.started') {
          // Christian: deprecated for UI Generate (server never emits these there).
          // Still valid if someone runs CLI --with-motion against the same campaign.
          setCurrentStage('Motion')
        }
        if (event === 'motion.completed') {
          const motionPath = data.motion_path ? String(data.motion_path) : null
          if (motionPath) {
            setTiles((prev) => {
              if (!prev.length) return prev
              const product = String(data.product || '')
              const ratio = String(data.ratio || '')
              return prev.map((t) => {
                const matchProduct =
                  !product ||
                  t.product === product ||
                  t.product === product.toLowerCase().replace(/\s+/g, '-')
                const matchRatio = !ratio || t.ratio === ratio
                if (matchProduct && matchRatio && (t.locale || 'creative') === 'creative') {
                  return { ...t, motion_path: motionPath }
                }
                return t
              })
            })
          }
        }
        if (event === 'run.completed' || event === 'run.failed') {
          es.close()
          esRef.current = null
          if (event === 'run.failed') {
            setError(String(data.error || 'Generation failed'))
            setToast(String(data.error || 'Generation failed'))
            setToastAction('generate')
            setBusy(false)
            setCurrentStage(null)
            returnToResultsRef.current = false
            return
          }
          const backToResults = returnToResultsRef.current
          returnToResultsRef.current = false
          if (backToResults) {
            setToast('Creatives ready')
            setToastAction('results')
            setApplyHighlight(false)
            fetchReport(campaignId)
              .then((r) => {
                setReport(r)
                setTiles(r.creatives || [])
                goToStep(5)
              })
              .catch((err) => setError(String(err)))
              .finally(() => {
                setBusy(false)
                setCurrentStage(null)
              })
            return
          }
          setToast('Creatives ready')
          setToastAction('finalize')
          setApplyHighlight(true)
          fetchReport(campaignId)
            .then((r) => {
              setReport(r)
              setTiles(r.creatives || [])
              goToStep(3)
            })
            .catch((err) => setError(String(err)))
            .finally(() => {
              setBusy(false)
              setCurrentStage(null)
            })
        }
      })
      esRef.current = es
      // Stills only here. Motion is opted into later on Results (POST /motion).
      await generateCampaign(
        campaignId,
        {
          enabled: false,
          duration_seconds: 6,
          ratios: [],
        },
        imageQuality,
        {
          outputs: brief.outputs,
          framing: brief.framing || 'both',
          creatives_only: true,
        },
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(false)
      setCurrentStage(null)
      returnToResultsRef.current = false
    }
  }

  async function handleGenerateMore(opts: {
    outputs: string[]
    framing: 'close-up' | 'zoomed' | 'both'
    imageQuality: ImageQuality
    useSourceStills: boolean
    sourcePaths: string[]
  }) {
    if (!campaignId || !brief) {
      throw new Error('Open a campaign with a brief before generating more.')
    }
    if (
      !requireOpenAI('Add an OpenAI key before generating more stills.')
    ) {
      throw new Error('OpenAI key required')
    }
    const mergedOutputs = Array.from(
      new Set([...(brief.outputs || []), ...opts.outputs].filter(Boolean)),
    )
    const nextBrief = { ...brief, outputs: mergedOutputs, framing: opts.framing }
    setBrief(nextBrief)
    await saveCampaign(campaignId, nextBrief)

    setBusy(true)
    setError(null)
    setCurrentStage(null)
    setApplyHighlight(false)
    setGenerateSourcePaths(opts.useSourceStills ? opts.sourcePaths : [])
    setGenerateRunTotal(
      countNoTextCreatives(brief, {
        outputs: opts.outputs,
        framing: opts.framing,
      }),
    )
    returnToResultsRef.current = true
    setStartedAt(Date.now())
    goToStep(2)
    setTab('pipeline')
    setTiles([])

    esRef.current?.close()
    const es = subscribeEvents(campaignId, (event, data) => {
      if (event === 'tile.started') {
        const product = String(data.product || '')
        const ratio = String(data.ratio || '')
        setCurrentStage([ratio, product].filter(Boolean).join(' '))
      }
      if (event === 'tile.completed') {
        setTiles((prev) => [
          ...prev,
          {
            product: String(data.product || ''),
            ratio: String(data.ratio || ''),
            path: String(data.path || ''),
            locale: data.locale ? String(data.locale) : 'creative',
            source: String(data.source || ''),
            image_provider: String(data.image_provider || 'openai'),
            fallback_triggered: Boolean(data.fallback_triggered),
            motion_path: data.motion_path ? String(data.motion_path) : null,
            compliance: (data.compliance as Record<string, boolean>) || {},
          },
        ])
      }
      // Christian: deprecated for UI Generate (same as handleApproveAndGenerate).
      if (event === 'motion.started') setCurrentStage('Motion')
      if (event === 'motion.completed') {
        const motionPath = data.motion_path ? String(data.motion_path) : null
        if (motionPath) {
          setTiles((prev) => {
            const product = String(data.product || '')
            const ratio = String(data.ratio || '')
            return prev.map((t) => {
              const matchProduct =
                !product ||
                t.product === product ||
                t.product === product.toLowerCase().replace(/\s+/g, '-')
              const matchRatio = !ratio || t.ratio === ratio
              if (matchProduct && matchRatio && (t.locale || 'creative') === 'creative') {
                return { ...t, motion_path: motionPath }
              }
              return t
            })
          })
        }
      }
      if (event === 'run.completed' || event === 'run.failed') {
        es.close()
        esRef.current = null
        returnToResultsRef.current = false
        if (event === 'run.failed') {
          setError(String(data.error || 'Generation failed'))
          setToast(String(data.error || 'Generation failed'))
          setToastAction('generate')
          setBusy(false)
          setCurrentStage(null)
          goToStep(5)
          return
        }
        setToast('Creatives ready')
        setToastAction('results')
        fetchReport(campaignId)
          .then((r) => {
            setReport(r)
            setTiles(r.creatives || [])
            goToStep(5)
          })
          .catch((err) => setError(String(err)))
          .finally(() => {
            setBusy(false)
            setCurrentStage(null)
          })
      }
    })
    esRef.current = es
    await generateCampaign(
      campaignId,
      {
        enabled: false,
        duration_seconds: 6,
        ratios: [],
      },
      opts.imageQuality,
      {
        outputs: opts.outputs,
        framing: opts.framing,
        creatives_only: true,
        source_paths: opts.useSourceStills ? opts.sourcePaths : [],
      },
    )
  }

  async function handleFinalizeDone() {
    if (!campaignId) return
    setBusy(true)
    try {
      const r = await fetchReport(campaignId)
      setReport(r)
      setMotionEntry('ask')
      goToStep(4)
      setApplyHighlight(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  function handleMotionGenerate(req: MotionGenerateRequest) {
    if (!req.targets.length) return
    const id = campaignId
    if (!id) return

    const stamp = Date.now()
    const jobs: MotionJob[] = req.targets.map((t, i) => ({
      id: `${t.path}:${stamp}:${i}`,
      sourcePath: t.path,
      product: t.product,
      ratio: t.ratio,
      status: 'queued',
    }))

    // Jump to Results first so loading placeholders are visible right away.
    setTab('pipeline')
    goToStep(5)
    setToast(
      `Generating ${jobs.length} motion clip${jobs.length === 1 ? '' : 's'}…`,
    )
    setToastAction('results')
    setMotionJobs((prev) => [
      ...prev.filter((j) => j.status === 'queued' || j.status === 'running' || j.status === 'error'),
      ...jobs,
    ])
    setReport((prev) => {
      if (prev) return prev
      return {
        campaign_id: id,
        started_at: new Date().toISOString(),
        finished_at: '',
        creatives: tiles,
        totals: {},
      }
    })

    motionChainRef.current = motionChainRef.current
      .catch(() => undefined)
      .then(async () => {
        let finished = 0
        for (const job of jobs) {
          setMotionJobs((prev) =>
            prev.map((j) => (j.id === job.id ? { ...j, status: 'running' } : j)),
          )
          setToast(
            `Generating motion ${finished + 1}/${jobs.length}: ${job.product} · ${job.ratio}`,
          )
          setToastAction('results')
          try {
            const result = await generateMotion(
              id,
              job.sourcePath,
              req.durationSeconds,
              req.prompt,
              req.promptExtra,
            )
            setReport((prev) => {
              if (!prev) return prev
              const jobSrc = job.sourcePath.replace(/\\/g, '/').toLowerCase()
              const jobTail = jobSrc.replace(/^campaigns\/[^/]+\//, '')
              const creatives = prev.creatives.map((c) => {
                const src = stillKey(c)
                if (!src) return c
                const srcTail = src.replace(/^campaigns\/[^/]+\//, '')
                const same =
                  src === jobSrc ||
                  srcTail === jobTail ||
                  src.endsWith('/' + jobTail) ||
                  jobSrc.endsWith('/' + srcTail)
                return same ? { ...c, motion_path: result.motion_path } : c
              })
              setTiles(creatives)
              return { ...prev, creatives }
            })
            setMotionJobs((prev) =>
              prev.map((j) => (j.id === job.id ? { ...j, status: 'done' } : j)),
            )
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err)
            setMotionJobs((prev) =>
              prev.map((j) =>
                j.id === job.id ? { ...j, status: 'error', error: message } : j,
              ),
            )
          }
          finished += 1
        }
        try {
          const refreshed = await fetchReport(id)
          setReport((prev) => {
            const nextCreatives = mergeMotionPaths(
              prev?.creatives ?? [],
              refreshed.creatives || [],
            )
            setTiles(nextCreatives)
            return { ...refreshed, creatives: nextCreatives }
          })
        } catch {
          /* keep patched report */
        }
        setMotionJobs((prev) => {
          const left = prev.filter(
            (j) => j.status === 'queued' || j.status === 'running' || j.status === 'error',
          )
          const errCount = left.filter((j) => j.status === 'error').length
          if (errCount) {
            setToast(
              `Motion finished with ${errCount} error${errCount === 1 ? '' : 's'}.`,
            )
          } else {
            setToast(
              `Motion ready · ${jobs.length} clip${jobs.length === 1 ? '' : 's'}`,
            )
          }
          setToastAction('results')
          return left
        })
      })
  }

  async function handleOpenPastCampaign(id: string) {
    const opened = await openPastCampaign(id)
    setCampaignId(opened.campaign_id)
    setBrief(opened.brief)
    setManifest(opened.asset_manifest)
    setMissingFields(opened.missing_fields || [])
    setProductSeeds(null)
    const openedTiles = opened.tiles || []
    setTiles(openedTiles)
    setReport(opened.report)
    setError(null)
    setBusy(false)
    setStartedAt(null)
    setCurrentStage(null)
    setMotionJobs([])
    setMotionEntry('settings')
    setTab('pipeline')

    const hasTiles = openedTiles.length > 0
    const hasReport = Boolean(opened.report)
    let nextStep = 1
    let unlockThrough = 1
    if (opened.stage === 'results' && opened.report) {
      nextStep = 5
      unlockThrough = 5
    } else if (opened.brief && (opened.stage === 'finalize' || hasTiles)) {
      nextStep = 3
      // Results stays reachable when stills exist; Motion only when a report exists.
      unlockThrough = hasReport || hasTiles ? 5 : 3
    } else if (opened.brief) {
      nextStep = 1
      unlockThrough = 1
    } else {
      throw new Error('This campaign has no brief or creatives to open.')
    }
    setFurthestStep(unlockThrough)
    setStep(nextStep)
  }

  async function restart() {
    await discardEphemeral(campaignId)
    esRef.current?.close()
    esRef.current = null
    setStep(0)
    setFurthestStep(0)
    setCampaignId(null)
    setBrief(null)
    setManifest(null)
    setMissingFields([])
    setProductSeeds(null)
    setTiles([])
    setReport(null)
    setError(null)
    setStartedAt(null)
    setCurrentStage(null)
    setImageQuality('medium')
    setApplyHighlight(false)
    setTab('pipeline')
    setGenerateRunTotal(null)
    setMotionJobs([])
    setMotionEntry('ask')
  }

  const chipLabel = busy
    ? `Generating · ${tiles.length}/${creativeTotal} stills · ${formatElapsed(elapsedSec)}${
        currentStage ? ` · next: ${currentStage}` : ''
      }`
    : null

  if (!authReady || !healthReady) {
    return (
      <div className="app-shell" style={{ padding: '2rem' }}>
        <p style={{ color: 'var(--muted)' }}>Loading…</p>
      </div>
    )
  }

  if (showLanding) {
    return <LandingHero onEnter={enterFromLanding} />
  }

  // After Get started: welcome menu, about, examples, then signup/signin.
  if (hosted && !authUser) {
    const view = preAuthView || 'welcome'
    if (view === 'about') {
      return (
        <AboutPage
          onBack={() => setPreAuthView('welcome')}
          onGetStarted={() => setPreAuthView('signup')}
        />
      )
    }
    if (view === 'examples') {
      return (
        <PublicExamplesGallery
          onBack={() => setPreAuthView('welcome')}
          onGetStarted={() => setPreAuthView('signup')}
        />
      )
    }
    if (view === 'signin' || view === 'signup') {
      return (
        <LoginScreen
          initialMode={view}
          trialMessage="Create a free account to use Campaign Pipeline. You get 3 trial generate runs on the demo key; your library and creatives stay in your account."
          onBack={() => setPreAuthView('welcome')}
          onSignedIn={() => {
            setPreAuthView(null)
            refreshAuth()
            refreshHealth()
          }}
        />
      )
    }
    return (
      <WelcomeGate
        onSignUp={() => setPreAuthView('signup')}
        onSignIn={() => setPreAuthView('signin')}
        onAbout={() => setPreAuthView('about')}
        onExamples={() => setPreAuthView('examples')}
      />
    )
  }

  if (showInstall) {
    return (
      <InstallSetup
        openaiConfigured={openaiConfigured}
        motionAvailable={motionAvailable}
        onKeysChanged={() => {
          refreshHealth()
        }}
        onContinue={finishInstallGate}
      />
    )
  }

  return (
    <div className="app-shell">
      <header className="app-chrome">
        <div className="app-chrome-bar">
          <div className="brand-lockup">
            <button
              type="button"
              className="brand-home-btn"
              onClick={() => setShowLanding(true)}
              aria-label="Return to title screen"
            >
              <h1 className="name-header page-title header-text-style">HERBIE CREATIVE</h1>
            </button>
            <p className="app-subtitle">Campaign Pipeline</p>
          </div>
          <nav className="app-tabs" aria-label="Main">
            <button
              type="button"
              className={tab === 'pipeline' ? 'app-tab active' : 'app-tab'}
              onClick={() => setTab('pipeline')}
            >
              Pipeline
            </button>
            <button
              type="button"
              className={tab === 'library' ? 'app-tab active' : 'app-tab'}
              onClick={() => setTab('library')}
            >
              Library
            </button>
            <button
              type="button"
              className={tab === 'settings' ? 'app-tab active' : 'app-tab'}
              onClick={() => setTab('settings')}
            >
              Settings
            </button>
            {authUser && (
              <button
                type="button"
                className="app-tab"
                onClick={() => {
                  void logout().finally(() => {
                    setAuthUser(null)
                    refreshAuth()
                  })
                }}
              >
                Sign out
              </button>
            )}
          </nav>
        </div>
        {accountTrialActive && (
          <div className="banner" style={{ margin: '0.75rem 1.25rem 0' }}>
            Free trial: {trial?.remaining ?? 0} of {trial?.limit ?? 3} generate runs left
            {typeof trial?.stills_remaining === 'number'
              ? ` · up to ${trial.stills_remaining} stills remaining`
              : ''}
            . After that, add your own OpenAI key in Settings.
          </div>
        )}
        {tab === 'pipeline' && (
          <div className="app-chrome-steps">
            <WizardStepper
              step={step}
              unlockedThrough={furthestStep}
              isStepEnabled={isStepEnabled}
              onStep={handleStepNav}
            />
        </div>
        )}
      </header>

      {chipLabel && (
        <button
          type="button"
          className="gen-status-chip"
          onClick={() => {
            setTab('pipeline')
            goToStep(2)
          }}
        >
          {chipLabel}
        </button>
      )}

      {toast && (
        <div className="toast-banner">
          {toast}
          <button type="button" className="btn-ghost" onClick={openToastTarget}>
            {toastAction === 'results'
              ? 'Open Results'
              : toastAction === 'generate'
                ? 'Open Generate'
                : 'Open Finalize'}
          </button>
        </div>
      )}

      <main className="app-workspace">
      {!openaiConfigured && tab === 'pipeline' && (
        <div className="banner">
          OpenAI key not set. Add your key to generate creatives. Library still works without it.
          <button
            type="button"
            className="btn-ghost"
            style={{ marginLeft: '0.75rem' }}
            onClick={() => setShowInstall(true)}
          >
            Add key
          </button>
        </div>
      )}

      {tab === 'settings' && (
        <SettingsPanel
          authUser={authUser}
          hosted={hosted}
          onKeysChanged={() => {
            refreshHealth()
          }}
        />
      )}

      {tab === 'library' && (
        <SamplesGallery
          onOpenCampaign={handleOpenPastCampaign}
          desktopTools={desktopTools}
        />
      )}

      {tab === 'pipeline' && (
        <>
          {step === 0 && (
            <IntakeStep
              onNext={handleIntake}
              onLoadSample={handleLoadSample}
              desktopTools={desktopTools}
            />
          )}
          {step === 1 && brief && campaignId && (
            <ReviewStep
              campaignId={campaignId}
              brief={brief}
              setBrief={setBrief}
              manifest={manifest}
              missingFields={missingFields}
              imageQuality={imageQuality}
              setImageQuality={setImageQuality}
              onBack={() => goToStep(0)}
              onApprove={handleApprove}
              onUploadAssets={handleUploadAssets}
              busy={busy}
              error={error}
              initialProductSeeds={productSeeds}
            />
          )}
          {step === 2 && (
            <GenerateStep
              done={tiles.length}
              total={creativeTotal}
              pipelineTotal={creativePlan?.pipelineTotal ?? creativeTotal}
              finalizeCount={creativePlan?.finalizeCount ?? 0}
              plan={creativePlan}
              elapsedSec={elapsedSec}
              tiles={tiles}
              currentStage={currentStage}
              sourcePreviewPaths={generateSourcePaths}
            />
          )}
          {step === 3 && campaignId && brief && (
            <FinalizeStep
              campaignId={campaignId}
              brief={brief}
              setBrief={setBrief}
              creatives={tiles}
              stillGenerating={busy}
              applyHighlight={applyHighlight}
              onBack={() => goToStep(report ? 5 : 2)}
              onDone={handleFinalizeDone}
            />
          )}
          {step === 4 && report && campaignId && brief && (
            <MotionStep
              campaignId={campaignId}
              report={report}
              brief={brief}
              setBrief={setBrief}
              motionAvailable={motionAvailable}
              entry={motionEntry}
              generating={motionJobs.some(
                (j) => j.status === 'queued' || j.status === 'running',
              )}
              onGenerate={handleMotionGenerate}
              onBack={() => goToStep(3)}
              onDone={() => goToStep(5)}
              onUploadAssets={handleUploadAssets}
            />
          )}
          {step === 5 && campaignId && (
            <ResultsStep
              report={
                report || {
                  campaign_id: campaignId,
                  started_at: '',
                  finished_at: '',
                  creatives: tiles,
                  totals: {},
                }
              }
              campaignId={campaignId}
              briefOutputs={brief?.outputs}
              briefFraming={brief?.framing || 'both'}
              plan={creativePlan}
              imageQuality={imageQuality}
              motionJobs={motionJobs}
              onReportUpdate={(next) => {
                setReport(next)
                setTiles(next.creatives || [])
              }}
              onRestart={() => void restart()}
              onBrowsePast={() => setTab('library')}
              onGenerateMore={brief ? (opts) => handleGenerateMore(opts) : undefined}
              onMotion={() => {
                setMotionEntry('settings')
                goToStep(4)
              }}
              onFinalize={
                brief
                  ? () => {
                      setTiles((report?.creatives || tiles).slice())
                      goToStep(3)
                    }
                  : undefined
              }
            />
          )}
        </>
      )}
      </main>
    </div>
  )
}
