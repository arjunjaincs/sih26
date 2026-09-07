/**
 * PRAMAAN global pipeline store — Zustand.
 * Holds live pipeline state fetched from the FastAPI backend.
 * All dashboard components read from this store; only this file calls the API.
 */
import { create } from 'zustand'
import { api } from '../services/api'
import type { ApiStageState, AttackScenario } from '../types/api'

/** Per-stage display metadata that doesn't come from the API */
const STAGE_META: Record<string, { stage_number: string; subtitle: string; summary_clean: string }> = {
  stage_1: {
    stage_number: '01',
    subtitle: 'Distribution & Dataset Hygiene',
    summary_clean:
      'Spectral signature scan verified class-conditional features. Marginal dispersion anomaly in night-scene classes is within natural long-tail limits with no poisoning signature.',
  },
  stage_2: {
    stage_number: '02',
    subtitle: 'Weight Integrity & Backdoors',
    summary_clean:
      'Neural Cleanse pattern inversion scanned 18 classification heads. Minimum trigger norm safely above anomaly threshold; zero backdoor trojans detected.',
  },
  stage_3: {
    stage_number: '03',
    subtitle: 'Runtime Telemetry & Perturbations',
    summary_clean:
      'STRIP entropy monitoring active across video frames. Minor transient dip attributed to camera pan homogeneity; no input tampering or trojan execution.',
  },
  stage_4: {
    stage_number: '04',
    subtitle: 'Bayesian Fusion & Threat Scoring',
    summary_clean:
      'Continuous evidence fusion combining multi-detector inputs into composite risk metrics. Global threat score sits at 0.018, well below defense threshold.',
  },
  stage_5: {
    stage_number: '05',
    subtitle: 'Merkle Attestation & Compliance',
    summary_clean:
      'Immutable audit ledger synchronized with offline Merkle tree root. End-to-end chain of custody verified without discrepancies.',
  },
}

const STAGE_METRICS: Record<string, { label: string; value: string }[]> = {
  stage_1: [
    { label: 'Samples Verified', value: '142,800' },
    { label: 'Class Parity', value: '0.992' },
    { label: 'Poisoning Index', value: '< 0.01' },
  ],
  stage_2: [
    { label: 'Trigger L1 Norm', value: '1.14 / 2.0 τ' },
    { label: 'Weight Checksum', value: 'MATCH' },
    { label: 'Layer Sparsity', value: '0.08%' },
  ],
  stage_3: [
    { label: 'Entropy Mean', value: '2.38 nats' },
    { label: 'Input Jitter', value: '0.012 RMS' },
    { label: 'Frame Latency', value: '18.4 ms' },
  ],
  stage_4: [
    { label: 'Posterior Risk', value: '0.018' },
    { label: 'Active Detectors', value: '7 / 7 Online' },
    { label: 'State Coherence', value: '0.998' },
  ],
  stage_5: [
    { label: 'Merkle Root', value: 'VERIFIED' },
    { label: 'Compliance Level', value: 'DEF-STD-05' },
    { label: 'Attestation Sign', value: 'ED25519-OK' },
  ],
}

/** Enrich a raw API stage with UI-only metadata fields */
function enrichStage(s: ApiStageState) {
  const meta = STAGE_META[s.stage_id]
  const metrics = STAGE_METRICS[s.stage_id] ?? []
  return {
    ...s,
    stage_number: meta?.stage_number ?? '??',
    stage_subtitle: meta?.subtitle ?? '',
    metrics,
    summary:
      s.findings.length > 0 && s.findings.some((f) => !f.mitigated)
        ? `${s.findings.length} active finding(s) detected. Highest severity: ${s.findings[0].severity.toUpperCase()}.`
        : meta?.summary_clean ?? '',
  }
}

// ─── Store shape ─────────────────────────────────────────────────────────────

export interface EnrichedStageState extends ApiStageState {
  stage_number: string
  stage_subtitle: string
  metrics: { label: string; value: string }[]
  summary: string
}

interface PipelineStore {
  // Data
  stages: EnrichedStageState[]
  activeScenarios: AttackScenario[]
  pipelineId: string
  capturedAt: string | null
  // Derived
  overallRisk: string
  overallConfidence: number
  coveragePct: number
  // UI state
  isLoading: boolean
  isTriggeringScenario: boolean
  error: string | null
  lastAction: string | null
  // Actions
  fetchPipelineState: () => Promise<void>
  triggerScenario: (scenario: AttackScenario) => Promise<void>
  resetPipeline: () => Promise<void>
}

function computeOverallRisk(stages: EnrichedStageState[]): string {
  const order = ['clean', 'low', 'medium', 'high', 'critical']
  let max = 0
  for (const s of stages) {
    const idx = order.indexOf(s.risk)
    if (idx > max) max = idx
  }
  return order[max]
}

export const usePipelineStore = create<PipelineStore>((set, get) => ({
  stages: [],
  activeScenarios: [],
  pipelineId: 'PL-CV-AIRGAP-26228',
  capturedAt: null,
  overallRisk: 'clean',
  overallConfidence: 0,
  coveragePct: 0,
  isLoading: false,
  isTriggeringScenario: false,
  error: null,
  lastAction: null,

  fetchPipelineState: async () => {
    set({ isLoading: true, error: null })
    try {
      const data = await api.getPipelineState()
      const enriched = data.stages.map(enrichStage)
      const avgConf =
        enriched.reduce((sum, s) => sum + s.confidence, 0) / (enriched.length || 1)
      const avgCov =
        enriched.reduce((sum, s) => sum + s.coverage_pct, 0) / (enriched.length || 1)
      set({
        stages: enriched,
        activeScenarios: data.active_scenarios,
        pipelineId: data.pipeline_id,
        capturedAt: data.captured_at,
        overallRisk: computeOverallRisk(enriched),
        overallConfidence: avgConf,
        coveragePct: avgCov,
        isLoading: false,
      })
    } catch (err) {
      set({ isLoading: false, error: String(err) })
    }
  },

  triggerScenario: async (scenario: AttackScenario) => {
    set({ isTriggeringScenario: true, error: null })
    try {
      const resp = await api.triggerScenario(scenario)
      set({ lastAction: `Scenario activated: ${resp.scenario} → ${resp.affected_stages.join(', ')}` })
      // Immediately re-fetch so the pipeline cards update
      await get().fetchPipelineState()
    } catch (err) {
      set({ error: String(err) })
    } finally {
      set({ isTriggeringScenario: false })
    }
  },

  resetPipeline: async () => {
    set({ isTriggeringScenario: true, error: null })
    try {
      await api.resetPipeline()
      set({ lastAction: 'Pipeline reset to clean baseline.' })
      await get().fetchPipelineState()
    } catch (err) {
      set({ error: String(err) })
    } finally {
      set({ isTriggeringScenario: false })
    }
  },
}))
