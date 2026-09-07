/**
 * PRAMAAN API service layer — all HTTP calls to the FastAPI backend.
 * Base URL reads from Vite env (VITE_API_URL) or falls back to localhost:8000.
 */
import type {
  PipelineStateResponse,
  AttackScenario,
  TriggerResponse,
  ResetResponse,
  AssuranceReport,
  AuditChainResponse,
} from '../types/api'

const BASE_URL =
  import.meta.env.VITE_API_URL ?? (import.meta.env.PROD ? '' : 'http://localhost:8000')

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  /** GET /api/pipeline/state — current pipeline state */
  getPipelineState(): Promise<PipelineStateResponse> {
    return request<PipelineStateResponse>('/api/pipeline/state')
  },

  /** POST /api/demo/trigger/{scenario} — activate an attack scenario */
  triggerScenario(scenario: AttackScenario): Promise<TriggerResponse> {
    return request<TriggerResponse>(`/api/demo/trigger/${scenario}`, {
      method: 'POST',
    })
  },

  /** POST /api/demo/reset — clear all active scenarios */
  resetPipeline(): Promise<ResetResponse> {
    return request<ResetResponse>('/api/demo/reset', { method: 'POST' })
  },

  /** GET /api/report/generate — full assurance audit report */
  getAssuranceReport(): Promise<AssuranceReport> {
    return request<AssuranceReport>('/api/report/generate')
  },

  /** GET /api/audit/events — cryptographic audit chain event blocks */
  getAuditEvents(): Promise<AuditChainResponse> {
    return request<AuditChainResponse>('/api/audit/events')
  },
}


